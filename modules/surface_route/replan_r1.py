"""Replan on the original forest, reviewing every edge on replacement PL walls.

Target choice, physical edge weighting, bounded smoothing and camera pose rule
come from the accepted navigation sources. This is an independent candidate,
not a route-file overwrite or a claim of whole-feature UI integration.
"""
from time import perf_counter
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree
from .audit import _points
from .refine_r1 import _query, refine_segments


def mask_segments_inside(centerline, points, *, segments=None, maximum_tests=200000):
    """Check all open voxel intervals of each straight segment, plus endpoints.

    Dense point membership alone can skip a very short background interval.
    Orthogonal image coordinates make every cell transition a half-integer
    crossing, so partitioning at all such crossings is complete for a segment.
    """
    p = _points(points,nonempty=False)
    if segments is None:
        segments=np.column_stack((np.arange(max(0,len(p)-1)),np.arange(1,len(p))))
    segments=np.asarray(segments)
    if (segments.ndim!=2 or segments.shape[1]!=2 or segments.dtype.kind not in 'iu'
            or (len(segments) and (segments.min()<0 or segments.max()>=len(p)))):
        raise ValueError('Valid mask segment indices required')
    if not len(segments):return np.empty(0,bool)
    q = centerline.geometry.to_zyx(p)-centerline.offset_zyx
    checks=[];owners=[]
    for i,(ia,ib) in enumerate(segments):
        a,b=q[ia],q[ib]
        cuts=[0.,1.]
        for x,y in zip(a,b):
            if x == y:continue
            first=int(np.ceil(min(x,y)-.5));last=int(np.floor(max(x,y)-.5))
            if last-first+1 > maximum_tests:
                raise ValueError('Mask traversal exceeds explicit test budget')
            t=(np.arange(first,last+1,dtype=float)+.5-x)/(y-x)
            cuts.extend(t[(t>0)&(t<1)].tolist())
        cuts=np.unique(cuts)
        fractions=np.r_[0.,.5*(cuts[:-1]+cuts[1:]),1.]
        checks.append(p[ia]+fractions[:,None]*(p[ib]-p[ia]));owners.extend([i]*len(fractions))
        if len(owners)>maximum_tests:raise ValueError('Mask traversal exceeds explicit test budget')
    membership=centerline.inside(np.vstack(checks))
    result=np.ones(len(segments),bool)
    result[np.asarray(owners,np.int64)[~membership]]=False
    return result


def review_curve(centerline, region, oracle, points, threshold):
    p=_points(points,nonempty=False)
    if not len(p):
        return False,{},dict(points_lps_mm=p,wall_distance_mm=np.empty(0),effective_distance_mm=np.empty(0))
    distance=_query(oracle,p)
    effective=np.minimum(distance,region.crop_clearance(p))
    edges=np.column_stack((np.arange(len(p)-1),np.arange(1,len(p)))).astype(np.int32)
    report,arrays=refine_segments(region,p,edges,distance,oracle,threshold_mm=threshold)
    membership=mask_segments_inside(centerline,p)
    root=region.root_winding(p[0])
    accepted=(root['inside_unit_winding_region'] and np.all(centerline.inside(p))
        and np.all(effective-1e-6>=threshold) and np.all(arrays['accepted']) and np.all(membership))
    report.update(root_winding=root,source_mask_segments_passed=bool(np.all(membership)),
                  whole_curve_accepted=bool(accepted))
    arrays.update(points_lps_mm=p,wall_distance_mm=distance,effective_distance_mm=effective,
                  source_mask_segment_inside=membership)
    return bool(accepted),report,arrays


