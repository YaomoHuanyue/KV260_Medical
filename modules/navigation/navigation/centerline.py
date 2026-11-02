"""Crop-first Lee thinning and sparse physical-space centerline graph."""
from dataclasses import dataclass
import itertools
import numpy as np
from scipy import ndimage as ndi
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, minimum_spanning_tree, dijkstra
from scipy.spatial import cKDTree
from skimage.morphology import skeletonize
from .geometry import Geometry


@dataclass
class Centerline:
    geometry: Geometry
    offset_zyx: np.ndarray
    mask: np.ndarray
    distance_mm: np.ndarray
    indices_zyx: np.ndarray
    points_lps_mm: np.ndarray
    radii_mm: np.ndarray
    edges: np.ndarray
    components: np.ndarray
    root: int
    metadata: dict

    def adjacency(self, weights=None):
        edges = self.edges
        if weights is None:
            weights = np.linalg.norm(self.points_lps_mm[edges[:, 0]] - self.points_lps_mm[edges[:, 1]], axis=1)
        return coo_matrix((np.r_[weights, weights],
            (np.r_[edges[:, 0], edges[:, 1]], np.r_[edges[:, 1], edges[:, 0]])),
            shape=(len(self.points_lps_mm),) * 2).tocsr()

    def sample_radius(self, points):
        coords = self.geometry.to_zyx(points) - self.offset_zyx
        return ndi.map_coordinates(self.distance_mm, coords.T, order=1, mode="constant", cval=0, prefilter=False)

    def inside(self, points):
        coords = self.geometry.to_zyx(points) - self.offset_zyx
        # At a voxel corner several closed foreground cells can contain the same
        # point. A floating-point tie must not choose an unrelated background cell.
        nearest=np.floor(coords+.5+1e-7).astype(np.int64)
        ties=np.abs(coords+.5-np.round(coords+.5))<1e-7
        result=np.zeros(len(coords),bool)
        for shift in itertools.product((0,-1),repeat=3):
            candidate=nearest+np.asarray(shift)*ties
            valid=np.all((candidate>=0)&(candidate<self.mask.shape),axis=1)
            result[valid] |= self.mask[tuple(candidate[valid].T)]
        return result

    @property
    def resolution_margin_mm(self):
        return float(np.linalg.norm(self.geometry.spacing_xyz) * 0.5)

    def save(self, path):
        np.savez_compressed(path, offset_zyx=self.offset_zyx, mask=self.mask,
            distance_mm=self.distance_mm, indices_zyx=self.indices_zyx,
            points_lps_mm=self.points_lps_mm, radii_mm=self.radii_mm,
            edges=self.edges, components=self.components, root=np.array(self.root))

    @classmethod
    def load(cls, path, metadata):
        with np.load(path, allow_pickle=False) as data:
            fields = {k: data[k] for k in data.files}
        fields["root"] = int(fields["root"])
        return cls(Geometry.from_dict(metadata["geometry"]), metadata=metadata, **fields)


def _edges(indices, shape):
    # Search only sparse point IDs, never allocate a full-volume parent/id map.
    linear = np.ravel_multi_index(indices.T, shape)
    blocks = []
    for offset in itertools.product((-1, 0, 1), repeat=3):
        if offset <= (0, 0, 0):
            continue
        q = indices + offset
        valid = np.all((q >= 0) & (q < shape), axis=1)
        source = np.flatnonzero(valid)
        target_linear = np.ravel_multi_index(q[valid].T, shape)
        target = np.searchsorted(linear, target_linear)
        found = target < len(linear)
        found[found] &= linear[target[found]] == target_linear[found]
        blocks.append(np.column_stack((source[found], target[found])))
    return np.concatenate(blocks).astype(np.int32)


