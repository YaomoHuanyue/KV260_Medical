from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Iterable
import numpy as np
from scipy import ndimage as ndi

@dataclass
class GrowthStep:
    upper_hu: int
    voxels: int
    volume_ml: float
    growth_ratio: float
    border_fraction: float
    leaked: bool
    reason: str
    def to_dict(self): return asdict(self)

@dataclass
class SegmentationResult:
    mask: np.ndarray
    selected_upper_hu: int
    steps: list[GrowthStep]

def _border_fraction(mask):
    total=int(mask.sum())
    if total==0:return 0.0
    b=np.zeros_like(mask,bool); b[[0,-1],:,:]=True; b[:,[0,-1],:]=True; b[:,:,[0,-1]]=True
    return float((mask & b).sum()/total)

def _connected_from_seed(candidate: np.ndarray, seed_xyz: tuple[int,int,int]) -> np.ndarray:
    x,y,z=map(int,seed_xyz)
    if not (0<=z<candidate.shape[0] and 0<=y<candidate.shape[1] and 0<=x<candidate.shape[2]):
        raise ValueError(f"Seed {seed_xyz} outside volume")
    if not candidate[z,y,x]:
        return np.zeros_like(candidate,bool)
    marker=np.zeros_like(candidate,bool); marker[z,y,x]=True
    structure=ndi.generate_binary_structure(3,1)  # 6-connected / face connectivity
    return ndi.binary_propagation(marker, structure=structure, mask=candidate)

def segment_airway_adaptive(ct: np.ndarray, spacing_xyz: tuple[float,float,float], seed_xyz: tuple[int,int,int],
                            lower_hu: int=-1050, upper_candidates: Iterable[int]=range(-950,-624,25),
                            min_volume_for_growth_check_ml: float=2.0, growth_ratio_limit: float=2.2,
                            absolute_volume_limit_ml: float=350.0, border_fraction_limit: float=0.02) -> SegmentationResult:
    voxel_ml=float(np.prod(spacing_xyz)/1000.0)
    previous=None; previous_vol=0.0; previous_upper=None; steps=[]
    for upper in upper_candidates:
        candidate=(ct>=lower_hu)&(ct<=upper)
        mask=_connected_from_seed(candidate,seed_xyz)
        vox=int(mask.sum()); vol=vox*voxel_ml
        ratio=vol/previous_vol if previous_vol>0 else 1.0
        border=_border_fraction(mask)
        reasons=[]
        if vol>absolute_volume_limit_ml: reasons.append("absolute-volume")
        if previous_vol>=min_volume_for_growth_check_ml and ratio>growth_ratio_limit: reasons.append("sudden-growth")
        if vol>5 and border>border_fraction_limit: reasons.append("border-contact")
        leaked=bool(reasons)
        steps.append(GrowthStep(int(upper),vox,float(vol),float(ratio),float(border),leaked,",".join(reasons)))
        if leaked and previous is not None:
            return SegmentationResult(previous,int(previous_upper),steps)
        if vox>0:
            previous=mask.copy(); previous_vol=vol; previous_upper=int(upper)
    if previous is None or previous_upper is None:
        raise RuntimeError("No connected airway candidate produced. Check the seed and HU range.")
    return SegmentationResult(previous,int(previous_upper),steps)
