"""Audit a complete selected polyline using the unchanged verified C4 interface.

This data producer does not load a bitstream or replace an interactive route.
The selected path is represented as a linear graph, so C4 cannot silently choose
a different branch. Its original segment geometry is retained during densifying.
"""
from dataclasses import dataclass,replace
from pathlib import Path
import hashlib,json,sys,time
import numpy as np
from scipy.spatial import cKDTree

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'modules/navigation'))
sys.path.insert(0,str(ROOT/'dfx/route_audit_speed'))
from navigation.planner import Target
from protocol import AuditRoutePlanner,validate_stored_audit
from checked_plan import checked_plan

sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

@dataclass(frozen=True)
class Selection:
    points:np.ndarray
    original_node_ids:np.ndarray
    diameter:float
    margin:float
    bend:float
    binding:dict

def load_selection(context,target,folder,group_index,candidate_id):
    """Bind JSON, complete arrays, raw parent chain, anatomy and target together."""
    folder=Path(folder)
    files=['whole_instrument_profiles.json','whole_alternative_routes.json','whole_comparison_arrays.npz']
    whole,alternatives=[json.loads((folder/n).read_text(encoding='utf-8')) for n in files[:2]]
    common=('schema','input_sha256','centerline_id','target_kind','target_metadata',
        'safety_margin_mm','minimum_bend_radius_mm','source_sha256')
    if any(whole[k]!=alternatives[k] for k in common):raise ValueError('Comparison report pair differs')
    if whole['schema']!='kv260.navigation.raw_comparison.v1':raise ValueError('Wrong comparison schema')
    for name,digest in whole['source_sha256'].items():
        path=(Path(__file__).parent/name).resolve()
        if path.parent!=Path(__file__).parent or sha(path)!=digest:raise ValueError('Producer source changed')
    if (whole['input_sha256']!=context.metadata['input_sha256'] or
        whole['centerline_id']!=context.metadata['centerline_id'] or
        whole['target_kind']!=target.kind or whole['target_metadata']!=target.metadata):
        raise ValueError('Comparison belongs to another anatomy or target')
    groups=alternatives['groups']
    if not isinstance(group_index,int) or not 0<=group_index<len(groups):raise ValueError('Invalid instrument group')
    group=groups[group_index]
    if not isinstance(candidate_id,int) or candidate_id not in [r['candidate_id'] for r in group['pareto']]:
        raise ValueError('Choose one displayed Pareto candidate')
    records=[r for r in group['candidates'] if r['candidate_id']==candidate_id]
    if len(records)!=1:raise ValueError('Ambiguous candidate identity')
    record=records[0];p=np.asarray(record['points_lps_mm'],np.float64)
    radii=np.asarray(record['radius_mm'],np.float64)
    values=[group['scope_diameter_mm'],whole['safety_margin_mm'],whole['minimum_bend_radius_mm']]
    if (p.ndim!=2 or p.shape[1:]!=(3,) or not 2<=len(p)<=4096 or
        radii.shape!=(len(p),) or not np.isfinite(np.r_[p.ravel(),radii,values]).all() or
        min(values)<0 or values[0]<=0 or np.any(radii<0) or
        np.any(np.linalg.norm(np.diff(p,axis=0),axis=1)<=1e-8)):
        raise ValueError('Invalid or degenerate selected polyline')
    with np.load(folder/files[2],allow_pickle=False) as arrays:
        prefix=f'profile_{group_index}_candidate_{candidate_id}_'
        if not np.array_equal(p,arrays[prefix+'path_xyz']) or not np.array_equal(radii,arrays[prefix+'radii']):
            raise ValueError('Displayed path differs from complete comparison arrays')
        raw=arrays['raw_coordinates_zyx'];chain=arrays[prefix+'path_zyx']
        if not np.array_equal(raw,context.indices_zyx-context.offset_zyx):raise ValueError('Raw node ordering differs')
        lookup={tuple(v):i for i,v in enumerate(raw)}
        try:ids=np.asarray([lookup[tuple(v)] for v in chain],np.int32)
        except KeyError as e:raise ValueError('Unknown raw path node') from e
        if (not len(ids) or ids[0]!=context.root or len(set(ids))!=len(ids) or
            not np.array_equal(arrays['parents'][group_index,ids[1:]],ids[:-1]) or
            not np.isfinite(arrays['distances'][group_index,ids]).all()):
            raise ValueError('Selected path does not match complete original parent chain')
        if not np.array_equal(raw[ids[-1]],record['end_zyx']):raise ValueError('Candidate endpoint mismatch')
    p.setflags(write=False);ids.setflags(write=False)
    return Selection(p,ids,*map(float,values),dict(group_index=group_index,candidate_id=candidate_id,
        comparison_files_sha256={n:sha(folder/n) for n in files},
        original_path_sha256=hashlib.sha256(p.astype('<f8',copy=False).tobytes()).hexdigest(),
        input_sha256=whole['input_sha256'],centerline_id=whole['centerline_id'],
        original_raw_parent_chain_retained=True))

