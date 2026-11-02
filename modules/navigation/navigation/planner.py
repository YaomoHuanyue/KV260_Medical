"""Clearance-aware routing without crossing disconnected airway components."""
from dataclasses import dataclass
import numpy as np
from scipy import ndimage as ndi
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree


@dataclass
class Target:
    kind: str
    points_lps_mm: np.ndarray
    metadata: dict


def lesion_targets(mask, geometry):
    if not np.any(mask):return []
    ranges=[np.flatnonzero(np.any(mask,axis=tuple(j for j in range(3) if j!=i))) for i in range(3)]
    offset=np.array([r[0] for r in ranges]);end=np.array([r[-1]+1 for r in ranges])
    cropped=mask[tuple(slice(a,b) for a,b in zip(offset,end))]
    labels, count = ndi.label(cropped, structure=np.ones((3, 3, 3)))
    sizes = np.bincount(labels.ravel())
    boxes=ndi.find_objects(labels)
    targets = []
    for rank, label in enumerate(sorted(range(1, count+1), key=lambda i: (-sizes[i], i))):
        box=boxes[label-1];local_offset=offset+np.array([s.start for s in box])
        component = labels[box] == label
        surface = component & ~ndi.binary_erosion(component)
        points = geometry.to_lps(np.argwhere(surface)+local_offset)
        center = geometry.to_lps(np.array(ndi.center_of_mass(component))+local_offset)
        targets.append(Target("lesion_candidate", points, dict(index=rank, voxel_count=int(sizes[label]),
            centroid_lps_mm=center.tolist(), label_status="segmentation candidate, not confirmed lesion")))
    return targets


def endpoint_target(centerline, point_id):
    if point_id < 0 or point_id >= len(centerline.points_lps_mm):
        raise ValueError("Endpoint ID outside centerline")
    degree = np.diff(centerline.adjacency().indptr)
    if degree[point_id] > 1:
        raise ValueError("Requested point is not a terminal endpoint")
    return Target("endpoint", centerline.points_lps_mm[[point_id]], dict(point_id=int(point_id)))


def densify(points, step_mm):
    if len(points) < 2:
        return np.array(points, dtype=np.float64, copy=True)
    blocks = []
    for a, b in zip(points[:-1], points[1:]):
        count = max(1, int(np.ceil(np.linalg.norm(b-a)/step_mm)))
        blocks.append(a + np.arange(count)[:, None] / count * (b-a))
    return np.vstack(blocks + [points[-1:]])


def _path(parent, root, end):
    result = [int(end)]
    while result[-1] != root:
        p = int(parent[result[-1]])
        if p < 0 or len(result) > len(parent):
            raise RuntimeError("Invalid route predecessor chain")
        result.append(p)
    return result[::-1]


