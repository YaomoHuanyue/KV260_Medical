"""Evidence scoring helpers preserved from the supplied Python algorithm."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.filters import frangi
from skimage.morphology import skeletonize


STRUCT26 = np.ones((3, 3, 3), dtype=np.uint8)


@dataclass
class RecoveryCandidate:
    component_label: int
    classification: str
    confidence: float
    component_voxels: int
    gap_mm: float
    lesion_distance_before_mm: float
    lesion_distance_after_mm: float
    lesion_distance_gain_mm: float
    direction_cosine: float
    elongation: float
    bridge_air_fraction: float
    bridge_strong_air_fraction: float
    bridge_tubularity: float
    bridge_network_probability: float | None
    endpoint_zyx: tuple[int, int, int]
    component_point_zyx: tuple[int, int, int]

    def to_dict(self):
        value = asdict(self)
        value["endpoint_zyx"] = list(self.endpoint_zyx)
        value["component_point_zyx"] = list(self.component_point_zyx)
        return value


def _scale_zyx(spacing_xyz) -> np.ndarray:
    sx, sy, sz = map(float, spacing_xyz)
    return np.array([sz, sy, sx], dtype=float)


def _degree_map(skeleton: np.ndarray) -> np.ndarray:
    kernel = STRUCT26.copy()
    kernel[1, 1, 1] = 0
    return ndi.convolve(skeleton.astype(np.uint8), kernel, mode="constant", cval=0)


def _endpoint_tangent(skeleton: np.ndarray, endpoint, scale: np.ndarray, steps: int = 8) -> np.ndarray:
    current = tuple(int(v) for v in endpoint)
    previous = None
    history = [current]
    for _ in range(max(1, int(steps))):
        z, y, x = current
        neighbors = []
        for dz in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    q = (z + dz, y + dy, x + dx)
                    if (dz, dy, dx) == (0, 0, 0) or q == previous:
                        continue
                    if (0 <= q[0] < skeleton.shape[0] and 0 <= q[1] < skeleton.shape[1]
                            and 0 <= q[2] < skeleton.shape[2] and skeleton[q]):
                        neighbors.append(q)
        if not neighbors:
            break
        # Prefer continuing away from the endpoint when a tiny junction cluster is met.
        if len(history) >= 2:
            inward = (np.asarray(current) - np.asarray(history[-2])) * scale
            next_point = max(
                neighbors,
                key=lambda q: float(np.dot((np.asarray(q) - np.asarray(current)) * scale, inward)),
            )
        else:
            next_point = neighbors[0]
        previous, current = current, next_point
        history.append(current)
    outward = (np.asarray(history[0], float) - np.asarray(history[-1], float)) * scale
    norm = float(np.linalg.norm(outward))
    return outward / norm if norm > 1e-9 else np.zeros(3, dtype=float)


def _line_samples(a, b, samples_per_voxel: float = 2.0) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    count = max(2, int(np.linalg.norm(b - a) * samples_per_voxel) + 1)
    return np.linspace(a, b, count)


def _component_elongation(points_zyx: np.ndarray, scale: np.ndarray) -> float:
    if len(points_zyx) < 4:
        return 1.0
    physical = points_zyx.astype(float) * scale
    values = np.linalg.eigvalsh(np.cov(physical.T))
    values = np.sort(np.maximum(values, 1e-6))
    return float(math.sqrt(values[-1] / values[-2]))


def _local_tubularity(ct: np.ndarray, line: np.ndarray) -> float:
    lo = np.maximum(np.floor(line.min(axis=0)).astype(int) - 5, 0)
    hi = np.minimum(np.ceil(line.max(axis=0)).astype(int) + 6, np.asarray(ct.shape))
    slices = tuple(slice(int(lo[i]), int(hi[i])) for i in range(3))
    roi = np.clip((ct[slices].astype(np.float32) + 1000.0) / 500.0, 0.0, 1.0)
    if min(roi.shape) < 3:
        return 0.0
    response = frangi(roi, sigmas=(1, 2), black_ridges=True)
    local_line = line - lo[None, :]
    sampled = ndi.map_coordinates(response, local_line.T, order=1, mode="constant", cval=0.0)
    positive = response[response > 0]
    reference = float(np.percentile(positive, 95)) if len(positive) else 0.0
    if reference <= 1e-9:
        return 0.0
    return float(np.clip(np.mean(sampled) / reference, 0.0, 1.0))


