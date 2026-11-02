"""Conservative continuous-polyline review against actual PL triangle walls.

This does not extract a surface, change a mask, repair geometry or plan a route.
Distance to a triangle union is 1-Lipschitz. Endpoint distance cones therefore
give a lower bound for *every* point of each straight segment, not just samples.
Crop openings are closed algebraically only for a root winding-number query;
all six crop planes remain additional conservative route constraints. These
virtual closures never become rendered walls or replace measured wall distance.
"""
import math
from time import perf_counter
import numpy as np


def _points(value, *, nonempty=True):
    p = np.asarray(value, np.float64)
    if p.ndim != 2 or p.shape[1] != 3 or (nonempty and not len(p)) or not np.isfinite(p).all():
        raise ValueError('Finite nonempty physical LPS points required')
    return p


class MeshRegion:
    def __init__(self, points, faces, geometry):
        start = perf_counter()
        p = _points(points)
        f = np.asarray(faces)
        if (f.ndim != 2 or f.shape[1] != 3 or not len(f) or f.dtype.kind not in 'iu'
                or f.min() < 0 or f.max() >= len(p)):
            raise ValueError('Nonempty indexed triangles required')
        f = f.astype(np.int64)
        if len(np.unique(np.sort(f, axis=1), axis=0)) != len(f):
            raise ValueError('Duplicate triangle faces refused')
        triangles = p[f]
        if np.any(np.linalg.norm(np.cross(triangles[:, 1]-triangles[:, 0],
                                          triangles[:, 2]-triangles[:, 0]), axis=1) == 0):
            raise ValueError('Degenerate triangle geometry refused')
        self.origin = np.asarray(geometry['origin_lps_mm'], np.float64)
        self.spacing = np.asarray(geometry['spacing_xyz'], np.float64)
        self.direction = np.asarray(geometry['direction'], np.float64).reshape(3, 3)
        size = np.asarray(geometry['size_xyz'])
        if (self.origin.shape != (3,) or self.spacing.shape != (3,) or size.shape != (3,)
                or size.dtype.kind not in 'iu' or np.any(size < 2) or np.any(self.spacing <= 0)
                or not np.isfinite(np.r_[self.origin, self.spacing, self.direction.ravel()]).all()
                or not np.allclose(self.direction.T @ self.direction, np.eye(3), atol=1e-8, rtol=0)):
            raise ValueError('Orthogonal finite physical crop geometry required')
        self.extent = (size-1)*self.spacing
        coordinates = (p-self.origin) @ self.direction
        # Mesh vertices are stored in float32 LPS. This only recognizes their
        # known crop face, never expands the usable region for the route.
        tolerance = 5e-5
        if np.any(coordinates < -tolerance) or np.any(coordinates > self.extent+tolerance):
            raise ValueError('Mesh leaves its bound physical scalar crop')
        edges = np.concatenate((f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]))
        _, inverse, count = np.unique(np.sort(edges, axis=1), axis=0,
                                      return_inverse=True, return_counts=True)
        balance = np.bincount(inverse, weights=np.where(edges[:, 0] < edges[:, 1], 1, -1))
        if np.any(count > 2) or np.any(balance[count == 2] != 0):
            raise ValueError('Nonmanifold edges or inconsistent triangle orientation refused')
        boundary = edges[count[inverse] == 1]
        caps, loops = [], []
        if len(boundary):
            starts, start_count = np.unique(boundary[:, 0], return_counts=True)
            ends, end_count = np.unique(boundary[:, 1], return_counts=True)
            if (not np.array_equal(starts, ends) or np.any(start_count != 1) or np.any(end_count != 1)):
                raise ValueError('Boundary is not a collection of simple directed loops')
            successor = {int(a): int(b) for a, b in boundary}
            remaining = set(successor)
            while remaining:
                first = min(remaining)
                loop, at = [], first
                while at in remaining:
                    remaining.remove(at)
                    loop.append(at)
                    at = successor[at]
                if at != first or len(loop) < 3:
                    raise ValueError('Boundary chain does not close independently')
                q = coordinates[loop]
                planes = [(axis, side) for axis in range(3) for side in (0, 1)
                          if np.all(np.abs(q[:, axis]-side*self.extent[axis]) <= tolerance)]
                if len(planes) != 1:
                    raise ValueError('Internal hole or ambiguous nonplanar crop opening refused')
                # Signed fan integral closes an oriented 2-chain, including a
                # concave polygon. It is not a surface repair/triangulation for
                # rendering, MC output, nearest-wall distance or STL export.
                for i in range(1, len(loop)-1):
                    caps.append(p[[loop[0], loop[i+1], loop[i]]])
                loops.append(dict(vertices=len(loop), axis=planes[0][0], side=planes[0][1]))
        self.triangles = triangles
        self.cap_integrals = np.asarray(caps, np.float64).reshape(-1, 3, 3)
        self.report = dict(triangles=len(f), boundary_edges=len(boundary), crop_openings=loops,
            winding_closure='signed_crop_polygon_integral_only',
            real_mesh_changed=False, virtual_closures_used_for_wall_distance=False,
            self_intersection_or_clinical_validation=False,
            preparation_seconds=perf_counter()-start)

    def crop_clearance(self, points):
        q = (_points(points)-self.origin) @ self.direction
        return np.minimum(q, self.extent-q).min(axis=1)

    def root_winding(self, root):
        root = _points(np.asarray(root).reshape(1, 3))[0]
        sums = []
        for source in (self.triangles, self.cap_integrals):
            t = source-root
            norm = np.linalg.norm(t, axis=2)
            if np.any(norm == 0):
                raise ValueError('Root lies on a wall vertex')
            a, b, c = t[:, 0], t[:, 1], t[:, 2]
            determinant = np.einsum('ij,ij->i', a, np.cross(b, c))
            denominator = (norm.prod(axis=1) + np.einsum('ij,ij->i', a, b)*norm[:, 2]
                           + np.einsum('ij,ij->i', b, c)*norm[:, 0]
                           + np.einsum('ij,ij->i', c, a)*norm[:, 1])
            sums.append(math.fsum(2*np.arctan2(determinant, denominator)))
        winding = math.fsum(sums)/(4*math.pi)
        inside = abs(abs(winding)-1.) <= 1e-6 and self.crop_clearance(root[None])[0] > 0
        return dict(value=winding, inside_unit_winding_region=bool(inside),
                    integer_tolerance=1e-6, clinical_containment_certified=False)


