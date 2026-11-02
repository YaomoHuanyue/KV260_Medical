"""Audit the selected complete polyline on the current wall, never another branch."""
from dataclasses import replace
import copy,json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from modules.surface_route.bundle_r8 import arrays,sha,canonical,digest
from modules.surface_route.comparison_r11 import MemoWall
from modules.surface_route.bend_replan_r3 import SurfaceBendPlanner,checked_replan,validate_stored_audit
from modules.navigation.navigation.planner import Target,densify
from modules.navigation_comparison.path_rules_r1 import resample_polyline,smooth_route_constrained


def arc(points):return np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]


def selected_source(comp,folder,group,candidate):
    folder=Path(folder);names=['whole_instrument_profiles.json','whole_alternative_routes.json','whole_comparison_arrays.npz']
    whole,alt=[json.loads((folder/n).read_text(encoding='utf-8')) for n in names[:2]]
    if whole['schema']!='kv260.surface_route.comparison.v1' or whole['binding']!=alt['binding']:
        raise ValueError('Current-surface comparison pair required')
    for key in ('scalar_sha256','mesh_sha256','CT_input_sha256','centerline_id','source_files_sha256'):
        if whole['binding'][key]!=comp.binding[key]:raise ValueError('Comparison belongs to another anatomy/surface: '+key)
    if whole['binding']['target']!=comp.target.metadata:raise ValueError('Comparison belongs to another target')
    if type(group)!=int or not 0<=group<len(alt['groups']):raise ValueError('Invalid instrument group')
    g=alt['groups'][group]
    if type(candidate)!=int or candidate not in [v['candidate_id'] for v in g['pareto']]:
        raise ValueError('Choose a displayed Pareto candidate')
    selected=[v for v in g['candidates'] if v['candidate_id']==candidate]
    if len(selected)!=1:raise ValueError('Ambiguous candidate')
    row=selected[0];saved=arrays(folder/names[2]);prefix=f'profile_{group}_candidate_{candidate}_'
    p=np.asarray(row['points_lps_mm'],np.float64);ids=np.asarray(row['original_parent_node_ids'])
    if (not 1<=len(p)<=4096 or p.shape!=(len(p),3) or not np.isfinite(p).all()
            or ids.ndim!=1 or ids.dtype.kind not in 'iu' or not len(ids)
            or ids[0]!=comp.c.root or len(np.unique(ids))!=len(ids)
            or np.any(ids<0) or np.any(ids>=len(comp.c.points_lps_mm))
            or not np.array_equal(saved['raw_coordinates_zyx'],comp.raw.coordinates_zyx)
            or not np.array_equal(saved['parents'][group,ids[1:]],ids[:-1])
            or not np.isfinite(saved['distances'][group,ids]).all()
            or not np.array_equal(saved[prefix+'path_zyx'],comp.raw.coordinates_zyx[ids])
            or int(row['endpoint_id'])!=int(ids[-1])
            or not np.array_equal(saved[prefix+'path_xyz'],p)
            or not np.array_equal(saved[prefix+'radii'],row['radius_mm'])):
        raise ValueError('Selected curve/raw chain differs from complete comparison arrays')
    raw=comp.c.points_lps_mm[ids]
    raw_arc=arc(raw)
    if row['unsafe_original_smoothing_replaced_by_reviewed_raw_path']:
        step=min(.5,min(comp.c.geometry.spacing_xyz)*.25)
        expected=densify(raw,step);u=[]
        for i,(a,b) in enumerate(zip(raw[:-1],raw[1:])):
            count=max(1,int(np.ceil(np.linalg.norm(b-a)/step)))
            u.extend((raw_arc[i]+np.arange(count)/count*(raw_arc[i+1]-raw_arc[i])).tolist())
        parameter=np.r_[u,raw_arc[-1]]
    else:
        base=resample_polyline(raw,.8)
        if len(raw)<=2:parameter=raw_arc.copy()
        else:
            parameter=np.arange(0.,raw_arc[-1]+.8*.5,.8);parameter[-1]=raw_arc[-1]
        _,nearest=cKDTree(raw).query(base)
        expected=smooth_route_constrained(base,saved['node_adjusted_radius_mm'][ids[nearest]])
    if not np.array_equal(expected,p) or len(parameter)!=len(p) or np.any(np.diff(parameter)<=0):
        raise ValueError('Cannot prove retained physical source parameter for selected curve')
    options=dict(scope_diameter_mm=float(g['scope_diameter_mm']),safety_margin_mm=float(whole['safety_margin_mm']),
                 minimum_bend_radius_mm=float(whole['minimum_bend_radius_mm']))
    if not np.isfinite(list(options.values())).all() or min(options.values())<0 or options['scope_diameter_mm']<=0:
        raise ValueError('Invalid selected instrument constraints')
    binding=dict(group_index=group,candidate_id=candidate,comparison_files_sha256={n:sha(folder/n) for n in names},
        original_path_sha256=digest(np.ascontiguousarray(p,dtype='<f8').tobytes()),
        original_raw_parent_chain_retained=True,target=comp.target.metadata,
        source_parameter_policy='exact original resample/densify parameter retained through the original constrained smoothing')
    return p,ids,parameter,options,binding


