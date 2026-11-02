"""Relocate existing PL MC edge vertices onto the shared scalar zero surface.

Triangle extraction and topology are exclusively produced by PL binary MC.
This module has no case table, triangulation, mesh smoothing or PS MC fallback.
It checks every PL midpoint against a real sign-changing source edge and uses
the same scalar as the resident ray sampler, then applies the physical affine.
"""
import numpy as np
from .scalar_mesh_indexing_r7 import retain_PL_fan_indexing


def from_pl_words(words, field, offset_zyx, spacing_xyz, origin_lps_mm, direction):
    words = np.asarray(words)
    q = np.asarray(field)
    offset = np.asarray(offset_zyx)
    spacing = np.asarray(spacing_xyz, float)
    origin = np.asarray(origin_lps_mm, float)
    matrix = np.asarray(direction, float).reshape(3, 3)
    if (words.dtype != np.uint64 or words.ndim != 1 or not len(words) or len(words) % 3 or
            np.any(words >> np.uint64(48))):
        raise ValueError('Complete nonempty reserved-zero PL triangle words required')
    if q.ndim != 3 or q.dtype != np.dtype('<i2') or min(q.shape) < 2:
        raise ValueError('Shared INT16 scalar field required')
    if (offset.shape != (3,) or offset.dtype.kind not in 'iu' or np.any(offset < 0) or
            spacing.shape != (3,) or origin.shape != (3,) or
            not np.isfinite(np.r_[spacing, origin, matrix.ravel()]).all() or
            np.any(spacing <= 0) or not np.allclose(matrix.T @ matrix, np.eye(3), atol=1e-6, rtol=0)):
        raise ValueError('Invalid crop or physical geometry')
    unique, inverse = np.unique(words, return_inverse=True)
    doubled = np.column_stack([((unique >> np.uint64(s)) & np.uint64(65535)) for s in (0, 16, 32)]).astype(np.int64)
    odd = (doubled & 1) != 0
    kinds = odd.sum(axis=1)
    if not np.all((kinds==1)|(kinds==3)):
        raise ValueError('PL vertex is not a single lattice edge or Lewiner cell centre')
    edge_ids = np.flatnonzero(kinds==1); centre_ids = np.flatnonzero(kinds==3)
    axis = odd[edge_ids].argmax(axis=1)
    low = doubled[edge_ids] // 2 + offset[::-1]
    high = low.copy(); high[np.arange(len(high)), axis] += 1
    if np.any(low < 0) or np.any(high >= np.array(q.shape[::-1])):
        raise ValueError('PL edge is outside scalar field')
    a = q[tuple(low[:, ::-1].T)].astype(np.int32)
    b = q[tuple(high[:, ::-1].T)].astype(np.int32)
    if np.any((a > 0) == (b > 0)):
        raise ValueError('PL edge does not cross the shared zero surface')
    fraction = a.astype(np.float64) / (a.astype(np.float64) - b)
    if not np.all((fraction >= 0) & (fraction <= 1)):
        raise ValueError('Invalid scalar edge interpolation')
    xyz = doubled.astype(np.float64)*.5+offset[::-1]
    xyz[edge_ids] = low
    xyz[edge_ids, axis] += fraction
    residual = a * (1-fraction) + b * fraction
    faces = inverse.reshape(-1, 3).astype(np.uint32)
    centre_residual = []
    for centre in centre_ids:
        # The existing binary Lewiner table sometimes emits an interior fan
        # vertex. Keep its PL fan topology and place it at the mean of its own
        # relocated boundary edges. Do not invent a case table on PS or claim
        # that interior triangles exactly reproduce a trilinear isosurface.
        cell = doubled[centre]//2+offset[::-1]
        if np.any(cell<0) or np.any(cell+1>=np.array(q.shape[::-1])):
            raise ValueError('PL Lewiner cell is outside scalar field')
        neighbours = np.unique(faces[np.any(faces==centre,axis=1)])
        neighbours = neighbours[neighbours!=centre]
        if len(neighbours)<3 or np.any(kinds[neighbours]!=1):
            raise ValueError('PL Lewiner fan requires incident lattice edges')
        xyz[centre] = xyz[neighbours].mean(axis=0)
        local = xyz[centre]-cell
        if np.any(local<0) or np.any(local>1):
            raise ValueError('Relocated Lewiner centre left its original cell')
        corners = np.array([q[cell[2]+(k>>2),cell[1]+((k>>1)&1),cell[0]+(k&1)] for k in range(8)],float)
        if not np.any(corners>0) or not np.any(corners<=0):
            raise ValueError('PL Lewiner cell does not cross shared scalar')
        weights = np.array([np.prod([local[j] if (k>>j)&1 else 1-local[j] for j in range(3)]) for k in range(8)])
        centre_residual.append(float(corners@weights))
    # Exactly-zero scalar endpoints can merge several PL edge vertices.
    # Collapse only identical coordinates and remove zero-area triangles;
    # never create a triangle or use a PS case table.
    raw_faces = inverse.reshape(-1, 3)
    xyz, merged = np.unique(xyz, axis=0, return_inverse=True)
    faces = merged[faces].astype(np.uint32)
    original_faces = len(faces)
    triangle = xyz[faces]
    valid = np.any(np.cross(triangle[:,1]-triangle[:,0], triangle[:,2]-triangle[:,0]) != 0, axis=1)
    faces = faces[valid]
    if not len(faces):
        raise ValueError('PL topology collapsed to an empty scalar mesh')
    xyz, faces, indexing = retain_PL_fan_indexing(xyz, faces, raw_faces, merged, centre_ids, valid)
    points = ((xyz * spacing) @ matrix.T + origin).astype(np.float32)
    if np.linalg.det(matrix) < 0:
        faces = faces[:, [0, 2, 1]]
    return points, faces, dict(topology_backend='PL_C1_binary_Marching_Cubes',
        edge_interpolation_backend='PS_vectorized_shared_INT16_zero_crossing',
        shared_scalar_edges_checked=len(edge_ids), triangles=len(faces),
        PL_Lewiner_interior_fan_vertices=len(centre_ids),
        interior_fan_placement='mean of incident scalar-relocated PL edge vertices',
        maximum_interior_fan_trilinear_residual_q=float(max(map(abs,centre_residual),default=0)),
        PL_triangles_before_zero_endpoint_collapse=original_faces,
        zero_area_triangles_removed=original_faces-len(faces),
        maximum_linear_edge_zero_residual=float(np.max(np.abs(residual))),
        maximum_midpoint_relocation_mm=float(np.max(np.abs(fraction-.5)*spacing[axis])),
        PS_Marching_Cubes_used=False, mesh_smoothing_applied=False,
        sign_topology='same_positive_rule_as_C9_sampler', scalar_zero_indexing=indexing,
        interpolation_scope='linear scalar on lattice edges; MC faces approximate the trilinear isosurface inside cells')
