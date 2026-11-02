"""Selected-branch cues bound to the revised curve and exact renderer scalar.

Topology comes from the retained original forest. Arc correspondence comes
from the curve producer, never a guessed length ratio or a new nearest branch.
Annotations are clipped to the same quantized scalar used by C9 and its mesh.
"""
import base64
import gzip
import hashlib
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from modules.navigation.navigation.centerline import branch_tree
from modules.navigation.navigation.guidance import guidance_route_id
from modules.navigation.navigation.lumen import lumen_owners, selected_lumen
from modules.surface_quality.target_mapping import map_target
from .audit import _points


class ScalarField:
    def __init__(self, values, geometry, bits):
        q = np.asarray(values)
        spacing = np.asarray(geometry['spacing_xyz'], float)
        origin = np.asarray(geometry['origin_lps_mm'], float)
        direction = np.asarray(geometry['direction'], float).reshape(3, 3)
        size = np.asarray(geometry['size_xyz'])
        if (bits not in (5, 6) or q.dtype != np.dtype('int16') or q.ndim != 3
                or size.shape != (3,) or size.dtype.kind not in 'iu'
                or tuple(size[::-1]) != q.shape or np.any(size < 2)
                or spacing.shape != (3,) or origin.shape != (3,)
                or not np.isfinite(np.r_[spacing, origin, direction.ravel()]).all()
                or np.any(spacing <= 0)
                or not np.allclose(direction.T @ direction, np.eye(3), rtol=0, atol=1e-6)):
            raise ValueError('Exact int16 Q5/Q6 scalar and orthonormal LPS geometry required')
        self.values, self.geometry, self.bits = q, geometry, bits
        self.spacing, self.origin, self.direction = spacing, origin, direction
        self.sha256 = hashlib.sha256(np.ascontiguousarray(q, dtype='<i2').tobytes()).hexdigest()

    def sample(self, points):
        p = np.asarray(points, dtype=float)
        if p.shape[-1:] != (3,) or not np.isfinite(p).all():
            raise ValueError('Finite physical LPS points required')
        xyz = ((p.reshape(-1, 3)-self.origin) @ self.direction)/self.spacing
        values = ndi.map_coordinates(self.values, xyz[:, ::-1].T, order=1,
            mode='constant', cval=-(4 << self.bits), prefilter=False, output=np.float64)
        return (values/(1 << self.bits)).reshape(p.shape[:-1])


def _arc(points):
    return np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]


from modules.surface_route.selected_surface_r13 import selected_node_arcs as source_node_arcs


