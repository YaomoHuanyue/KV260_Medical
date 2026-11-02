"""Sparse, original-rule whole-skeleton profile; not a route safety certificate."""
from dataclasses import dataclass
from pathlib import Path
import ctypes
import itertools
import math
import numpy as np

OFFSETS = tuple(offset for offset in itertools.product((-1, 0, 1), repeat=3) if offset != (0, 0, 0))
HERE = Path(__file__).resolve().parent


@dataclass
class Graph:
    coordinates_zyx: np.ndarray
    rows: np.ndarray
    neighbors: np.ndarray
    lengths: np.ndarray
    radii_mm: np.ndarray
    spacing_zyx: tuple
    root: int
    half_edges: tuple


def graph(coordinates, radii_mm, root, spacing_zyx):
    raw = np.asarray(coordinates)
    if raw.ndim != 2 or raw.shape[1] != 3 or not len(raw) or not np.issubdtype(raw.dtype, np.integer):
        raise ValueError('Require a nonempty integer skeleton coordinate array')
    if np.any(raw < 0) or np.any(raw > np.iinfo(np.int32).max):
        raise ValueError('Skeleton coordinates are outside supported integer bounds')
    coordinates = np.ascontiguousarray(raw, dtype=np.int32)
    order = np.lexsort(coordinates.T[::-1])
    if not np.array_equal(order, np.arange(len(raw))) or np.any(np.all(np.diff(coordinates, axis=0) == 0, axis=1)):
        raise ValueError('Skeleton coordinates must be unique and in original argwhere order')
    spacing = tuple(map(float, spacing_zyx))
    radii = np.ascontiguousarray(radii_mm, dtype=np.float64)
    if len(spacing) != 3 or not np.isfinite(spacing).all() or min(spacing) <= 0:
        raise ValueError('Require three positive voxel spacings')
    if radii.shape != (len(raw),) or not np.isfinite(radii).all() or np.any(radii < 0):
        raise ValueError('Invalid skeleton radii')
    if not isinstance(root, (int, np.integer)) or not 0 <= root < len(raw):
        raise ValueError('Root is not a skeleton node')
    lookup = {tuple(map(int, point)): index for index, point in enumerate(coordinates)}
    rows = [0]; neighbors = []; lengths = []
    half_edges = {offset: [] for offset in OFFSETS if offset > (0, 0, 0)}
    steps = {offset: math.sqrt(sum((delta*scale)**2 for delta, scale in zip(offset, spacing))) for offset in OFFSETS}
    for index, point in enumerate(coordinates):
        p = tuple(map(int, point))
        for offset in OFFSETS:
            other = tuple(a+b for a, b in zip(p, offset))
            target = lookup.get(other)
            if target is not None:
                neighbors.append(target); lengths.append(steps[offset])
                if offset > (0, 0, 0):
                    half_edges[offset].append((index, target))
        rows.append(len(neighbors))
    half = tuple((offset, steps[offset], np.asarray(pairs, dtype=np.int32).reshape(-1, 2))
                 for offset, pairs in half_edges.items())
    return Graph(coordinates, np.asarray(rows, dtype=np.uint32), np.asarray(neighbors, dtype=np.uint32),
                 np.asarray(lengths, dtype=np.float64), radii, spacing, int(root), half)


def solve(data, diameters, safety_margin_mm=.2, radius_weight=2., threads=4, library=None):
    diameters = np.asarray(sorted({float(value) for value in diameters if float(value) > 0.}), dtype=np.float64)
    if not len(diameters):
        return diameters, np.empty((0, len(data.coordinates_zyx))), np.empty((0, len(data.coordinates_zyx)), np.int32)
    if not np.isfinite(diameters).all() or len(diameters) > 64:
        raise ValueError('Invalid instrument diameters')
    library = Path(library) if library is not None else HERE/'build'/('profile_ps_r1.dll' if __import__('os').name == 'nt' else 'libprofile_ps_r1.so')
    lib = ctypes.CDLL(str(library))
    function = lib.profile_ps
    function.argtypes = [ctypes.c_uint32]*2 + [ctypes.c_void_p]*4 + [ctypes.c_uint32]*2 + [ctypes.c_void_p,
                         ctypes.c_double, ctypes.c_double, ctypes.c_uint32] + [ctypes.c_void_p]*2
    function.restype = ctypes.c_int
    distances = np.empty((len(diameters), len(data.coordinates_zyx)), dtype=np.float64)
    parents = np.empty(distances.shape, dtype=np.int32)
    code = function(len(data.coordinates_zyx), len(data.neighbors), data.rows.ctypes.data,
                    data.neighbors.ctypes.data, data.lengths.ctypes.data, data.radii_mm.ctypes.data,
                    data.root, len(diameters), diameters.ctypes.data, safety_margin_mm, radius_weight, threads,
                    distances.ctypes.data, parents.ctypes.data)
    if code:
        raise ValueError('Invalid original profile inputs: '+str(code))
    return diameters, distances, parents


def report(data, image, lesion_tree, diameters, distances, parents):
    # Same coordinate transform and summation order as the supplied Python rule.
    origin = np.asarray(image.GetOrigin()); spacing = np.asarray(image.GetSpacing())
    direction = np.asarray(image.GetDirection()).reshape(3, 3)
    points = origin + (direction @ (data.coordinates_zyx[:, ::-1].astype(float)*spacing).T).T
    gaps = lesion_tree.query(points, k=1)[0]
    profiles = []
    for diameter, dist, parent in zip(diameters, distances, parents):
        reachable = np.isfinite(dist)
        ids = np.flatnonzero(reachable)
        if not len(ids):
            profiles.append(dict(scope_diameter_mm=float(diameter), reachable=False,
                                 closest_lesion_gap_mm=None, reachable_centerline_length_mm=0.))
            continue
        end = int(ids[int(np.argmin(gaps[ids]))])
        chain = [end]
        while chain[-1] != data.root:
            previous = int(parent[chain[-1]])
            if not 0 <= previous < len(parent) or len(chain) > len(parent):
                raise ValueError('Invalid reachable parent chain')
            chain.append(previous)
        chain.reverse()
        path = points[chain]
        length = float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())
        total = 0.
        for offset, step, edges in data.half_edges:
            total += float(np.count_nonzero(reachable[edges[:, 0]] & reachable[edges[:, 1]]))*step
        profiles.append(dict(scope_diameter_mm=float(diameter), reachable=True,
            closest_lesion_gap_mm=float(gaps[end]), closest_endpoint_xyz_mm=points[end].tolist(),
            path_length_to_closest_point_mm=length, reachable_skeleton_voxels=int(reachable.sum()),
            reachable_centerline_length_mm=total, maximum_geodesic_cost_mm=float(np.max(dist[reachable]))))
    return profiles
