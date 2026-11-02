"""PL input preparation and output geometry; no PS Marching Cubes implementation."""
import numpy as np

MAX_DIM = 512


def validate_mask(mask):
    a = np.asarray(mask)
    if a.ndim != 3 or any(n < 2 or n > MAX_DIM for n in a.shape):
        raise ValueError("Mask must be a 3D array with each dimension in [2,512]")
    if not np.all((a == 0) | (a == 1)):
        raise ValueError("Only binary 0/1 masks are supported; do not pass CT intensities")
    return np.ascontiguousarray(a, dtype=np.uint8)


def crop_mask(mask):
    """Crop with one existing background voxel of halo; do not pad image edges.

    Keeping the original image edge avoids artificially closing a clipped airway.
    Returns ZYX crop offset. Caller must add this before the physical transform.
    """
    a = np.asarray(mask)
    if a.ndim != 3 or min(a.shape) < 2:
        raise ValueError("Expected a 3D mask with dimensions >= 2")
    if not np.all((a == 0) | (a == 1)):
        raise ValueError("Expected binary data")
    # Axis projections avoid allocating three coordinates for every foreground
    # voxel (hundreds of MiB for a dense lung mask). Same exact crop bounds.
    occupied = [np.flatnonzero(np.any(a, axis=tuple(j for j in range(3) if j != i)))
                for i in range(3)]
    if len(occupied[0]) == 0:
        return validate_mask(a[:2, :2, :2]), np.zeros(3, dtype=np.int64)
    lo = np.array([max(0, int(c[0])-1) for c in occupied])
    hi = np.array([min(a.shape[i], int(c[-1])+2) for i,c in enumerate(occupied)])
    return validate_mask(a[tuple(slice(l,h) for l,h in zip(lo,hi))]), lo


def unpack_vertices(words):
    w = np.asarray(words, dtype=np.uint64)
    if np.any(w >> np.uint64(48)):
        raise ValueError("Reserved vertex bits are not zero")
    return np.column_stack([((w >> np.uint64(s)) & np.uint64(65535))
                            for s in (0,16,32)]).astype(np.float32) * 0.5


def to_mesh(words, spacing_xyz=(1,1,1), origin_xyz=(0,0,0),
            direction=np.eye(3), crop_offset_zyx=(0,0,0)):
    """Deduplicate exact Q1 voxel vertices, then apply the original image affine."""
    words = np.asarray(words, dtype=np.uint64)
    if words.size % 3:
        raise ValueError("Output must contain complete triangles")
    d=np.asarray(direction, dtype=float).reshape(3,3)
    spacing=np.asarray(spacing_xyz, dtype=float)
    origin=np.asarray(origin_xyz, dtype=float)
    if spacing.shape!=(3,) or origin.shape!=(3,) or not np.all(spacing>0):
        raise ValueError("Invalid image geometry")
    if not all(np.isfinite(v).all() for v in (d,spacing,origin)) or abs(np.linalg.det(d))<1e-9:
        raise ValueError("Invalid image direction/geometry")
    unique,inverse=np.unique(words, return_inverse=True)
    xyz=unpack_vertices(unique)+np.asarray(crop_offset_zyx)[::-1]
    points=(xyz*spacing) @ d.T+origin
    faces=inverse.reshape(-1,3).astype(np.int32)
    if np.linalg.det(d)<0:
        faces=faces[:,[0,2,1]]
    return points.astype(np.float32),faces

