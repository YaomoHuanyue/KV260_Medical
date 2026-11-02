"""Exact first-order probability correction only at eligible distance samples.

Slabs bound scratch memory even when an entire field is in the distance band.
Each finite difference uses the same float32 subtraction, scalar division and
float32 output assignment as numpy.gradient(edge_order=1). No interpolation,
mask, centreline or smoothing rule changes here.
"""
import numpy as np


def correct_probability_band(probability,sdf,spacing_xyz,threshold,limit_mm,*,slab_depth=8):
    if (probability.dtype!=np.float32 or sdf.dtype!=np.float32 or
            probability.ndim!=3 or probability.shape!=sdf.shape or min(sdf.shape)<2):
        raise ValueError('Same-size float32 probability/distance volumes with axes >=2 required')
    spacing=np.asarray(spacing_xyz)
    if (spacing.shape!=(3,) or not np.isfinite(spacing).all() or np.any(spacing<=0) or
            not np.isfinite([threshold,limit_mm]).all() or limit_mm<=0 or
            not isinstance(slab_depth,int) or slab_depth<1 or slab_depth>32):
        raise ValueError('Invalid physical correction parameters')
    count=eligible=0
    for begin in range(0,sdf.shape[0],slab_depth):
        slab=sdf[begin:begin+slab_depth]
        position=list(np.nonzero((slab>=-limit_mm)&(slab<=limit_mm)))
        if not position[0].size:continue
        position[0]+=begin;eligible+=position[0].size
        gradients=[]
        for axis,distance in enumerate(spacing[::-1]):
            center=position[axis];maximum=sdf.shape[axis]-1
            low=list(position);high=list(position)
            low[axis]=np.maximum(center-1,0);high[axis]=np.minimum(center+1,maximum)
            numerator=probability[tuple(high)]-probability[tuple(low)]
            # Match gradient's uniform interior expression and output dtype.
            gradient=(numerator/(2*distance)).astype(np.float32)
            boundary=(center==0)|(center==maximum)
            gradient[boundary]=(numerator[boundary]/distance).astype(np.float32)
            gradients.append(gradient)
        gz,gy,gx=gradients
        magnitude=np.sqrt(gx*gx+gy*gy+gz*gz)
        local=(probability[tuple(position)]-threshold)/np.maximum(magnitude,1e-4)
        accepted=magnitude>=.02
        selected=tuple(v[accepted] for v in position)
        sdf[selected]=np.clip(local[accepted],-limit_mm,limit_mm)
        count+=int(np.count_nonzero(accepted))
    return count,dict(implementation='exact_first_order_local_gradient_slabs',
        eligible_distance_samples=eligible,corrected_samples=count,slab_depth=slab_depth,
        dense_gradient_volumes_allocated=0)
