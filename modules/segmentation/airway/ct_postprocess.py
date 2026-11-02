"""CT segmentation-only postprocessing with bounded component scans."""
import numpy as np
from scipy import ndimage as ndi
from .seed import SeedCandidate


def find_trachea_seed(ct, spacing_xyz, air_hu=-850, min_area_mm2=30, max_area_mm2=1000):
    """Same scoring as the original seed finder; inspect each component's bounding box only."""
    nz,ny,nx=ct.shape;sx,sy,_=spacing_xyz;pixel_area=sx*sy;cx,cy=(nx-1)/2,(ny-1)/2;candidates=[]
    for z in range(max(1,int(.08*nz)),min(nz-1,int(.92*nz))):
        lab,n=ndi.label(ct[z]<=air_hu,structure=np.ones((3,3),np.uint8))
        if not n:continue
        objects=ndi.find_objects(lab);sizes=np.bincount(lab.ravel())
        border=set(np.concatenate([lab[0],lab[-1],lab[:,0],lab[:,-1]]).tolist())
        for idx,obj in enumerate(objects,1):
            area=int(sizes[idx])*pixel_area
            if obj is None or idx in border or not min_area_mm2<=area<=max_area_mm2:continue
            h=max(1,obj[0].stop-obj[0].start);w=max(1,obj[1].stop-obj[1].start);aspect=max(h/w,w/h)
            if aspect>3.2:continue
            yy,xx=np.where(lab[obj]==idx);xx=xx+obj[1].start;yy=yy+obj[0].start
            x=int(round(xx.mean()));y=int(round(yy.mean()))
            score=float(np.hypot((x-cx)*sx,(y-cy)*sy))+9*abs(np.log(max(area,1e-6)/250.0))+7*(aspect-1)
            candidates.append(SeedCandidate(x,y,z,float(score),float(area),float(ct[z,y,x]),0))
    if not candidates:raise RuntimeError('Automatic trachea seed not found')
    for c in candidates:
        pers=sum(abs(o.z-c.z)<=5 and np.hypot(o.x-c.x,o.y-c.y)<=14 for o in candidates)
        c.persistence=int(pers);c.score-=2.2*pers
    candidates.sort(key=lambda c:c.score)
    return candidates[0]


def keep_seed_connected(mask,seed_xyz,spacing_xyz):
    binary=np.asarray(mask,dtype=bool)
    bounds=[]
    for axis in range(3):
        indices=np.flatnonzero(np.any(binary,axis=tuple(i for i in range(3) if i!=axis)))
        if not len(indices):raise RuntimeError('Airway mask is empty')
        bounds.append(slice(int(indices[0]),int(indices[-1])+1))
    region=tuple(bounds);origin=np.array([s.start for s in bounds]);crop=binary[region]
    labels,count=ndi.label(crop,structure=np.ones((3,3,3),np.uint8))
    target=np.array(seed_xyz[::-1],dtype=int)-origin
    selected=int(labels[tuple(target)]) if np.all(target>=0) and np.all(target<crop.shape) else 0
    if selected==0:
        points=np.argwhere(crop);scale=np.array(spacing_xyz[::-1],dtype=float)
        nearest=points[np.argmin(np.sum(((points-target)*scale)**2,axis=1))];selected=int(labels[tuple(nearest)])
    kept=np.zeros(binary.shape,dtype=bool);kept[region]=labels==selected;size=int(kept.sum())
    return kept,{'input_component_count':int(count),'selected_component_label':selected,'kept_voxels':size,
        'removed_voxels':int(binary.sum())-size,'removed_component_count':int(count-1)}