def plan(centerline, target, scope_diameter_mm=1.0, safety_margin_mm=0.2, sample_mm=0.5,
         narrow_weight=2.0, smooth=True):
    c = centerline
    numbers = [scope_diameter_mm, safety_margin_mm, sample_mm, narrow_weight]
    if not np.all(np.isfinite(numbers)) or min(numbers) < 0 or sample_mm <= 0:
        raise ValueError("Require finite nonnegative scope/margin/weight and positive sample step")
    if not len(target.points_lps_mm) or not np.all(np.isfinite(target.points_lps_mm)):
        raise ValueError("Target is empty or nonfinite")
    required = scope_diameter_mm*0.5 + safety_margin_mm
    # A zero-diameter, zero-margin camera is a virtual point explorer. Its only
    # constraint is mask membership, not a finite instrument radius estimate.
    resolution = c.resolution_margin_mm if required>0 else 0.0
    adjusted = np.maximum(0, c.radii_mm - resolution)
    target_tree = cKDTree(target.points_lps_mm)
    gaps, _ = target_tree.query(c.points_lps_mm)
    desired = int(np.argmin(gaps))
    if target.kind == "manual_point" and gaps[desired] > 5:
        raise ValueError("Manual target is more than 5 mm from the centerline; use a lesion candidate or a closer waypoint")
    edges = c.edges
    length = np.linalg.norm(c.points_lps_mm[edges[:, 0]] - c.points_lps_mm[edges[:, 1]], axis=1)
    clearance = np.minimum(adjusted[edges[:, 0]], adjusted[edges[:, 1]])
    weights = length * (1 + narrow_weight*(required/(clearance+min(c.geometry.spacing_xyz)))**2)
    # Remove impassable edges rather than replacing them by an arbitrary huge cost.
    allowed = clearance + 1e-6 >= required
    if len(edges):
        # Voxel-center radii alone miss narrow corners between adjacent points.
        edge_step = min(float(sample_mm), min(c.geometry.spacing_xyz)*.25)
        subdivisions = max(1, int(np.ceil(length.max()/edge_step)))
        fractions = np.linspace(0,1,subdivisions+1)
        samples = c.points_lps_mm[edges[:,0],None,:] + fractions[None,:,None] * (
            c.points_lps_mm[edges[:,1]]-c.points_lps_mm[edges[:,0]])[:,None,:]
        shape = samples.shape[:2]
        flat = samples.reshape(-1,3)
        valid_samples = c.inside(flat) & (c.sample_radius(flat)-resolution+1e-5 >= required)
        allowed &= np.all(valid_samples.reshape(shape),axis=1)
    graph = c.adjacency(weights)
    if len(edges):
        from scipy.sparse import coo_matrix
        e = edges[allowed]; w = weights[allowed]
        graph = coo_matrix((np.r_[w,w],(np.r_[e[:,0],e[:,1]],np.r_[e[:,1],e[:,0]])),shape=graph.shape).tocsr()
    costs, parent = dijkstra(graph, indices=c.root, directed=False, return_predecessors=True)
    root_has_clearance = bool(adjusted[c.root]+1e-6 >= required)
    if not root_has_clearance:
        costs[:] = np.inf
    reachable = np.flatnonzero(np.isfinite(costs))
    reason = None
    if c.components[desired] != c.components[c.root]:
        reason = "disconnected_target_component"
    elif not root_has_clearance:
        reason = "insufficient_root_clearance"
    elif not np.isfinite(costs[desired]):
        reason = "insufficient_route_clearance"
    end = desired if reason is None else (int(reachable[np.argmin(gaps[reachable])]) if len(reachable) else None)
    ids = _path(parent, c.root, end) if end is not None else []
    raw = c.points_lps_mm[ids]
    step = min(float(sample_mm), min(c.geometry.spacing_xyz)*0.25)
    points = densify(raw, step)
    def valid(p):
        return bool(np.all(c.inside(p)) and np.all(c.sample_radius(p)-resolution+1e-5 >= required))
    smoothing_accepted = False
    # Bound displacement and verify the actual curve; smoothing cannot bridge gaps.
    if smooth and len(points) > 2 and valid(points):
        candidate = points.copy()
        for _ in range(8):
            update = .2 * (.5*(candidate[:-2]+candidate[2:])-candidate[1:-1])
            candidate[1:-1] += update
            delta = candidate-points; size = np.linalg.norm(delta,axis=1)
            limit = min(c.geometry.spacing_xyz)*.15
            candidate = points + delta * np.minimum(1, limit/np.maximum(size, 1e-12))[:,None]
        tested = densify(candidate, step)
        if valid(tested):
            points = tested; smoothing_accepted = True
    if len(points) and not valid(points):
        good = c.inside(points) & (c.sample_radius(points)-resolution+1e-5 >= required)
        first_bad = int(np.flatnonzero(~good)[0]); points = points[:first_bad]
        reason = "continuous_route_clearance_failed"
    radii = c.sample_radius(points) if len(points) else np.empty(0)
    arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(points, axis=0),axis=1))] if len(points) else np.empty(0)
    if len(points) > 2:
        a = np.diff(points,axis=0); norm = np.linalg.norm(a,axis=1)
        angles = np.arccos(np.clip(np.sum(a[:-1]*a[1:],axis=1)/np.maximum(norm[:-1]*norm[1:],1e-12),-1,1))
        max_curvature = float(np.max(angles/np.maximum(.5*(norm[:-1]+norm[1:]),1e-12)))
    else:
        max_curvature = 0.0
    status = "limited_reach" if reason and len(points) > 1 else ("unreachable" if reason else
        ("airway_approach" if target.kind == "lesion_candidate" else "route_found"))
    report = dict(schema="kv260.navigation.route.v1", backend="ps", status=status, reason=reason,
        target_kind=target.kind, target=target.metadata, requested_endpoint_id=desired,
        selected_endpoint_id=end, requested_endpoint_lps_mm=c.points_lps_mm[desired].tolist(),
        closest_centerline_gap_mm=float(gaps[desired]),
        final_target_gap_mm=float(target_tree.query(points[-1])[0]) if len(points) else None,
        length_mm=float(arc[-1]) if len(arc) else 0.0, point_count=len(points),
        minimum_edt_radius_mm=float(radii.min()) if len(radii) else None,
        minimum_adjusted_radius_mm=float(np.maximum(0,radii-resolution).min()) if len(radii) else None,
        scope_diameter_mm=float(scope_diameter_mm), safety_margin_mm=float(safety_margin_mm),
        required_radius_mm=float(required), resolution_margin_mm=resolution,
        reachable_centerline_points=len(reachable), total_centerline_points=len(c.points_lps_mm),
        smoothing_accepted=smoothing_accepted, max_discrete_curvature_per_mm=max_curvature,
        target_points_lps_mm=target.points_lps_mm.tolist() if target.kind != "lesion_candidate" else [],
        quality_status="experimental_geometry_only", warnings=list(c.metadata["warnings"]))
    report["planning_mode"]="clearance_estimate" if required>0 else "virtual_point_exploration"
    if reason:
        report["warnings"].append("Displayed route is the reachable approach only; requested endpoint was not reached")
    if target.kind == "lesion_candidate":
        report["warnings"].append("Route ends inside airway near candidate; it does not enter or reach an external lesion")
    return report, dict(points_lps_mm=points, radius_mm=radii, arc_mm=arc, centerline_point_ids=np.asarray(ids,dtype=np.int32))
