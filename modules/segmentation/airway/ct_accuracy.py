"""Compact-model accuracy work: physical CT context, partial labels and widening."""
from pathlib import Path
import numpy as np
import SimpleITK as sitk
import torch
from torch import nn
from torch.nn import functional as F
from .ct_student import CTStudent, CHANNELS

ACCURACY_CHANNELS=(16,32,32,64)
from .ct_geometry import context_indices, prepare_grid, make_context, largest_airway_component


def partial_label_loss(logits,target,known):
    """Unknown public nodule labels produce no loss, rather than false negatives."""
    y=target.float();l=logits.float();p=l.sigmoid()
    pos=l.new_tensor([1.,8.,12.])[None,:,None,None]
    bce=F.binary_cross_entropy_with_logits(l,y,pos_weight=pos,reduction='none')
    # Emphasize boundaries during training; no extra inference operators.
    boundary=(F.max_pool2d(y,3,1,1)-(-F.max_pool2d(-y,3,1,1))).clamp(0,1)
    bce=(bce*(1+boundary)).mean((2,3))
    dice=1-(2*(p*y).sum((2,3))+1)/(p.sum((2,3))+y.sum((2,3))+1)
    valid=known.to(l.dtype)
    return ((bce+2*dice)*valid).sum()/valid.sum().clamp_min(1)


def widen_student(old,channels=ACCURACY_CHANNELS):
    """Function-preserving Net2Wider initialization, including U-Net concat maps."""
    new=CTStudent(channels).eval();old=old.cpu().eval()
    maps=[torch.arange(n)%o for o,n in zip(old.channels,channels)]
    a,b,c,d=maps;oa,ob,oc,od=old.channels
    mapping={
      'enc0.0':(torch.arange(5),a),'enc0.3':(a,a),
      'enc1.0':(a,b),'enc1.3':(b,b),'enc2.0':(b,c),'enc2.3':(c,c),
      'enc3.0':(c,d),'enc3.3':(d,d),
      'up2.reduce':(d,c),'up2.conv.0':(torch.cat((c,c+oc)),c),'up2.conv.3':(c,c),
      'up1.reduce':(c,b),'up1.conv.0':(torch.cat((b,b+ob)),b),'up1.conv.3':(b,b),
      'up0.reduce':(b,a),'up0.conv.0':(torch.cat((a,a+oa)),a),'up0.conv.3':(a,a),
      'head':(a,torch.arange(3))}
    source=dict(old.named_modules());dest=dict(new.named_modules())
    with torch.no_grad():
        for name,(im,om) in mapping.items():
            src,dst=source[name],dest[name]
            counts=torch.bincount(im,minlength=src.in_channels).float()
            dst.weight.copy_(src.weight[om][:,im]/counts[im][None,:,None,None])
            if src.bias is not None:dst.bias.copy_(src.bias[om])
            if name.endswith(('.0','.3')):
                bn=name[:-1]+str(int(name[-1])+1)
                for field in ['weight','bias','running_mean','running_var']:
                    getattr(dest[bn],field).copy_(getattr(source[bn],field)[om])
                dest[bn].num_batches_tracked.copy_(source[bn].num_batches_tracked)
    return new

