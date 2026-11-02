"""Original all-reachable-node route candidates from checked PS or PL profiles."""
import math
import numpy as np
from scipy.spatial import cKDTree
from path_rules_r1 import (zyx_to_phys,resample_polyline,smooth_route_constrained,
    route_clearance_mm,route_curvature,turn_cost)
from pareto_r1 import select


def candidates(graph,image,radius_volume,lesion_points,distances,parents,
    scope_diameter_mm,safety_margin_mm=.2,gap_weight=8.,bend_weight=8.,
    candidate_slack_mm=4.,path_sample_mm=.8,minimum_bend_radius_mm=0.):
    """Use all reachable nodes, retain original 80 candidates and Pareto 8.

    Profiles are caller supplied; this routine neither loads a bitstream nor
    substitutes a graph of leaves. Every path is recomputed for the target.
    """
    coords=graph.coordinates_zyx
    distances=np.asarray(distances,dtype=np.float64)
    parents=np.asarray(parents)
    radius=np.asarray(radius_volume)
    lesion=np.asarray(lesion_points,dtype=np.float64)
    parameters=(scope_diameter_mm,safety_margin_mm,gap_weight,bend_weight,
        candidate_slack_mm,path_sample_mm,minimum_bend_radius_mm)
    if not all(math.isfinite(float(v)) and float(v)>=0 for v in parameters):
        raise ValueError('Nonfinite or negative physical route parameter')
    if scope_diameter_mm<=0 or path_sample_mm<=0:
        raise ValueError('Positive scope diameter and path sample spacing required')
    if distances.shape!=(len(coords),) or parents.shape!=distances.shape or not np.issubdtype(parents.dtype,np.integer):
        raise ValueError('Complete raw-node distance and parent arrays required')
    if np.isnan(distances).any() or (distances<0).any() or not np.isfinite(distances[graph.root]):
        raise ValueError('Invalid original root costs')
    if radius.ndim!=3 or tuple(radius.shape[::-1])!=tuple(image.GetSize()):
        raise ValueError('Full radius volume and image geometry must agree')
    if np.any(coords<0) or np.any(coords>=np.asarray(radius.shape)):
        raise ValueError('Raw node outside the radius volume')
    if lesion.ndim!=2 or lesion.shape[1:]!=(3,) or not len(lesion) or not np.isfinite(lesion).all():
        raise ValueError('Nonempty finite target surface required')
    ids=np.flatnonzero(np.isfinite(distances))
    # Complete raw parent linkage is checked once, rather than issuing a
    # NumPy neighbor search at every step of every candidate backtrack.
    nonroot=ids[ids!=graph.root]
    prior=parents[nonroot]
    if np.any(prior<0) or np.any(prior>=len(coords)) or not np.isfinite(distances[prior]).all():
        raise ValueError('Invalid connected raw-node parent chain')
    sources=np.repeat(np.arange(len(coords)),np.diff(graph.rows.astype(np.int64)))
    child=graph.neighbors
    present=np.zeros(len(coords),dtype=bool)
    present[child[parents[child]==sources]]=True
    if not present[nonroot].all():
        raise ValueError('Parent link is absent from the unchanged raw graph')
    parent_ids=parents.tolist()
    points=zyx_to_phys(coords[ids].astype(float),image)
    gaps=cKDTree(lesion).query(points,k=1)[0]
    minimum_gap=float(np.min(gaps))
    eligible_ids=np.flatnonzero(gaps<=minimum_gap+float(candidate_slack_mm))
    if len(eligible_ids)>80:
        eligible_ids=eligible_ids[np.argsort(gaps[eligible_ids])[:80]]
    records=[]
    for local in eligible_ids:
        node=int(ids[local]);chain=[node]
        while chain[-1]!=graph.root:
            if len(chain)>len(coords):
                raise ValueError('Invalid connected raw-node parent cycle')
            chain.append(parent_ids[chain[-1]])
        chain.reverse()
        path_zyx=coords[chain].astype(int)
        raw_path=zyx_to_phys(path_zyx.astype(float),image)
        raw_radii=radius[tuple(path_zyx.T)]
        path=resample_polyline(raw_path,sample_mm=path_sample_mm)
        _,nearest=cKDTree(raw_path).query(path,k=1)
        path=smooth_route_constrained(path,raw_radii[nearest])
        radii=route_clearance_mm(path,radius,image)
        bend=turn_cost(path)
        length=float(np.linalg.norm(np.diff(path,axis=0),axis=1).sum())
        minimum_diameter=2.*float(np.min(radii))
        _,bend_radius=route_curvature(path)
        score=float(distances[node])+float(gap_weight)*float(gaps[local])+float(bend_weight)*bend
        records.append(dict(end=tuple(int(v) for v in coords[node]),path_zyx=path_zyx,
            path_xyz=path,radii=radii,gap_mm=float(gaps[local]),bend_radians=float(bend),
            path_length_mm=length,minimum_diameter_mm=minimum_diameter,
            minimum_bend_radius_mm=bend_radius,endpoint_xyz_mm=[float(v) for v in points[local]],score=float(score)))
    if not records:
        raise RuntimeError('No connected airway route to the lesion vicinity was found.')
    required=float(scope_diameter_mm)+2.*float(safety_margin_mm)
    eligible=[r for r in records if r['minimum_diameter_mm']+1e-6>=required and
        (float(minimum_bend_radius_mm)<=0. or r['minimum_bend_radius_mm']+1e-6>=float(minimum_bend_radius_mm))]
    chosen=min(eligible or records,key=lambda r:r['score'])
    return records,chosen,select(records)