def replan(centerline,target,region,oracle,*,scope_diameter_mm=1.,safety_margin_mm=.2,
           sample_mm=.5,narrow_weight=2.,smooth=True,minimum_bend_radius_mm=0.):
    start=perf_counter()
    c=centerline
    options=np.array([scope_diameter_mm,safety_margin_mm,sample_mm,narrow_weight,minimum_bend_radius_mm],float)
    if not np.isfinite(options).all() or np.any(options<0) or sample_mm<=0:
        raise ValueError('Finite nonnegative constraints and positive sample step required')
    if minimum_bend_radius_mm != 0:
        raise NotImplementedError('New-surface integration of the accepted bend-prefix policy remains pending; constraint is never ignored')
    p=_points(c.points_lps_mm)
    edges=np.asarray(c.edges)
    if (edges.ndim!=2 or edges.shape[1]!=2 or edges.dtype.kind not in 'iu'
            or (len(edges) and (edges.min()<0 or edges.max()>=len(p)))
            or np.any(edges[:,0]==edges[:,1])
            or len(np.unique(np.sort(edges,axis=1),axis=0))!=len(edges)
            or not 0<=c.root<len(p)):
        raise ValueError('Valid original forest with unique edges required')
    graph=c.adjacency()
    count,components=connected_components(graph,directed=False)
    if len(edges)!=len(p)-count:raise ValueError('Original branch forest required; never silently remove cycles')
    from modules.navigation.navigation.planner import densify,_path
    from modules.navigation.navigation.camera import poses
    required=scope_diameter_mm*.5+safety_margin_mm
    resolution=c.resolution_margin_mm if required>0 else 0.
    threshold=required+resolution
    node_wall=_query(oracle,p)
    effective=np.minimum(node_wall,region.crop_clearance(p))
    edge_report,edge_arrays=refine_segments(region,p,edges,node_wall,oracle,threshold_mm=threshold)
    # Original forest edges join original adjacent foreground voxel centres.
    # Still verify all source-mask intervals instead of relying on this fact.
    mask_good=mask_segments_inside(c,p,segments=edges)
    allowed=edge_arrays['accepted']&mask_good
    root_winding=region.root_winding(p[c.root])
    root_good=(root_winding['inside_unit_winding_region'] and c.inside(p[[c.root]])[0]
               and effective[c.root]-1e-6>=threshold)
    adjusted=np.maximum(0.,effective-resolution)
    length=np.linalg.norm(p[edges[:,0]]-p[edges[:,1]],axis=1)
    clearance=np.minimum(adjusted[edges[:,0]],adjusted[edges[:,1]])
    # Exactly the accepted original planner's weighting formula. Profile-only
    # Dijkstra has a different formula and must not be substituted to fit PL.
    weight=length*(1+narrow_weight*(required/(clearance+min(c.geometry.spacing_xyz)))**2)
    e=edges[allowed];w=weight[allowed]
    filtered=coo_matrix((np.r_[w,w],(np.r_[e[:,0],e[:,1]],np.r_[e[:,1],e[:,0]])),shape=graph.shape).tocsr()
    target_points=_points(target.points_lps_mm)
    tree=cKDTree(target_points);gaps=tree.query(p)[0];desired=int(gaps.argmin())
    if target.kind=='manual_point' and gaps[desired]>5:
        raise ValueError('Manual target is more than 5 mm from the original centerline')
    cost,parent=dijkstra(filtered,indices=c.root,directed=False,return_predecessors=True)
    if not root_good:cost[:]=np.inf
    reachable=np.flatnonzero(np.isfinite(cost))
    reason=None
    if components[desired]!=components[c.root]:reason='disconnected_target_component'
    elif not root_good:reason='insufficient_new_surface_root_clearance'
    elif not np.isfinite(cost[desired]):reason='insufficient_new_surface_route_clearance'
    end=desired if reason is None else (int(reachable[gaps[reachable].argmin()]) if len(reachable) else None)
    ids=_path(parent,c.root,end) if end is not None else []
    step=min(float(sample_mm),min(c.geometry.spacing_xyz)*.25)
    points=densify(p[ids],step)
    if len(points)>4096:raise ValueError('New route exceeds original 4096-point capacity; no silent downsampling')
    accepted,curve_report,curve_arrays=review_curve(c,region,oracle,points,threshold)
    if len(points) and not accepted:raise RuntimeError('Selected graph route failed independent whole-curve review')
    smoothing_accepted=False;smoothing_report=None
    if smooth and len(points)>2:
        candidate=points.copy()
        for _ in range(8):
            candidate[1:-1]+=.2*(.5*(candidate[:-2]+candidate[2:])-candidate[1:-1])
            delta=candidate-points;size=np.linalg.norm(delta,axis=1)
            limit=min(c.geometry.spacing_xyz)*.15
            candidate=points+delta*np.minimum(1,limit/np.maximum(size,1e-12))[:,None]
        candidate=densify(candidate,step)
        if len(candidate)>4096:raise ValueError('Smoothed route exceeds original capacity')
        valid,smoothing_report,smoothed_arrays=review_curve(c,region,oracle,candidate,threshold)
        if valid:
            points=candidate;curve_report=smoothing_report;curve_arrays=smoothed_arrays;smoothing_accepted=True
    arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))] if len(points) else np.empty(0)
    camera=poses(points,arc)
    route=dict(points_lps_mm=points,arc_mm=arc,radius_mm=curve_arrays['wall_distance_mm'],
               centerline_point_ids=np.asarray(ids,np.int32))
    state=('limited_reach' if len(points)>1 else 'unreachable') if reason else (
        'airway_approach' if target.kind=='lesion_candidate' else 'route_found')
    report=dict(schema='kv260.surface_route.replanned.v1',status=state,reason=reason,
        backend='PS_source_forest_exact_triangle_wall_review_and_original_weighted_Dijkstra',
        target_kind=target.kind,target=target.metadata,requested_endpoint_id=desired,selected_endpoint_id=end,
        reachable_centerline_points=len(reachable),total_centerline_points=len(p),
        original_edges=len(edges),accepted_edges=int(allowed.sum()),source_mask_edges_rejected=int((~mask_good).sum()),
        scope_diameter_mm=float(scope_diameter_mm),safety_margin_mm=float(safety_margin_mm),
        required_radius_mm=float(required),resolution_margin_mm=float(resolution),
        minimum_bend_radius_mm=0.,nonzero_bend_prefix_policy_integration_pending=True,
        length_mm=float(arc[-1]) if len(arc) else 0.,point_count=len(points),
        minimum_wall_distance_mm=float(route['radius_mm'].min()) if len(points) else None,
        closest_centerline_gap_mm=float(gaps[desired]),
        final_target_gap_mm=float(tree.query(points[-1])[0]) if len(points) else None,
        edge_audit=edge_report,curve_audit=curve_report,smoothing_accepted=smoothing_accepted,
        rejected_smoothing_audit=smoothing_report if not smoothing_accepted else None,
        root_winding=root_winding,radius_semantics='actual PL triangle wall distance, physical LPS mm',
        source_graph_edges_or_mask_changed=False,new_graph_is_constraint_filtered_original_forest=True,
        graph_cycles_removed_in_this_module=0,synthetic_bridge_edges=0,PS_Marching_Cubes_used=False,
        source_route_overwritten=False,new_camera_generated_from_new_route=True,
        branch_guidance_and_current_complete_UI_integration_pending=True,
        clinical_safety_certified=False,production_promoted=False,
        runtime_seconds=perf_counter()-start)
    diagnostics=dict(node_wall_distance_mm=node_wall,node_effective_distance_mm=effective,
        allowed_edges=allowed,all_costs=cost,all_parents=parent,edge_audit=edge_arrays,curve_audit=curve_arrays)
    return report,route,camera,diagnostics
