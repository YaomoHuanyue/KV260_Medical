"""Supplied physical path arithmetic; self-contained production helpers."""
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

def zyx_to_phys(zyx: np.ndarray, image: sitk.Image) -> np.ndarray:
    zyx = np.asarray(zyx, dtype=np.float64)
    xyz_idx = zyx[..., ::-1]
    spacing = np.asarray(image.GetSpacing(), dtype=np.float64)
    origin = np.asarray(image.GetOrigin(), dtype=np.float64)
    direction = np.asarray(image.GetDirection(), dtype=np.float64).reshape(3, 3)
    flat = xyz_idx.reshape(-1, 3)
    phys = origin + (direction @ (flat * spacing).T).T
    return phys.reshape(xyz_idx.shape)

def phys_to_zyx(points_xyz: np.ndarray, image: sitk.Image) -> np.ndarray:
    """Convert physical LPS coordinates to continuous numpy z,y,x indices."""
    points = np.asarray(points_xyz, dtype=np.float64)
    spacing = np.asarray(image.GetSpacing(), dtype=np.float64)
    origin = np.asarray(image.GetOrigin(), dtype=np.float64)
    direction = np.asarray(image.GetDirection(), dtype=np.float64).reshape(3, 3)
    flat = points.reshape(-1, 3)
    xyz_idx = (np.linalg.inv(direction) @ (flat - origin).T).T / spacing
    return xyz_idx[:, ::-1].reshape(points.shape)

def route_clearance_mm(path_xyz: np.ndarray, radius_mm: np.ndarray, image: sitk.Image) -> np.ndarray:
    """Sample the lumen distance field after smoothing in physical space."""
    coords = phys_to_zyx(path_xyz, image)
    return ndi.map_coordinates(
        radius_mm, coords.T, order=1, mode='constant', cval=0.0, prefilter=False
    )

def route_curvature(path_xyz: np.ndarray) -> tuple[float, float]:
    """Return maximum curvature (1/mm) and corresponding minimum bend radius."""
    points = np.asarray(path_xyz, dtype=float)
    if len(points) < 3:
        return 0.0, float('inf')
    a = points[1:-1] - points[:-2]
    b = points[2:] - points[1:-1]
    la = np.linalg.norm(a, axis=1)
    lb = np.linalg.norm(b, axis=1)
    good = (la > 1e-6) & (lb > 1e-6)
    if not np.any(good):
        return 0.0, float('inf')
    dots = np.sum(a[good] * b[good], axis=1) / (la[good] * lb[good])
    angles = np.arccos(np.clip(dots, -1.0, 1.0))
    arc = 0.5 * (la[good] + lb[good])
    curvature = angles / np.maximum(arc, 1e-6)
    maximum = float(np.max(curvature)) if len(curvature) else 0.0
    return maximum, (float(1.0 / maximum) if maximum > 1e-9 else float('inf'))

def turn_cost(path_xyz: np.ndarray) -> float:
    if len(path_xyz) < 3:
        return 0.0
    v = np.diff(path_xyz, axis=0)
    n = np.linalg.norm(v, axis=1)
    good = n > 1e-6
    v = v[good]
    n = n[good]
    if len(v) < 2:
        return 0.0
    u = v / n[:, None]
    dots = np.clip(np.sum(u[:-1] * u[1:], axis=1), -1.0, 1.0)
    ang = np.arccos(dots)
    # Ignore tiny voxel stair-step changes, penalize meaningful bends.
    return float(np.maximum(ang - np.deg2rad(12.0), 0.0).sum())

def resample_polyline(points_xyz: np.ndarray, sample_mm: float = 0.8) -> np.ndarray:
    points = np.asarray(points_xyz, dtype=float)
    if len(points) <= 2:
        return points
    keep = np.r_[True, np.linalg.norm(np.diff(points, axis=0), axis=1) > 1e-6]
    points = points[keep]
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    cum = np.r_[0.0, np.cumsum(seg)]
    if cum[-1] <= 0:
        return points
    s = np.arange(0.0, cum[-1] + sample_mm * 0.5, max(sample_mm, 0.25))
    s[-1] = cum[-1]
    return np.column_stack([np.interp(s, cum, points[:, j]) for j in range(3)])

def smooth_route_constrained(path_xyz: np.ndarray, local_radius_mm: np.ndarray) -> np.ndarray:
    """Smooth voxel stair-steps while keeping the camera close to the original airway centreline.

    A stronger smoothing pass is useful for virtual bronchoscopy because raw skeleton
    coordinates change direction voxel-by-voxel and make the camera shake.  The
    displacement is constrained by the local lumen radius so the path is not allowed
    to cut aggressively across airway walls at bifurcations.
    """
    if len(path_xyz) < 7:
        return path_xyz

    original = np.asarray(path_xyz, dtype=float)
    smooth = original.copy()
    # Two gentle passes remove high-frequency skeleton zig-zag without flattening bends.
    for sigma in (2.2, 1.4):
        smooth = np.column_stack([
            ndi.gaussian_filter1d(smooth[:, j], sigma=sigma, mode='nearest')
            for j in range(3)
        ])

    smooth[0] = original[0]
    smooth[-1] = original[-1]

    tree = cKDTree(original)
    d, idx = tree.query(smooth, k=1)
    idx = np.minimum(idx, len(local_radius_mm) - 1)
    safe = 0.28 * np.maximum(local_radius_mm[idx], 0.8)

    # Instead of snapping every unsafe point back abruptly (which itself creates
    # camera jumps), blend it back toward the nearest original centreline point.
    bad = d > safe
    if np.any(bad):
        target = original[idx[bad]]
        frac = np.clip(safe[bad] / np.maximum(d[bad], 1e-9), 0.0, 1.0)[:, None]
        smooth[bad] = target + (smooth[bad] - target) * frac

    return smooth
