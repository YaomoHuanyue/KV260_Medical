"""ROI implementation of the supplied recovery rules; no accepted-mask edits."""
from __future__ import annotations

import math
import time
import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.morphology import skeletonize

from .evidence import (STRUCT26, RecoveryCandidate, _scale_zyx, _degree_map,
                       _endpoint_tangent, _line_samples, _component_elongation,
                       _local_tubularity)


def _expanded(box, shape, halo=1):
    return tuple(slice(max(0, s.start - halo), min(n, s.stop + halo))
                 for s, n in zip(box, shape))


def _offset(box):
    return np.array([s.start for s in box], dtype=np.int64)


def _cropped_skeleton(mask):
    box = ndi.find_objects(mask.astype(np.uint8), max_label=1)[0]
    if box is None:
        return np.empty((0, 3), np.int64)
    box = _expanded(box, mask.shape)
    return np.argwhere(skeletonize(mask[box], method='lee').astype(bool)) + _offset(box)


def _validate(airway, ct, lesion, probability, spacing, maximum_gap,
              minimum_size, high, review):
    if airway.ndim != 3 or min(airway.shape) < 1 or ct.shape != airway.shape or lesion.shape != airway.shape:
        raise ValueError('CT, airway and lesion must have the same nonempty 3D shape')
    if not np.issubdtype(ct.dtype, np.number) or np.issubdtype(ct.dtype, np.complexfloating):
        raise ValueError('CT must contain real numerical values')
    if probability is not None and probability.shape != airway.shape:
        raise ValueError('Probability shape mismatch')
    scale = np.asarray(spacing, float)
    if scale.shape != (3,) or not np.isfinite(scale).all() or (scale <= 0).any():
        raise ValueError('Invalid physical spacing')
    if not np.isfinite([maximum_gap, high, review]).all() or maximum_gap <= 0 or not 0 <= review <= high <= 1:
        raise ValueError('Invalid confidence/gap parameters')
    if int(minimum_size) != minimum_size or minimum_size < 1:
        raise ValueError('Invalid minimum component size')
    for z in range(len(ct)):
        if np.any((airway[z] != 0) & (airway[z] != 1)) or np.any((lesion[z] != 0) & (lesion[z] != 1)):
            raise ValueError('Masks must be binary')
        if not np.isfinite(ct[z]).all():
            raise ValueError('Non-finite CT')
        if probability is not None and (not np.isfinite(probability[z]).all() or
                                       np.any((probability[z] < 0) | (probability[z] > 1))):
            raise ValueError('Probability must be finite in [0,1]')


def _sample_float_roi(values, line, mode):
    """Keep float32/order-1 arithmetic, cast only the interpolation footprint."""
    lo = np.maximum(np.floor(line.min(axis=0)).astype(int), 0)
    hi = np.minimum(np.floor(line.max(axis=0)).astype(int) + 2, values.shape)
    box = tuple(slice(int(a), int(b)) for a, b in zip(lo, hi))
    return ndi.map_coordinates(np.asarray(values[box], dtype=np.float32),
                               (line - lo).T, order=1, mode=mode, cval=0.0)


def _candidate_region(component_box, component, line, shape):
    points = np.clip(np.rint(line).astype(int), 0, np.asarray(shape) - 1)
    lo = np.minimum(_offset(component_box), np.maximum(points.min(axis=0) - 1, 0))
    hi = np.maximum(np.array([s.stop for s in component_box]), np.minimum(points.max(axis=0) + 2, shape))
    box = tuple(slice(int(a), int(b)) for a, b in zip(lo, hi))
    bridge = np.zeros(tuple(hi - lo), bool)
    bridge[tuple((points - lo).T)] = True
    bridge = ndi.binary_dilation(bridge, structure=STRUCT26, iterations=1)
    inside = tuple(slice(s.start - int(a), s.stop - int(a)) for s, a in zip(component_box, lo))
    bridge[inside] |= component
    return box, bridge