def extract(mask, geometry, root_lps_mm=None, max_crop_voxels=80_000_000, distance_fn=None):
    if not np.any(mask):
        raise ValueError("Airway mask is empty")
    if tuple(mask.shape[::-1]) != geometry.size_xyz:
        raise ValueError("Mask shape and geometry disagree")
    # Axis reductions avoid allocating coordinates for every foreground voxel.
    ranges = [np.flatnonzero(np.any(mask, axis=tuple(j for j in range(3) if j != i))) for i in range(3)]
    lo = np.array([r[0] for r in ranges]); hi = np.array([r[-1] + 1 for r in ranges])
    crop_shape = hi - lo + 4
    if int(np.prod(crop_shape)) > max_crop_voxels:
        raise ValueError("Airway crop exceeds memory budget; require explicit tiling, not silent downsampling")
    crop = np.pad(mask[tuple(slice(a, b) for a, b in zip(lo, hi))], 2)
    offset = lo - 2
    import time
    begin=time.perf_counter()
    if distance_fn is None:
        distance = ndi.distance_transform_edt(crop, sampling=geometry.spacing_xyz[::-1]).astype(np.float32)
        distance_stats=dict(backend='ps_scipy',total_seconds=time.perf_counter()-begin)
    else:
        distance,distance_stats=distance_fn(crop,geometry.spacing_xyz[::-1])
        if distance.shape!=crop.shape or not np.all(np.isfinite(distance)) or np.any(distance<0) or np.any(distance[~crop]!=0):
            raise ValueError('Distance backend returned invalid field')
        distance=np.asarray(distance,dtype=np.float32)
    skel = skeletonize(crop, method="lee")
    coords = np.argwhere(skel).astype(np.int32)
    if not len(coords):
        raise ValueError("Thinning produced no centerline; inspect mask or supply a different extraction algorithm")
    points = geometry.to_lps(coords + offset)
    radii = distance[tuple(coords.T)]
    edges = _edges(coords, crop.shape)
    raw = coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(len(coords),)*2).tocsr()
    component_count, component = connected_components(raw, directed=False)
    degree = np.bincount(edges.ravel(), minlength=len(coords))
    if root_lps_mm is not None:
        gap, root = cKDTree(points).query(root_lps_mm)
        if gap > 5:
            raise ValueError("Manual root is more than 5 mm from the centerline")
        root_mode = "manual_lps"
    else:
        # LPS +Z is superior even when array Z is reversed. Prefer a thick upper
        # endpoint in the component with the greatest airway voxel support.
        labels, _ = ndi.label(crop, structure=np.ones((3, 3, 3)))
        counts = np.bincount(labels.ravel()); counts[0] = 0
        primary = labels[tuple(coords.T)] == int(np.argmax(counts))
        candidates = np.flatnonzero(primary & (degree <= 1))
        if not len(candidates):
            candidates = np.flatnonzero(primary)
        superior = points[candidates, 2]
        band_mm = max(10., min(25., .15*float(np.ptp(superior))))
        upper = candidates[superior >= superior.max()-band_mm]
        root = int(upper[np.argmax(radii[upper])])
        root_mode = "automatic_superior_thick_endpoint_requires_confirmation"
    # A voxel skeleton can contain local cycles around junctions. Preserve their
    # count, then expose a spanning forest rather than silently calling it a tree.
    lengths = np.linalg.norm(points[edges[:, 0]] - points[edges[:, 1]], axis=1)
    weighted = coo_matrix((lengths, (edges[:, 0], edges[:, 1])), shape=(len(coords),)*2).tocsr()
    forest = minimum_spanning_tree(weighted + weighted.T).tocoo()
    tree_edges = np.column_stack((forest.row, forest.col)).astype(np.int32)
    removed = len(edges) - len(tree_edges)
    metadata = dict(schema="kv260.navigation.centerline.v1", backend="ps" if distance_fn is None else "pl_edt_ps_skeleton_graph", distance_transform=distance_stats, geometry=geometry.to_dict(),
        airway_voxels=int(crop.sum()), crop_shape_zyx=list(crop.shape), skeleton_points=len(coords),
        component_count=int(component_count), root=int(root), root_mode=root_mode,
        root_lps_mm=points[root].tolist(), raw_graph_edges=len(edges), removed_cycle_edges=removed,
        requested_root_lps_mm=None if root_lps_mm is None else list(map(float,root_lps_mm)),
        radius_semantics="EDT distance to background voxel centers in mm; not anatomical ground truth",
        resolution_margin_mm=float(np.linalg.norm(geometry.spacing_xyz)*0.5),
        mask_touches_image_boundary=bool(any(r[0] == 0 or r[-1] == mask.shape[i]-1 for i, r in enumerate(ranges))),
        warnings=["Automatic root requires visual confirmation", "Centerline and diameter estimates depend on segmentation and voxel spacing"])
    if removed:
        metadata["warnings"].append(f"{removed} voxel graph cycle edges removed for branch forest; inspect junction topology")
    if component_count > 1:
        metadata["warnings"].append("Disconnected components retained and marked; no bridges generated")
    return Centerline(geometry, offset, crop, distance, coords+offset, points, radii, tree_edges,
                      component.astype(np.int32), int(root), metadata)


