"""Small 2.5-D, three-head U-Net for a custom PL engine (no AMD DPU).

Five neighbouring native CT slices -> three independent centre-slice logits.
Only Conv2d, foldable BatchNorm, ReLU, MaxPool, nearest Resize and Concat.
"""
from __future__ import annotations
import copy
import torch
from torch import nn
from torch.nn import functional as F

PARAMETER_BUDGET = 250_000
INPUT_SLICES = 5
CHANNELS = (8, 16, 32, 64)


class ConvBlock(nn.Sequential):
    def __init__(self, cin, cout):
        super().__init__(nn.Conv2d(cin, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(),
                         nn.Conv2d(cout, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU())


class UpBlock(nn.Module):
    def __init__(self, cin, cout):
        super().__init__()
        self.reduce = nn.Conv2d(cin, cout, 1)
        self.conv = ConvBlock(2*cout, cout)

    def forward(self, x, skip):
        x = self.reduce(F.interpolate(x, scale_factor=2, mode="nearest"))
        return self.conv(torch.cat((x, skip), dim=1))


class CTStudent(nn.Module):
    def __init__(self, channels=CHANNELS):
        super().__init__()
        if len(channels)!=4 or min(channels)<=0 or max(channels)>64 or max(2*x for x in channels[:3])>64:
            raise ValueError('Channels exceed the custom PL engine limits')
        self.channels=tuple(channels)
        a, b, c, d = self.channels
        self.enc0 = ConvBlock(INPUT_SLICES, a)
        self.enc1 = ConvBlock(a, b)
        self.enc2 = ConvBlock(b, c)
        self.enc3 = ConvBlock(c, d)
        self.pool = nn.MaxPool2d(2)
        self.up2 = UpBlock(d, c); self.up1 = UpBlock(c, b); self.up0 = UpBlock(b, a)
        self.head = nn.Conv2d(a, 3, 1)
        if sum(p.numel() for p in self.parameters()) > PARAMETER_BUDGET:
            raise ValueError("Student exceeds PL parameter budget")

    def forward(self, x):
        a = self.enc0(x); b = self.enc1(self.pool(a)); c = self.enc2(self.pool(b))
        d = self.enc3(self.pool(c))
        return self.head(self.up0(self.up1(self.up2(d, c), b), a))


def fold_batch_norm(model):
    """Produce inference weights without runtime BatchNorm; never change the training model."""
    model = copy.deepcopy(model).eval()
    for block in model.modules():
        if isinstance(block, ConvBlock):
            for i in (0, 3):
                block[i] = torch.nn.utils.fuse_conv_bn_eval(block[i], block[i+1])
                block[i+1] = nn.Identity()
    return model


def segmentation_loss(logits, target):
    # Independent labels: nodules and lung region can overlap.
    # Equal head weighting prevents the lung's size from dominating sparse structures.
    positive_weight = logits.new_tensor([1.,20.,40.],dtype=torch.float32)[None,:,None,None]
    bce = F.binary_cross_entropy_with_logits(logits, target, reduction="none",pos_weight=positive_weight).mean((0, 2, 3))
    # Accumulate in FP32: a 4x160x160 half-precision sum can overflow 65504.
    probability = logits.float().sigmoid()
    axes = (0, 2, 3)
    dice = 1 - (2*(probability*target).sum(axes)+1) / (probability.sum(axes)+target.sum(axes)+1)
    return (bce + 2*dice).mean()


def model_cost(model, height=512, width=512):
    if height % 8 or width % 8:
        raise ValueError("Image dimensions must be multiples of 8")
    macs, max_input, max_output = [], [], []
    hooks = []
    def count(module, args, output):
        if isinstance(module, nn.Conv2d):
            macs.append(output.numel() * (module.in_channels//module.groups) * module.kernel_size[0]*module.kernel_size[1])
        max_input.append(args[0].numel()); max_output.append(output.numel())
    for m in model.modules():
        if isinstance(m, (nn.Conv2d, nn.MaxPool2d)):
            hooks.append(m.register_forward_hook(count))
    try:
        with torch.no_grad():
            model.eval()(torch.zeros(1, INPUT_SLICES, height, width))
    finally:
        for h in hooks:
            h.remove()
    params = sum(p.numel() for p in model.parameters())
    return {"architecture": "CTStudent_2p5D_"+'_'.join(map(str,model.channels)), "input_slices": INPUT_SLICES,
            "output_heads": ["lung", "airway", "nodule"], "parameters": params,
            "parameter_budget": PARAMETER_BUDGET, "int8_parameter_bytes_estimate": params,
            "int8_note": "Estimate only; scales and wider biases add overhead. Measured quantization results, if available, are in int8/quantization_report.json.",
            "input_height": height, "input_width": width,
            "macs_per_slice": sum(macs), "macs_for_139_slice_case": 139*sum(macs),
            "largest_conv_input_int8_bytes": max(max_input), "largest_operator_output_int8_bytes": max(max_output),
            "fpga_note": "Feature maps/skip connections reside in DDR; line buffers in PL. Measured throughput must be validated for each deployed model."}