def round_down_float32(value):
    """Keep a float32 protocol radius from overstating its float64 bound."""
    d = np.asarray(value, np.float64)
    if not np.isfinite(d).all() or np.any(d < 0) or np.any(d > np.finfo(np.float32).max):
        raise ValueError('Finite nonnegative float32-representable bounds required')
    q = d.astype(np.float32)
    above = q.astype(np.float64) > d
    q[above] = np.nextafter(q[above], np.float32(-np.inf))
    return q


def audit_polyline(region, points, wall_distances_mm, *, required_radius_mm,
                   resolution_margin_mm, numerical_guard_mm=1e-6):
    start = perf_counter()
    p = _points(points)
    d = np.asarray(wall_distances_mm, np.float64)
    parameters = np.asarray([required_radius_mm, resolution_margin_mm, numerical_guard_mm], np.float64)
    if (d.shape != (len(p),) or not np.isfinite(d).all() or np.any(d < 0)
            or not np.isfinite(parameters).all() or np.any(parameters < 0)
            or numerical_guard_mm <= 0):
        raise ValueError('Matched wall distances and nonnegative finite instrument parameters required')
    crop = region.crop_clearance(p)
    effective = np.minimum(d, crop)
    length = np.linalg.norm(np.diff(p, axis=0), axis=1)
    arc = np.r_[0., np.cumsum(length)]
    # min_x max(d0-x, d1-(L-x)); clamping by either endpoint remains
    # conservative under numerical disagreement with the Lipschitz premise.
    segment = np.minimum(np.minimum(effective[:-1], effective[1:]),
                         .5*(effective[:-1]+effective[1:]-length))-numerical_guard_mm
    threshold = float(required_radius_mm+resolution_margin_mm)
    point_ok = effective-numerical_guard_mm >= threshold
    segment_ok = segment >= threshold
    root = region.root_winding(p[0])
    prefix = 0
    if root['inside_unit_winding_region'] and point_ok[0]:
        prefix = len(p)
        failed = np.flatnonzero(~segment_ok | ~point_ok[1:])
        if len(failed):
            prefix = int(failed[0])+1
    conservative = np.maximum(0., effective-numerical_guard_mm)
    if len(segment):
        conservative[:-1] = np.minimum(conservative[:-1], np.maximum(0., segment))
        conservative[1:] = np.minimum(conservative[1:], np.maximum(0., segment))
    report = dict(schema='kv260.surface_route.continuous_audit.v1',
        status='whole_polyline_geometric_bound_passed' if prefix == len(p) else 'limited_geometric_prefix',
        point_count=len(p), point_failures=int((~point_ok).sum()), segment_failures=int((~segment_ok).sum()),
        first_uncertified_segment=int(np.flatnonzero(~segment_ok)[0]) if np.any(~segment_ok) else None,
        reviewed_prefix_points=prefix, reviewed_prefix_length_mm=float(arc[prefix-1]) if prefix else 0.,
        full_length_mm=float(arc[-1]), minimum_actual_wall_distance_mm=float(d.min()),
        minimum_crop_distance_mm=float(crop.min()),
        minimum_continuous_lower_bound_mm=float(segment.min()) if len(segment) else float(effective[0]-numerical_guard_mm),
        required_radius_mm=float(required_radius_mm), resolution_margin_mm=float(resolution_margin_mm),
        numerical_guard_mm=float(numerical_guard_mm), root_winding=root, mesh_region=region.report,
        bound_definition='minimum endpoint distance cones over each straight segment; actual triangle walls and all crop planes',
        scope='experimental geometric estimate for this exact polyline, not a physical instrument contact model',
        source_route_replanned=False, source_route_changed=False, PS_Marching_Cubes_used=False,
        clinical_safety_certified=False, production_promoted=False,
        audit_seconds=perf_counter()-start)
    arrays = dict(points_lps_mm=p, arc_mm=arc, actual_wall_distance_mm=d, crop_distance_mm=crop,
        segment_lower_bound_mm=segment, point_ok=point_ok, segment_ok=segment_ok,
        conservative_radius_mm=round_down_float32(conservative))
    return report, arrays
