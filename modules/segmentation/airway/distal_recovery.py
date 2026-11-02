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


def _paint_bridge(mask: np.ndarray, line: np.ndarray, radius_voxels: int = 1) -> np.ndarray:
    bridge = np.zeros_like(mask, dtype=bool)
    points = np.rint(line).astype(int)
    points = np.clip(points, 0, np.asarray(mask.shape) - 1)
    bridge[tuple(points.T)] = True
    if radius_voxels > 0:
        bridge = ndi.binary_dilation(bridge, structure=STRUCT26, iterations=int(radius_voxels))
    return bridge


def closest_centerline_to_lesion_mm(mask: np.ndarray, lesion: np.ndarray, spacing_xyz) -> float:
    skeleton = skeletonize(mask.astype(bool), method="lee").astype(bool)
    airway_points = np.argwhere(skeleton)
    lesion_points = np.argwhere(lesion)
    if not len(airway_points) or not len(lesion_points):
        return float("inf")
    scale = _scale_zyx(spacing_xyz)
    tree = cKDTree(lesion_points.astype(float) * scale)
    distances, _ = tree.query(airway_points.astype(float) * scale, k=1)
    return float(np.min(distances))


def recover_distal_components(
    airway_mask: np.ndarray,
    ct: np.ndarray,
    lesion_mask: np.ndarray,
    spacing_xyz,
    network_probability: np.ndarray | None = None,
    maximum_gap_mm: float = 12.0,
    minimum_component_voxels: int = 5,
    high_threshold: float = 0.65,
    review_threshold: float = 0.38,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[RecoveryCandidate], dict]:
    """Recover probability-supported disconnected distal airway components.

    The function never edits the input mask.  It returns separate high-confidence,
    review, and experimental merged masks so uncertain evidence stays inspectable.
    """
    airway = np.asarray(airway_mask, dtype=bool)
    lesion = np.asarray(lesion_mask, dtype=bool)
    ct = np.asarray(ct)
    if airway.shape != ct.shape or lesion.shape != ct.shape:
        raise ValueError("CT, airway, and lesion arrays must share the same geometry")
    if network_probability is not None and np.asarray(network_probability).shape != ct.shape:
        raise ValueError("Network probability shape mismatch")

    labels, count = ndi.label(airway, structure=STRUCT26)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    main_label = int(np.argmax(sizes))
    main = labels == main_label
    main_skeleton = skeletonize(main, method="lee").astype(bool)
    degree = _degree_map(main_skeleton)
    endpoints = np.argwhere(main_skeleton & (degree <= 1))
    if not len(endpoints):
        raise RuntimeError("No main-tree endpoints found")

    scale = _scale_zyx(spacing_xyz)
    endpoint_tree = cKDTree(endpoints.astype(float) * scale)
    lesion_points = np.argwhere(lesion)
    if not len(lesion_points):
        raise RuntimeError("Lesion mask is empty")
    lesion_tree = cKDTree(lesion_points.astype(float) * scale)

    high_mask = np.zeros_like(airway, dtype=bool)
    review_mask = np.zeros_like(airway, dtype=bool)
    evidence = np.zeros_like(ct, dtype=np.float32)
    candidates: list[RecoveryCandidate] = []

    for component_label in range(1, count + 1):
        if component_label == main_label or sizes[component_label] < int(minimum_component_voxels):
            continue
        component = labels == component_label
        component_skeleton = skeletonize(component, method="lee").astype(bool)
        component_points = np.argwhere(component_skeleton)
        if not len(component_points):
            continue
        distances, endpoint_indices = endpoint_tree.query(component_points.astype(float) * scale, k=1)
        best_index = int(np.argmin(distances))
        gap_mm = float(distances[best_index])
        if gap_mm > float(maximum_gap_mm):
            continue
        component_point = tuple(int(v) for v in component_points[best_index])
        endpoint = tuple(int(v) for v in endpoints[int(endpoint_indices[best_index])])
        line = _line_samples(endpoint, component_point)
        bridge_vector = (np.asarray(component_point, float) - np.asarray(endpoint, float)) * scale
        bridge_norm = float(np.linalg.norm(bridge_vector))
        if bridge_norm <= 1e-9:
            continue
        tangent = _endpoint_tangent(main_skeleton, endpoint, scale)
        direction_cosine = float(np.dot(tangent, bridge_vector / bridge_norm))
        if direction_cosine < -0.15:
            continue

        endpoint_distance = float(lesion_tree.query(np.asarray(endpoint, float) * scale, k=1)[0])
        component_distance = float(lesion_tree.query(component_points.astype(float) * scale, k=1)[0].min())
        lesion_gain = endpoint_distance - component_distance
        if lesion_gain < -2.0:
            continue

        hu_values = ndi.map_coordinates(ct.astype(np.float32), line.T, order=1, mode="nearest")
        air_fraction = float(np.mean(hu_values <= -700.0))
        strong_air_fraction = float(np.mean(hu_values <= -850.0))
        tubularity = _local_tubularity(ct, line)
        elongation = _component_elongation(np.argwhere(component), scale)
        network_score = None
        if network_probability is not None:
            probability_values = ndi.map_coordinates(
                np.asarray(network_probability, dtype=np.float32), line.T,
                order=1, mode="constant", cval=0.0,
            )
            network_score = float(np.mean(probability_values))

        gap_score = math.exp(-gap_mm / max(float(maximum_gap_mm), 1e-6))
        direction_score = float(np.clip((direction_cosine + 0.15) / 1.15, 0.0, 1.0))
        elongation_score = float(np.clip((elongation - 1.0) / 3.0, 0.0, 1.0))
        lesion_score = float(1.0 / (1.0 + math.exp(-lesion_gain / 5.0)))
        if network_score is None:
            confidence = (
                0.25 * air_fraction + 0.15 * strong_air_fraction + 0.18 * tubularity
                + 0.17 * direction_score + 0.10 * elongation_score
                + 0.08 * gap_score + 0.07 * lesion_score
            )
        else:
            confidence = (
                0.25 * network_score + 0.18 * air_fraction + 0.10 * strong_air_fraction
                + 0.14 * tubularity + 0.13 * direction_score
                + 0.08 * elongation_score + 0.06 * gap_score + 0.06 * lesion_score
            )
        confidence = float(np.clip(confidence, 0.0, 1.0))
        classification = "high" if confidence >= high_threshold else (
            "review" if confidence >= review_threshold else "rejected"
        )
        bridge = _paint_bridge(airway, line, radius_voxels=1)
        candidate_region = component | bridge
        evidence[candidate_region] = np.maximum(evidence[candidate_region], confidence)
        if classification == "high":
            high_mask |= candidate_region
        elif classification == "review":
            review_mask |= candidate_region

        candidates.append(RecoveryCandidate(
            component_label=component_label,
            classification=classification,
            confidence=confidence,
            component_voxels=int(sizes[component_label]),
            gap_mm=gap_mm,
            lesion_distance_before_mm=endpoint_distance,
            lesion_distance_after_mm=component_distance,
            lesion_distance_gain_mm=lesion_gain,
            direction_cosine=direction_cosine,
            elongation=elongation,
            bridge_air_fraction=air_fraction,
            bridge_strong_air_fraction=strong_air_fraction,
            bridge_tubularity=tubularity,
            bridge_network_probability=network_score,
            endpoint_zyx=endpoint,
            component_point_zyx=component_point,
        ))

    recovered = main | high_mask
    before_gap = closest_centerline_to_lesion_mm(main, lesion, spacing_xyz)
    after_gap = closest_centerline_to_lesion_mm(recovered, lesion, spacing_xyz)
    summary = {
        "input_component_count": int(count),
        "evaluated_candidates": int(len(candidates)),
        "high_confidence_candidates": int(sum(c.classification == "high" for c in candidates)),
        "review_candidates": int(sum(c.classification == "review" for c in candidates)),
        "rejected_candidates": int(sum(c.classification == "rejected" for c in candidates)),
        "added_high_confidence_voxels": int((high_mask & ~main).sum()),
        "review_voxels": int((review_mask & ~main).sum()),
        "closest_centerline_to_lesion_before_mm": before_gap,
        "closest_centerline_to_lesion_after_mm": after_gap,
        "gap_improvement_mm": before_gap - after_gap,
        "probability_source": "network_probability" if network_probability is not None else "multi_evidence_without_network_probability",
        "high_confidence_threshold": float(high_threshold),
        "review_threshold": float(review_threshold),
        "warning": "Experimental recovery candidates; review against CT before use.",
    }
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return recovered, high_mask, review_mask, candidates, {"summary": summary, "evidence": evidence}