def linear_scene(context,selection):
    """Share the original checked EDT field; encode only the selected path edges."""
    p=selection.points;n=len(p)
    root_error=np.linalg.norm(p[0]-context.points_lps_mm[context.root])
    if root_error>1e-7:raise ValueError('Selected polyline starts at a different root')
    radii=context.sample_radius(p).astype(np.float64)
    if not np.isfinite(radii).all() or np.any(radii<0):raise ValueError('Invalid volume radii')
    indices=context.geometry.to_zyx(p)
    identity=hashlib.sha256(p.tobytes()).hexdigest()
    meta=dict(context.metadata,selected_polyline_id=identity)
    return replace(context,indices_zyx=indices,points_lps_mm=p,radii_mm=radii,
        edges=np.column_stack((np.arange(n-1),np.arange(1,n))).astype(np.int32),
        components=np.zeros(n,np.int32),root=0,metadata=meta)

def verify_polyline_prefix(source,route,scene_ids):
    """Require the exact selected start and all retained original vertices.

    The PL can add collinear clearance samples or stop at an unsafe prefix;
    it cannot move an original vertex or choose a different path.
    """
    points=route['points_lps_mm'];ids=np.asarray(scene_ids)
    if not np.array_equal(ids,np.arange(len(ids))):raise ValueError('PL chose a non-prefix path')
    if len(points) and not np.array_equal(points[0],source[0]):raise ValueError('PL changed the path root')
    if not len(ids):
        if len(points):raise ValueError('Points without retained scene IDs')
        return
    # Only scene vertices actually reached by the truncated dense output count.
    cursor=0
    for i in ids:
        while cursor<len(points) and not np.array_equal(points[cursor],source[i]):cursor+=1
        if cursor==len(points):break
        cursor+=1
    segments=np.diff(source[:len(ids)],axis=0)
    if not len(segments):
        if len(points)>1:raise ValueError('Unexpected path after a single-node prefix')
        return
    cursor=0
    for p in points:
        while cursor+1<len(segments) and np.linalg.norm(p-source[cursor+1])<1e-8:cursor+=1
        a=source[cursor];v=segments[cursor];f=float(np.dot(p-a,v)/np.dot(v,v))
        if not -1e-8<=f<=1+1e-8 or np.linalg.norm(p-(a+f*v))>1e-7:
            raise ValueError('PL returned a point outside the selected polyline')
        if f>=1-1e-8 and cursor+1<len(segments):cursor+=1

def audit_selection(context,target,selection,session,*,forward_window_mm=10.,sample_mm=.5):
    """Run continuous field checks, bend audit and camera on the supplied C4 owner."""
    start=time.perf_counter();scene=linear_scene(context,selection)
    planner=AuditRoutePlanner(scene,session)
    endpoint=Target('manual_point',selection.points[-1:].copy(),{})
    report,route,camera=checked_plan(planner,endpoint,minimum_bend_radius_mm=selection.bend,
        scope_diameter_mm=selection.diameter,safety_margin_mm=selection.margin,
        sample_mm=sample_mm,smooth=False,forward_window_mm=forward_window_mm)
    linear_ids=route['centerline_point_ids'].copy()
    verify_polyline_prefix(selection.points,route,linear_ids)
    validate_stored_audit(route,report)
    report.update(target_kind=target.kind,target=target.metadata,selection=selection.binding,
        target_points_lps_mm=target.points_lps_mm.tolist() if target.kind!='lesion_candidate' else [],
        requested_original_endpoint_id=int(selection.original_node_ids[-1]),
        final_target_gap_mm=float(cKDTree(target.points_lps_mm).query(route['points_lps_mm'][-1])[0]) if len(route['arc_mm']) else None,
        selected_path_geometry='original complete polyline; collinear clearance samples and verified prefix only',
        automatic_route_replanning=False,selected_path_linear_scene_ids=linear_ids.tolist(),
        actual_UI_route_replaced=False,branch_guidance_application_pending=True,
        selection_audit_whole_API_seconds=time.perf_counter()-start,pl_scene=planner.scene_info)
    return report,route,camera