def field_aperture(field, center, tangent, branch_point_ids, point_tree):
    center = np.asarray(center, float)
    normal = np.asarray(tangent, float)
    length = np.linalg.norm(normal)
    if length < 1e-8 or float(field.sample(center)) <= 0:
        return None
    normal /= length
    axis = np.eye(3)[np.argmin(np.abs(normal))]
    u = np.cross(normal, axis); u /= np.linalg.norm(u)
    v = np.cross(normal, u)
    radius = float(field.sample(center))
    half = max(radius*2.2, min(field.spacing)*3)
    size = min(129, max(33, int(np.ceil(half*2/(min(field.spacing)*.4))) | 1))
    step = half*2/(size-1)
    x, y = np.meshgrid(np.linspace(-half, half, size), np.linspace(-half, half, size))
    world = center+x[..., None]*u+y[..., None]*v
    inside = field.sample(world) > 0
    _, owners = point_tree.query(world.reshape(-1, 3))
    owned = np.isin(owners, branch_point_ids).reshape(size, size)
    labels, _ = ndi.label(inside & owned, structure=np.ones((3, 3)))
    label = labels[size//2, size//2]
    if not label:
        return None
    mask = labels == label
    interior = ndi.binary_erosion(mask)
    stride = max(1, size//10)
    seeds = [(size//2, size//2)]
    seeds += [(a, b) for a in range(stride//2, size, stride)
              for b in range(stride//2, size, stride) if interior[a, b]]
    seeds = seeds[:1]+seeds[1:][::max(1, int(np.ceil((len(seeds)-1)/32)))]
    return dict(center_lps_mm=center.tolist(), normal_lps=normal.tolist(),
        u_lps=u.tolist(), v_lps=v.tolist(), size=size, step_mm=step,
        mask_gzip=base64.b64encode(gzip.compress(mask.astype(np.uint8).tobytes(), mtime=0)).decode(),
        sample_points_lps_mm=[world[a, b].tolist() for a, b in seeds],
        lumen_pixels=int(mask.sum()), area_mm2=float(mask.sum()*step*step),
        scalar_sha256=field.sha256, inside_rule='same_renderer_scalar_trilinear_positive')


def field_visible_samples(field, eye, gate):
    if gate is None:
        return 0
    eye = np.asarray(eye, float)
    count = 0
    for point in gate['sample_points_lps_mm']:
        delta = np.asarray(point)-eye
        steps = max(2, int(np.ceil(np.linalg.norm(delta)/(min(field.spacing)*.35))))
        count += int(np.all(field.sample(eye+np.linspace(0, 1, steps+1)[:, None]*delta) > 0))
    return count


def build_guidance(c, route, field, source_image):
    from modules.navigation.navigation.geometry import Geometry
    if not c.geometry.matches(Geometry.from_image(source_image)):
        raise ValueError('Branch ownership and original airway image geometry disagree')
    original = sitk.GetArrayViewFromImage(source_image)
    if np.any((original != 0) & (original != 1)):
        raise ValueError('Original binary airway image required')
    low = np.maximum(0, c.offset_zyx)
    high = np.minimum(original.shape, c.offset_zyx+np.asarray(c.mask.shape))
    if np.any(high <= low):
        raise ValueError('Original airway crop does not overlap its image')
    roi = original[tuple(slice(int(a), int(b)) for a, b in zip(low, high))]
    cropped = c.mask[tuple(slice(int(a), int(b)) for a, b in zip(low-c.offset_zyx, high-c.offset_zyx))]
    if (not np.array_equal(roi != 0, cropped)
            or np.count_nonzero(roi) != np.count_nonzero(original)
            or np.count_nonzero(roi) != np.count_nonzero(c.mask)):
        raise ValueError('Original airway image differs from the retained branch-ownership mask')
    mapped_arcs, correspondence = source_node_arcs(c, route)
    points, arc = route['points_lps_mm'], route['arc_mm']
    ids = np.asarray(route['centerline_point_ids'])
    result = dict(schema='kv260.surface_route.guidance.v1', route_id=guidance_route_id(route),
        scalar_sha256=field.sha256, coordinates='LPS/mm', events=[],
        correspondence=correspondence,
        policy='retained_route_selected_exit_and_descendants_in_exact_renderer_scalar',
        source_forest_or_mask_changed=False, instrument_clearance_recomputed_here=False,
        scalar_distance_used_only_for_annotation_sizing=True, production_promoted=False)
    targets = {}
    if len(points) < 2:
        return result, targets
    if np.any(field.sample(points) <= 0):
        raise ValueError('Route lies outside the scalar bound to these annotations')
    tree = branch_tree(c)
    branches = {b['id']: b for b in tree['branches']}
    edge_branch = {frozenset((a, z)): b['id'] for b in tree['branches']
                   for a, z in zip(b['point_ids'][:-1], b['point_ids'][1:])}
    degree = np.diff(c.adjacency().indptr)
    candidates = [dict(k=k, arc=float(mapped_arcs[k])) for k, pid in enumerate(ids[:-1]) if degree[pid] >= 3]
    groups = []
    cluster_mm = max(1., min(c.geometry.spacing_xyz)*2)
    for candidate in candidates:
        if groups and candidate['arc']-groups[-1][0]['arc'] <= cluster_mm:
            groups[-1].append(candidate)
        else:
            groups.append([candidate])
    point_tree = cKDTree(c.points_lps_mm)
    voxels, owners = lumen_owners(c, point_tree)

    def at(distance):
        return np.array([np.interp(distance, arc, points[:, a]) for a in range(3)])

    for i, group in enumerate(groups):
        first, last = group[0], group[-1]
        k = last['k']
        next_arc = groups[i+1][0]['arc'] if i+1 < len(groups) else float(arc[-1])
        radius = max(0., float(field.sample(at(last['arc']))))
        available = next_arc-last['arc']
        branch_id = edge_branch[frozenset((int(ids[k]), int(ids[k+1])))]
        event = dict(id=len(result['events']),
            junction_point_ids=[int(ids[v['k']]) for v in group],
            junction_lps_mm=at(first['arc']).tolist(),
            original_junction_lps_mm=c.points_lps_mm[ids[first['k']]].tolist(),
            junction_arc_mm=first['arc'], exit_arc_mm=last['arc'],
            selected_branch_id=int(branch_id), selected_exit_point_id=int(ids[k+1]),
            available=False)
        result['events'].append(event)
        if available < .5:
            event['reason'] = 'retained_route_ends_before_a_markable_exit'
            continue
        advance = min(max(1., radius*1.25), available*.55)
        marker_arc = last['arc']+advance
        marker = at(marker_arc)
        selected_ids = [pid for pid in branches[branch_id]['point_ids'] if pid != int(ids[k])]
        options = []
        eye = at(max(0, first['arc']-3))
        for shift in sorted(set(min(max(1., radius*f), available*.55) for f in (1.25, 2., 3., 4.))):
            distance = last['arc']+shift; point = at(distance)
            tangent = at(min(next_arc-.1, distance+.75))-at(max(last['arc']+.1, distance-.75))
            candidate = field_aperture(field, point, tangent, selected_ids, point_tree)
            visible = field_visible_samples(field, eye, candidate)
            if candidate and visible:
                options.append((candidate['area_mm2'], distance, point, candidate, visible))
        if options:
            _, marker_arc, marker, gate, visible = min(options, key=lambda x: x[0])
            advance = marker_arc-last['arc']; gate['incoming_visible_samples'] = visible
        else:
            tangent = at(min(next_arc-.1, marker_arc+.75))-at(max(last['arc']+.1, marker_arc-.75))
            gate = field_aperture(field, marker, tangent, selected_ids, point_tree)
        lumen = selected_lumen(c, branch_id, branches, voxels, owners, gate)
        target, mapping = map_target(lumen, source_image, field.geometry, field.values > 0)
        if not np.any(target):
            event['reason'] = 'selected_daughter_has_no_label_in_this_scalar'
            continue
        if lumen:
            samples = np.asarray(lumen['sample_points_lps_mm'], float).reshape(-1, 3)
            lumen['sample_points_lps_mm'] = samples[field.sample(samples) > 0].tolist()
        event.update(available=True, marker_lps_mm=marker.tolist(), marker_arc_mm=float(marker_arc),
            marker_radius_mm=max(.15, float(field.sample(marker))*.65), aperture=gate, lumen=lumen,
            target_mapping=mapping, target_voxels=int(target.sum()),
            show_from_mm=max(0., first['arc']-min(24., max(10., radius*3))),
            hide_after_mm=min(marker_arc-min(.8, advance*.25), next_arc-.35))
        targets[event['id']] = target
    result['unavailable_events'] = sum(not e['available'] for e in result['events'])
    return result, targets
