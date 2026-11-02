"""Exact integer grouping and bounded binary-mask validation for display assets."""
import numpy as np


def cluster_inverse(coordinates):
    values=np.asarray(coordinates)
    if values.ndim!=2 or values.shape[1]!=3 or values.dtype!=np.int32:
        raise ValueError('Expected the original Nx3 int32 cluster coordinates')
    if not len(values):return np.empty(0,dtype=np.intp)
    lo=values.min(axis=0).astype(np.int64)
    hi=values.max(axis=0).astype(np.int64)
    spans=[int(hi[i])-int(lo[i])+1 for i in range(3)]
    # Mixed-radix encoding is injective and preserves the original x/y/z
    # lexicographic ordering. Overflow must use the original row algorithm.
    if spans[0]*spans[1]*spans[2]>(1<<63):
        return np.unique(values,axis=0,return_inverse=True)[1]
    wide=values.astype(np.int64)
    keys=((wide[:,0]-lo[0])*spans[1]+(wide[:,1]-lo[1]))*spans[2]+(wide[:,2]-lo[2])
    return np.unique(keys,return_inverse=True)[1]


def is_binary(values,block_size=262144):
    array=np.asarray(values)
    if array.dtype.kind not in 'buifc':raise ValueError('Expected a numeric medical mask')
    if block_size<=0:raise ValueError('Positive validation block required')
    # A view for normal contiguous medical arrays; at most two small boolean
    # temporaries. NaN, infinity, negatives and fractional values stay invalid.
    flat=array.reshape(-1)
    for start in range(0,flat.size,block_size):
        part=flat[start:start+block_size]
        if np.any((part!=0)&(part!=1)):return False
    return True
