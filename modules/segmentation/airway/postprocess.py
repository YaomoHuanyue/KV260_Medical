from __future__ import annotations
import numpy as np
from scipy import ndimage as ndi


def keep_seed_connected(
    mask: np.ndarray,
    seed_xyz: tuple[int, int, int],
    spacing_xyz: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> tuple[np.ndarray, dict]:
    """Keep only the 26-connected airway tree associated with the tracheal seed.

    If interpolation or model output leaves the exact seed voxel outside the mask,
    the physically nearest foreground component is selected.  This avoids treating
    isolated false positives as distal airway generations.
    """
    binary = np.asarray(mask, dtype=bool)
    labels, count = ndi.label(binary, structure=np.ones((3, 3, 3), dtype=np.uint8))
    if count == 0:
        raise RuntimeError("Airway mask is empty")

    x, y, z = map(int, seed_xyz)
    selected = 0
    if 0 <= z < binary.shape[0] and 0 <= y < binary.shape[1] and 0 <= x < binary.shape[2]:
        selected = int(labels[z, y, x])

    if selected == 0:
        points = np.argwhere(binary)
        sx, sy, sz = map(float, spacing_xyz)
        scale = np.array([sz, sy, sx], dtype=float)
        target = np.array([z, y, x], dtype=float)
        nearest = points[int(np.argmin(np.sum(((points - target) * scale) ** 2, axis=1)))]
        selected = int(labels[tuple(nearest)])

    kept = labels == selected
    sizes = np.bincount(labels.ravel())
    kept_voxels = int(kept.sum())
    return kept, {
        "input_component_count": int(count),
        "selected_component_label": int(selected),
        "kept_voxels": kept_voxels,
        "removed_voxels": int(binary.sum()) - kept_voxels,
        "removed_component_count": int(count - 1),
        "component_sizes_voxels": [int(v) for v in sizes[1:]],
    }

def postprocess_airway(mask: np.ndarray, closing_iterations: int=0) -> np.ndarray:
    out=mask.astype(bool)
    # Default is zero: median/erosion can erase distal bronchi. Only close when requested.
    if closing_iterations>0:
        out=ndi.binary_closing(out, structure=ndi.generate_binary_structure(3,1), iterations=closing_iterations)
    return out
