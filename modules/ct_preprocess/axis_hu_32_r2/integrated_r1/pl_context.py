"""Pack five already-quantized PL planes for the existing convolution engine.

HU clipping/normalization/quantization is not repeated here. Context gathering
and HWC padding remain PS layout operations until a fused hardware path exists.
"""
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from airway.ct_geometry import context_indices
from ct_pl.quantized_runtime import Quantized


class PLContextPreparer:
    def __init__(self, graph, quantized, metadata, spacing_z=None):
        if (not isinstance(quantized, np.ndarray) or quantized.dtype != np.int8
                or quantized.ndim != 3 or min(quantized.shape) < 1
                or not quantized.flags.c_contiguous):
            raise ValueError('Nonempty contiguous int8 ZYX PL output required')
        if spacing_z is not None and (not np.isfinite(spacing_z) or spacing_z <= 0):
            raise ValueError('Positive finite Z spacing required')
        first = next(n for n in graph.nodes if n['op'] == 'QuantizeLinear'
                     and n['inputs'][0] == graph.plan['input'])
        self.scale, self.zero = [graph.arrays[n] for n in first['inputs'][1:]]
        if (self.scale.dtype != np.float32 or self.zero.dtype != np.int8
                or self.scale.size != 1 or self.zero.size != 1
                or not np.isfinite(self.scale).all() or self.scale.item() <= 0
                or self.scale.item() != metadata['scale']
                or self.zero.item() != metadata['zero']):
            raise ValueError('PL quantizer and convolution graph model mismatch')
        self.graph, self.ct, self.spacing_z = graph, quantized, spacing_z

    def __call__(self, z):
        if (isinstance(z, (bool, np.bool_)) or not isinstance(z, (int, np.integer))
                or not 0 <= z < len(self.ct)):
            raise ValueError('Context slice outside PL volume')
        ct = self.ct
        _, h, w = ct.shape
        hp, wp = (h + 7) // 8 * 8, (w + 7) // 8 * 8
        indices = (context_indices(z, len(ct), self.spacing_z)
                   if self.spacing_z is not None else
                   np.clip(np.arange(z - 2, z + 3), 0, len(ct) - 1))
        out = np.empty((hp, wp, 8), np.int8)
        self.graph.ops.ct_context5(*[ct[i].ctypes.data for i in indices],
                                   out.ctypes.data, h, w, hp, wp)
        return Quantized(self.graph.nchw(out[:, :, :5]), self.scale, self.zero)

    def slices(self):
        # Same bounded one-future prefetch as the released PS context preparer.
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix='ct-context') as pool:
            pending = pool.submit(self, 0)
            for z in range(len(self.ct)):
                value = pending.result()
                if z + 1 < len(self.ct):
                    pending = pool.submit(self, z + 1)
                yield z, value
