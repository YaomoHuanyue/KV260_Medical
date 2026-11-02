"""Same 14 offset decisions, with one band extraction instead of 14 scans."""
import numpy as np


def preserving_offset(regularized, target_voxels, sigma_mm):
    if (not isinstance(regularized,np.ndarray) or regularized.dtype!=np.float32 or
            not np.isfinite(regularized).all() or not 0<=target_voxels<=regularized.size or
            not np.isfinite(sigma_mm) or sigma_mm<=0):
        raise ValueError('Invalid volume offset input')
    low,high=-2.0*sigma_mm,2.0*sigma_mm
    # The original comparison uses a float32 array and a Python scalar;
    # NumPy casts that scalar to float32. Keep the same rounding at ties.
    band=(regularized>np.float32(low))&(regularized<=np.float32(high))
    values=np.sort(regularized[band]);constant=int(np.count_nonzero(regularized>np.float32(high)))
    for _ in range(14):
        offset=(low+high)*.5
        count=constant+len(values)-int(np.searchsorted(values,np.float32(offset),side='right'))
        if count>target_voxels:low=offset
        else:high=offset
    return (low+high)*.5,dict(scans_replaced=14,band_voxels=len(values),constant_positive_voxels=constant)
