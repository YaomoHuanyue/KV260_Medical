from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np
from scipy import ndimage as ndi

@dataclass
class SeedCandidate:
    x: int
    y: int
    z: int
    score: float
    area_mm2: float
    hu: float
    persistence: int
    def to_dict(self): return asdict(self)

def _touches_border(labels: np.ndarray, idx: int) -> bool:
    return bool(np.any(labels[0] == idx) or np.any(labels[-1] == idx) or np.any(labels[:,0] == idx) or np.any(labels[:,-1] == idx))

def find_trachea_seed(ct: np.ndarray, spacing_xyz: tuple[float,float,float], air_hu: float=-850,
                      min_area_mm2: float=30, max_area_mm2: float=1000) -> SeedCandidate:
    if ct.ndim != 3: raise ValueError("CT must be z,y,x")
    nz, ny, nx = ct.shape
    sx, sy, _ = spacing_xyz
    pixel_area = sx*sy
    cx, cy = (nx-1)/2, (ny-1)/2
    candidates=[]
    # broad range makes this robust to superior-inferior array orientation
    for z in range(max(1,int(.08*nz)), min(nz-1,int(.92*nz))):
        air = ct[z] <= air_hu
        lab, n = ndi.label(air, structure=np.ones((3,3), np.uint8))
        if not n: continue
        objs=ndi.find_objects(lab)
        for idx,obj in enumerate(objs,1):
            if obj is None or _touches_border(lab,idx): continue
            yy,xx=np.where(lab==idx)
            area=len(xx)*pixel_area
            if not (min_area_mm2<=area<=max_area_mm2): continue
            x=int(round(xx.mean())); y=int(round(yy.mean()))
            h=max(1,obj[0].stop-obj[0].start); w=max(1,obj[1].stop-obj[1].start)
            aspect=max(h/w,w/h)
            if aspect>3.2: continue
            center_mm=float(np.hypot((x-cx)*sx,(y-cy)*sy))
            area_penalty=abs(np.log(max(area,1e-6)/250.0))
            score=center_mm + 9*area_penalty + 7*(aspect-1)
            candidates.append([SeedCandidate(x,y,z,float(score),float(area),float(ct[z,y,x]),0), xx, yy])
    if not candidates:
        raise RuntimeError("Automatic trachea seed not found. Use inspect_ct.py and pass --seed x,y,z.")
    # Reward persistence on neighboring slices near the same x/y location.
    basic=[c[0] for c in candidates]
    for item in candidates:
        c=item[0]
        pers=sum(abs(o.z-c.z)<=5 and np.hypot(o.x-c.x,o.y-c.y)<=14 for o in basic)
        c.persistence=int(pers)
        c.score-=2.2*pers
    candidates.sort(key=lambda item:item[0].score)
    return candidates[0][0]
