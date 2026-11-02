"""CT inference geometry and mask postprocessing; no training runtime required."""
import numpy as np
import SimpleITK as sitk

XY_SPACING=.7617189884185791


def context_indices(z, nz, spacing_z):
    return np.clip(z+np.rint(np.arange(-2,3)*2.5/spacing_z).astype(int),0,nz-1)


def prepare_grid(image):
    canonical=sitk.DICOMOrient(image,'LPS')
    spacing=(XY_SPACING,XY_SPACING,canonical.GetSpacing()[2])
    if np.allclose(canonical.GetSpacing()[:2],spacing[:2],rtol=0,atol=1e-6):
        return sitk.Cast(canonical,sitk.sitkInt16)
    size=[int(np.ceil((n-1)*s/t))+1 for n,s,t in zip(canonical.GetSize(),canonical.GetSpacing(),spacing)]
    grid=sitk.Image(size,sitk.sitkInt16);grid.SetOrigin(canonical.GetOrigin());grid.SetDirection(canonical.GetDirection());grid.SetSpacing(spacing)
    return sitk.Resample(canonical,grid,sitk.Transform(),sitk.sitkLinear,-1000,sitk.sitkInt16)


def make_context(ct,z,spacing_z,ys=slice(None),xs=slice(None)):
    x=ct[context_indices(z,len(ct),spacing_z),ys,xs].astype(np.float32)
    return (np.clip(x,-1000,400)+1000)/1400


def largest_airway_component(raw):
    """A fixed, model-mask-only policy; avoids attaching to a wrong CT seed."""
    from scipy import ndimage as ndi
    mask=np.asarray(raw,dtype=bool)
    if not np.any(mask):return np.zeros(mask.shape,np.uint8),{'policy':'largest_26_connected','input_voxels':0,'kept_voxels':0}
    bounds=[]
    for axis in range(3):
        idx=np.flatnonzero(np.any(mask,axis=tuple(a for a in range(3) if a!=axis)))
        bounds.append(slice(int(idx[0]),int(idx[-1])+1))
    region=tuple(bounds);lab,n=ndi.label(mask[region],np.ones((3,3,3),np.uint8))
    counts=np.bincount(lab.ravel());counts[0]=0;selected=int(np.argmax(counts))
    out=np.zeros(mask.shape,np.uint8);out[region]=lab==selected
    return out,{'policy':'largest_26_connected','input_voxels':int(mask.sum()),'kept_voxels':int(counts[selected]),'components':int(n)}
