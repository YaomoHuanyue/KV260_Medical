"""Bounded breadth-first refinement of uncertain actual-wall edge bounds."""
from time import perf_counter
import numpy as np
from .audit import _points

# Labels describe why a bound was not accepted, not a clinical collision test.
PASSED, ENDPOINT, INTERIOR, UNRESOLVED, BUDGET = range(5)


def _query(oracle, points):
    p = _points(points)
    blocks = []
    for at in range(0, len(p), 4096):
        result = oracle.distance(p[at:at+4096])[0]
        d = np.asarray(result, np.float64)
        if d.shape != (min(4096, len(p)-at),) or not np.isfinite(d).all() or np.any(d < 0):
            raise ValueError('Wall oracle returned invalid physical distances')
        blocks.append(d)
    return np.concatenate(blocks)


def refine_segments(region, points, edges, node_wall_mm, oracle, *, threshold_mm,
                    numerical_guard_mm=1e-6, maximum_depth=12,
                    minimum_length_mm=1e-3, query_budget=40000):
    start = perf_counter()
    p = _points(points)
    edges = np.asarray(edges)
    wall = np.asarray(node_wall_mm, np.float64)
    if (edges.ndim != 2 or edges.shape[1] != 2 or edges.dtype.kind not in 'iu'
            or (len(edges) and (edges.min() < 0 or edges.max() >= len(p)))
            or wall.shape != (len(p),) or not np.isfinite(wall).all() or np.any(wall < 0)):
        raise ValueError('Matched physical nodes, indexed segments and wall distances required')
    if (not np.isfinite([threshold_mm,numerical_guard_mm,minimum_length_mm]).all()
            or threshold_mm < 0 or numerical_guard_mm <= 0 or minimum_length_mm <= 0
            or type(maximum_depth) is not int or not 0 <= maximum_depth <= 24
            or type(query_budget) is not int or not 0 <= query_budget <= 1_000_000):
        raise ValueError('Finite thresholds and bounded integer refinement limits required')
    edges = edges.astype(np.int64)
    effective = np.minimum(wall, region.crop_clearance(p))
    state = np.full(len(edges), -1, np.int8)
    lower = np.full(len(edges), np.inf)
    witness = np.full((len(edges),3), np.nan)
    witness_distance = np.full(len(edges), np.nan)
    bad = effective-numerical_guard_mm < threshold_mm
    endpoint_bad = np.any(bad[edges],axis=1)
    state[endpoint_bad] = ENDPOINT
    for i in np.flatnonzero(endpoint_bad):
        node = edges[i, int(np.argmin(effective[edges[i]]))]
        witness[i] = p[node]; witness_distance[i] = effective[node]
    ids = np.flatnonzero(~endpoint_bad)
    a,b = p[edges[ids,0]],p[edges[ids,1]]
    da,db = effective[edges[ids,0]],effective[edges[ids,1]]
    depths = np.zeros(len(ids),np.int16)
    queries = 0; rounds = 0; accepted_leaves = 0; peak_cells = len(ids)
    query_points=[];query_distances=[]
    while len(ids):
        keep = state[ids] == -1
        ids,a,b,da,db,depths = [v[keep] for v in (ids,a,b,da,db,depths)]
        if not len(ids):break
        length = np.linalg.norm(b-a,axis=1)
        bound = np.minimum(np.minimum(da,db),.5*(da+db-length))-numerical_guard_mm
        good = bound >= threshold_mm
        np.minimum.at(lower, ids[good], bound[good])
        accepted_leaves += int(good.sum())
        ids,a,b,da,db,depths,length = [v[~good] for v in (ids,a,b,da,db,depths,length)]
        if not len(ids):break
        stopped = (depths >= maximum_depth) | (length <= minimum_length_mm)
        state[ids[stopped]] = UNRESOLVED
        ids,a,b,da,db,depths = [v[~stopped] for v in (ids,a,b,da,db,depths)]
        keep = state[ids] == -1
        ids,a,b,da,db,depths = [v[keep] for v in (ids,a,b,da,db,depths)]
        if not len(ids):break
        if len(ids) > query_budget-queries:
            state[ids] = BUDGET
            break
        middle = .5*(a+b)
        mid_wall = _query(oracle,middle)
        dm = np.minimum(mid_wall,region.crop_clearance(middle))
        query_points.append(middle);query_distances.append(mid_wall)
        queries += len(ids);rounds += 1
        failed = dm-numerical_guard_mm < threshold_mm
        for index in np.flatnonzero(failed):
            edge = ids[index]
            if state[edge] == -1:
                state[edge] = INTERIOR
                witness[edge] = middle[index];witness_distance[edge] = dm[index]
        keep = state[ids] == -1
        ids,a,b,da,db,depths,middle,dm = [v[keep] for v in (ids,a,b,da,db,depths,middle,dm)]
        a,b = np.concatenate((a,middle)),np.concatenate((middle,b))
        da,db = np.r_[da,dm],np.r_[dm,db]
        ids = np.tile(ids,2);depths = np.tile(depths+1,2)
        peak_cells = max(peak_cells,len(ids))
    state[state == -1] = PASSED
    # Zero is only a sentinel for rejected/unresolved edges, never an asserted
    # exact distance or a bound used for a retained route.
    lower[state != PASSED] = 0.
    assert np.all(np.isfinite(lower)) and np.all(lower[state==PASSED] >= threshold_mm)
    arrays = dict(edges=edges,state=state,accepted=state==PASSED,accepted_lower_bound_mm=lower,
        witness_lps_mm=witness,witness_effective_distance_mm=witness_distance,
        query_points_lps_mm=np.vstack(query_points) if query_points else np.empty((0,3)),
        query_wall_distances_mm=np.concatenate(query_distances) if query_distances else np.empty(0))
    report = dict(schema='kv260.surface_route.refined_edges.v1',segments=len(edges),
        accepted=int((state==PASSED).sum()),endpoint_below_threshold=int((state==ENDPOINT).sum()),
        interior_below_threshold=int((state==INTERIOR).sum()),unresolved=int((state==UNRESOLVED).sum()),
        query_budget_exhausted=int((state==BUDGET).sum()),queried_midpoints=queries,
        breadth_first_rounds=rounds,accepted_leaves=accepted_leaves,peak_active_cells=peak_cells,
        threshold_mm=float(threshold_mm),numerical_guard_mm=float(numerical_guard_mm),
        maximum_depth=maximum_depth,minimum_length_mm=minimum_length_mm,query_budget=query_budget,
        rejected_edge_lower_bound_zero_is_only_sentinel=True,
        distance_backend='caller_bound_actual_triangle_wall_oracle',
        runtime_seconds=perf_counter()-start,clinical_safety_certified=False)
    return report, arrays