def forest_for_path(comp,ids):
    c=comp.c;original={tuple(sorted(map(int,e))) for e in c.edges}
    raw={tuple(map(int,e)) for e in comp.edges}
    required=[tuple(sorted(map(int,e))) for e in zip(ids[:-1],ids[1:])]
    if any(e not in raw for e in required) or not original<=raw:raise ValueError('Unknown original graph edge')
    if all(e in original for e in required):return c,dict(changed=False,removed_edges=[],added_edges=[])
    parent=np.arange(len(c.points_lps_mm));retained=[]
    def find(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    for a,b in required+sorted(original)+sorted(raw-original):
        x,y=find(a),find(b)
        if x!=y:parent[y]=x;retained.append((a,b))
    final=set(retained)
    if not set(required)<=final:raise ValueError('Selected branch chain contains a cycle')
    labels=np.asarray([find(i) for i in range(len(parent))]);_,labels=np.unique(labels,return_inverse=True)
    if len(final)!=len(parent)-len(np.unique(labels)):raise ValueError('Invalid selected guidance forest')
    derived=replace(c,edges=np.asarray(sorted(final),np.int32),components=labels.astype(np.int32))
    return derived,dict(changed=True,removed_edges=sorted(original-final),added_edges=sorted(final-original),
        rule='selected original raw path first, then original forest edges; all components and node IDs retained',
        original_case_files_or_mask_modified=False)


def selected_node_arcs(c,route):
    """Full physical source parameter, including a selected-curve partial prefix."""
    p=np.asarray(route['points_lps_mm']);a=np.asarray(route['arc_mm'])
    ref=np.asarray(route['guidance_reference_points_lps_mm']);ra=np.asarray(route['guidance_reference_arc_mm'])
    full=np.asarray(route['guidance_reference_node_ids']);ids=np.asarray(route['centerline_point_ids'])
    u=np.asarray(route['guidance_source_parameter_mm'])
    if (not len(p) or p.shape!=(len(p),3) or a.shape!=(len(p),) or u.shape!=a.shape
            or ids.ndim!=1 or ids.dtype.kind not in 'iu' or not len(ids)
            or full.ndim!=1 or not len(full) or full.dtype.kind not in 'iu' or full[0]!=c.root
            or full.min()<0 or full.max()>=len(c.points_lps_mm) or len(np.unique(full))!=len(full)
            or not np.array_equal(ref,c.points_lps_mm[full]) or ra.shape!=(len(ref),)
            or not np.allclose(ra,arc(ref),rtol=0,atol=1e-9)
            or not np.allclose(a,arc(p),rtol=0,atol=1e-9)
            or not np.isfinite(np.r_[p.ravel(),a,u,ra]).all()
            or a[0]!=0 or u[0]!=0 or u[-1]>ra[-1]+1e-9 or np.any(np.diff(u)<=0)
            or np.any(np.diff(a)<=0) or np.any(np.diff(ra)<=0)
            or not np.array_equal(p[0],ref[0])
            or not np.array_equal(ids,full[ra<=u[-1]+1e-9])):
        raise ValueError('Changed selected physical source correspondence')
    edges={frozenset(map(int,e)) for e in c.edges}
    if any(frozenset(map(int,e)) not in edges for e in zip(full[:-1],full[1:])):
        raise ValueError('Selected reference path differs from the guidance forest')
    mapped=np.interp(ra[:len(ids)],u,a)
    if np.any(np.diff(mapped)<=0):raise ValueError('Selected source nodes collapsed in the curve')
    return mapped,dict(source_node_count=len(ids),mapping='retained exact producer source parameter, restricted to audited selected prefix',
        original_node_reference_arcs_mm=ra[:len(ids)].tolist(),unreached_source_nodes_omitted=len(full)-len(ids))


def audit_selected(comp,folder,group,candidate,*,auditor=None):
    p,ids,parameter,options,binding=selected_source(comp,folder,group,candidate)
    c=comp.c;n=len(p)
    linear=replace(c,indices_zyx=c.geometry.to_zyx(p),points_lps_mm=p,radii_mm=np.zeros(n,np.float32),
        edges=np.column_stack((np.arange(n-1),np.arange(1,n))).astype(np.int32),components=np.zeros(n,np.int32),root=0)
    planner=SurfaceBendPlanner(linear,comp.region,MemoWall(comp.base),auditor=auditor)
    report,route,camera=checked_replan(planner,Target('manual_point',p[-1:],{}),**options,smooth=False)
    linear_ids=route['centerline_point_ids'].copy()
    if not np.array_equal(linear_ids,np.arange(len(linear_ids))):raise ValueError('Selected path was replanned')
    from modules.navigation_comparison.selected_path_r1 import verify_polyline_prefix
    verify_polyline_prefix(p,route,linear_ids)
    if not len(route['points_lps_mm']):raise ValueError('Selected root is not inside the active surface')
    if np.any(comp.field.sample(route['points_lps_mm'])<=0):raise ValueError('Selected prefix left the active scalar')
    u=np.interp(route['arc_mm'],arc(p),parameter);u[0]=0.
    if np.array_equal(route['points_lps_mm'][-1],p[-1]):u[-1]=parameter[-1]
    ref=c.points_lps_mm[ids];ra=arc(ref)
    route.update(centerline_point_ids=ids[ra<=u[-1]+1e-9],guidance_reference_points_lps_mm=ref,
        guidance_reference_arc_mm=ra,guidance_reference_node_ids=ids,guidance_source_parameter_mm=u)
    guidance_context,forest=forest_for_path(comp,ids)
    selected_node_arcs(guidance_context,route)
    report.update(target_kind=comp.target.kind,target=comp.target.metadata,selection=binding,
        requested_endpoint_id=int(ids[-1]),selected_endpoint_id=None,
        selected_endpoint_identity='audited prefix point on selected complete polyline',
        final_target_gap_mm=float(cKDTree(comp.target.points_lps_mm).query(route['points_lps_mm'][-1])[0]),
        automatic_route_replanning=False,selected_path_geometry='complete selected polyline or original audited prefix; no branch substitution',
        branch_guidance_application_pending=True,guidance_forest=forest,
        branch_guidance_and_current_complete_UI_integration_pending=True)
    if not report['reason']:report['status']='airway_approach' if comp.target.kind=='lesion_candidate' else 'route_found'
    validate_stored_audit(route,report)
    return report,route,camera,guidance_context