def branch_tree(centerline, spur_threshold_mm=2.0):
    c = centerline; graph = c.adjacency(); n = len(c.points_lps_mm)
    degree = np.diff(graph.indptr)
    critical = set(np.flatnonzero(degree != 2).tolist()) | {c.root}
    # Every forest component has a critical point, including isolated points.
    nodes = sorted(critical); visited = set(); branches = []
    root_dist, parent = dijkstra(graph, directed=False, indices=c.root, return_predecessors=True)
    for start in nodes:
        for first in graph.indices[graph.indptr[start]:graph.indptr[start+1]]:
            pair = tuple(sorted((start, int(first))))
            if pair in visited:
                continue
            chain = [start]; prev, curr = start, int(first); visited.add(pair)
            while curr not in critical:
                chain.append(curr)
                adj = graph.indices[graph.indptr[curr]:graph.indptr[curr+1]]
                nxt = int(adj[adj != prev][0]); visited.add(tuple(sorted((curr, nxt))))
                prev, curr = curr, nxt
            chain.append(curr)
            if root_dist[chain[-1]] < root_dist[chain[0]]:
                chain.reverse()
            xyz = c.points_lps_mm[chain]; length = float(np.linalg.norm(np.diff(xyz, axis=0), axis=1).sum())
            branches.append(dict(id=len(branches), start=chain[0], end=chain[-1], point_ids=chain,
                length_mm=length, min_radius_mm=float(c.radii_mm[chain].min()),
                mean_radius_mm=float(c.radii_mm[chain].mean()), root_connected=bool(np.isfinite(root_dist[chain[0]])),
                short_terminal_candidate=bool(length < spur_threshold_mm and (degree[chain[0]] == 1 or degree[chain[-1]] == 1))))
    incoming = {b["end"]: b["id"] for b in branches if b["root_connected"]}
    by_id = {b["id"]: b for b in branches}
    for b in branches:
        b["parent_branch"] = incoming.get(b["start"]) if b["root_connected"] else None
    for b in branches:
        b["generation"] = None
        if b["root_connected"]:
            depth = 0; p = b["parent_branch"]
            while p is not None:
                depth += 1; p = by_id[p]["parent_branch"]
            b["generation"] = depth
    return dict(schema="kv260.navigation.branches.v1", root=c.root, branches=branches,
        nodes=[dict(id=i, lps_mm=c.points_lps_mm[i].tolist(), degree=int(degree[i]),
            component=int(c.components[i]), root_connected=bool(np.isfinite(root_dist[i]))) for i in nodes],
        short_branches_policy="flag only; preserve fine branches and original mask",
        total_length_mm=float(sum(b["length_mm"] for b in branches)))