def recover_distal_components(airway_mask, ct, lesion_mask, spacing_xyz,
                              network_probability=None, maximum_gap_mm=12.,
                              minimum_component_voxels=5, high_threshold=.65,
                              review_threshold=.38, distance_provider=None):
    """Same decisions as the supplied algorithm, with sparse/ROI preparation.

    Optional distance_provider compares the existing PL distance field on the
    exact point sets. Nearest-point IDs and tie rules remain the supplied KD tree.
    It must return distances of the same length; mismatches fail before output.
    """
    begin = time.perf_counter()
    airway, ct, lesion = map(np.asarray, [airway_mask, ct, lesion_mask])
    probability = None if network_probability is None else np.asarray(network_probability)
    _validate(airway, ct, lesion, probability, spacing_xyz, maximum_gap_mm,
              minimum_component_voxels, high_threshold, review_threshold)
    airway, lesion = airway.astype(bool, copy=False), lesion.astype(bool, copy=False)
    if not airway.any():
        raise ValueError('Airway mask is empty')
    lesion_points = np.argwhere(lesion)
    if not len(lesion_points):
        raise ValueError('Lesion mask is empty')
    labels, count = ndi.label(airway, structure=STRUCT26)
    sizes = np.bincount(labels.ravel()); sizes[0] = 0
    main_label = int(np.argmax(sizes))
    boxes = ndi.find_objects(labels, max_label=count)
    main_box = _expanded(boxes[main_label - 1], airway.shape)
    main_local = labels[main_box] == main_label
    main_skeleton = skeletonize(main_local, method='lee').astype(bool)
    main_offset = _offset(main_box)
    main_points = np.argwhere(main_skeleton) + main_offset
    endpoints = np.argwhere(main_skeleton & (_degree_map(main_skeleton) <= 1)) + main_offset
    if not len(endpoints):
        raise RuntimeError('No main-tree endpoints found')
    scale = _scale_zyx(spacing_xyz)
    endpoint_tree = cKDTree(endpoints.astype(float) * scale)
    lesion_tree = cKDTree(lesion_points.astype(float) * scale)
    high_mask, review_mask = np.zeros_like(airway), np.zeros_like(airway)
    evidence = np.zeros(airway.shape, np.float32)
    candidates, queries = [], []
    for component_label in range(1, count + 1):
        if component_label == main_label or sizes[component_label] < int(minimum_component_voxels):
            continue
        component_box = _expanded(boxes[component_label - 1], airway.shape)
        component = labels[component_box] == component_label
        component_points = np.argwhere(skeletonize(component, method='lee').astype(bool)) + _offset(component_box)
        if not len(component_points):
            continue
        distances, endpoint_indices = endpoint_tree.query(component_points.astype(float) * scale, k=1)
        queries.append((endpoints, component_points, np.asarray(distances)))
        best_index = int(np.argmin(distances)); gap_mm = float(distances[best_index])
        if gap_mm > float(maximum_gap_mm):
            continue
        component_point = tuple(int(v) for v in component_points[best_index])
        endpoint = tuple(int(v) for v in endpoints[int(endpoint_indices[best_index])])
        line = _line_samples(endpoint, component_point)
        vector = (np.asarray(component_point, float) - endpoint) * scale
        norm = float(np.linalg.norm(vector))
        if norm <= 1e-9:
            continue
        tangent = _endpoint_tangent(main_skeleton, np.asarray(endpoint) - main_offset, scale)
        direction_cosine = float(np.dot(tangent, vector / norm))
        if direction_cosine < -.15:
            continue
        endpoint_distance = float(lesion_tree.query(np.asarray(endpoint, float) * scale, k=1)[0])
        component_distance = float(lesion_tree.query(component_points.astype(float) * scale, k=1)[0].min())
        lesion_gain = endpoint_distance - component_distance
        if lesion_gain < -2.:
            continue
        hu = _sample_float_roi(ct, line, 'nearest')
        air = float(np.mean(hu <= -700.)); strong_air = float(np.mean(hu <= -850.))
        tubularity = _local_tubularity(ct, line)
        elongation = _component_elongation(np.argwhere(component) + _offset(component_box), scale)
        network = None if probability is None else float(np.mean(_sample_float_roi(probability, line, 'constant')))
        gap_score = math.exp(-gap_mm / max(float(maximum_gap_mm), 1e-6))
        direction_score = float(np.clip((direction_cosine + .15) / 1.15, 0., 1.))
        elongation_score = float(np.clip((elongation - 1.) / 3., 0., 1.))
        lesion_score = float(1. / (1. + math.exp(-lesion_gain / 5.)))
        if network is None:
            confidence = (.25 * air + .15 * strong_air + .18 * tubularity + .17 * direction_score
                          + .10 * elongation_score + .08 * gap_score + .07 * lesion_score)
        else:
            confidence = (.25 * network + .18 * air + .10 * strong_air + .14 * tubularity
                          + .13 * direction_score + .08 * elongation_score + .06 * gap_score + .06 * lesion_score)
        confidence = float(np.clip(confidence, 0., 1.))
        classification = 'high' if confidence >= high_threshold else ('review' if confidence >= review_threshold else 'rejected')
        box, region = _candidate_region(component_box, component, line, airway.shape)
        local_evidence = evidence[box]
        local_evidence[region] = np.maximum(local_evidence[region], confidence)
        if classification == 'high':
            high_mask[box] |= region
        elif classification == 'review':
            review_mask[box] |= region
        candidates.append(RecoveryCandidate(component_label, classification, confidence, int(sizes[component_label]),
            gap_mm, endpoint_distance, component_distance, lesion_gain, direction_cosine, elongation,
            air, strong_air, tubularity, network, endpoint, component_point))
    recovered = labels == main_label
    recovered |= high_mask
    before_gap = float(lesion_tree.query(main_points.astype(float) * scale, k=1)[0].min())
    after_points = _cropped_skeleton(recovered) if high_mask.any() else main_points
    after_gap = float(lesion_tree.query(after_points.astype(float) * scale, k=1)[0].min())
    queries.append((lesion_points, main_points, lesion_tree.query(main_points.astype(float) * scale, k=1)[0]))
    if distance_provider is not None:
        # A comparison backend cannot silently change tie-breaking or thresholds.
        distance_provider(queries, scale)
    summary = dict(input_component_count=int(count), evaluated_candidates=len(candidates),
        high_confidence_candidates=sum(c.classification == 'high' for c in candidates),
        review_candidates=sum(c.classification == 'review' for c in candidates),
        rejected_candidates=sum(c.classification == 'rejected' for c in candidates),
        added_high_confidence_voxels=int(np.count_nonzero(high_mask & (labels != main_label))),
        review_voxels=int(np.count_nonzero(review_mask & (labels != main_label))),
        closest_centerline_to_lesion_before_mm=before_gap, closest_centerline_to_lesion_after_mm=after_gap,
        gap_improvement_mm=before_gap - after_gap,
        probability_source='network_probability' if probability is not None else 'multi_evidence_without_network_probability',
        high_confidence_threshold=float(high_threshold), review_threshold=float(review_threshold),
        warning='Experimental recovery candidates; review against CT before use.')
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return recovered, high_mask, review_mask, candidates, dict(summary=summary, evidence=evidence,
        backend='PS_ROI_sparse_same_rules', total_seconds=time.perf_counter() - begin,
        comparison_queries=queries)
