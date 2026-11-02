"""Whole raw-skeleton comparison and original all-node candidate reports.

The caller supplies a checked PS or PL profile provider. This module does not
load firmware and does not replace the separately audited navigation route.
"""
from pathlib import Path
import hashlib
import json
import math
import time
import numpy as np
import SimpleITK as sitk
from scipy.spatial import cKDTree
from profile_r1 import graph, report as profile_report
from candidates_r2 import candidates

HERE = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def context_graph(context):
    coordinates = context.indices_zyx - context.offset_zyx
    data = graph(coordinates, context.radii_mm, context.root,
                 context.geometry.spacing_xyz[::-1])
    image = sitk.Image(list(map(int, context.mask.shape[::-1])), sitk.sitkUInt8)
    image.SetSpacing(tuple(context.geometry.spacing_xyz))
    image.SetDirection(tuple(context.geometry.direction))
    image.SetOrigin(tuple(context.geometry.to_lps(context.offset_zyx.reshape(1, 3))[0]))
    return data, image


def json_record(record, index, scope_diameter_mm, safety_margin_mm, minimum_bend_radius_mm):
    bend_radius = float(record['minimum_bend_radius_mm'])
    required = scope_diameter_mm + 2. * safety_margin_mm
    eligible = (record['minimum_diameter_mm'] + 1e-6 >= required and
                (minimum_bend_radius_mm <= 0. or bend_radius + 1e-6 >= minimum_bend_radius_mm))
    return dict(candidate_id=index, end_zyx=list(record['end']),
        endpoint_xyz_mm=record['endpoint_xyz_mm'], gap_mm=record['gap_mm'],
        bend_radians=record['bend_radians'], path_length_mm=record['path_length_mm'],
        minimum_diameter_mm=record['minimum_diameter_mm'],
        minimum_bend_radius_mm=bend_radius if math.isfinite(bend_radius) else None,
        bend_radius_unbounded=math.isinf(bend_radius), score=record['score'],
        original_diameter_bend_eligible=bool(eligible),
        points_lps_mm=record['path_xyz'].tolist(), radius_mm=record['radii'].tolist())


def produce(context, target, provider, *, provider_kind, scope_diameter_mm=1.,
            safety_margin_mm=.2, minimum_bend_radius_mm=0., diameters=(1.2, 1.8, 2.8, 4.)):
    """Calculate every profile and path anew; keep raw cycles and original rules."""
    parameters = np.asarray([scope_diameter_mm, safety_margin_mm, minimum_bend_radius_mm], float)
    if not np.isfinite(parameters).all() or scope_diameter_mm <= 0 or min(parameters[1:]) < 0:
        raise ValueError('Invalid physical comparison parameters')
    diameters = np.asarray(sorted(set([float(scope_diameter_mm), *map(float, diameters)])), float)
    if not 1 <= len(diameters) <= 64 or not np.isfinite(diameters).all() or np.any(diameters <= 0):
        raise ValueError('Invalid comparison diameters')
    if provider_kind not in ('optimized_PS1', 'optimized_PS4', 'verified_PL_R1', 'PL_native_model_R2'):
        raise ValueError('Explicit checked profile provider required')
    start = time.perf_counter()
    data, image = context_graph(context)
    graph_seconds = time.perf_counter() - start
    begin = time.perf_counter()
    distances, parents = provider(data, diameters, float(safety_margin_mm), 2.)
    distances, parents = np.asarray(distances), np.asarray(parents)
    expected = (len(diameters), len(data.coordinates_zyx))
    if distances.dtype != np.float64 or distances.shape != expected or parents.shape != expected:
        raise ValueError('Complete FP64 raw-node profiles required')
    profile_seconds = time.perf_counter() - begin
    begin = time.perf_counter()
    profiles = profile_report(data, image, cKDTree(target.points_lps_mm), diameters, distances, parents)
    groups = []
    arrays = dict(diameters_mm=diameters, distances=distances, parents=parents,
                  raw_coordinates_zyx=data.coordinates_zyx, raw_rows=data.rows, raw_neighbors=data.neighbors)
    for i, diameter in enumerate(diameters):
        records, chosen, front = candidates(data, image, context.distance_mm, target.points_lps_mm,
            distances[i], parents[i], float(diameter), float(safety_margin_mm),
            minimum_bend_radius_mm=float(minimum_bend_radius_mm))
        rows = [json_record(record, j, float(diameter), float(safety_margin_mm),
                            float(minimum_bend_radius_mm)) for j, record in enumerate(records)]
        selected = next(j for j, record in enumerate(records) if record is chosen)
        # Stable endpoint identity connects the original Pareto metrics to full paths.
        lookup = {tuple(row['endpoint_xyz_mm']): row['candidate_id'] for row in rows}
        pareto = [dict(row, candidate_id=lookup[tuple(row['airway_endpoint_xyz_mm'])]) for row in front]
        groups.append(dict(scope_diameter_mm=float(diameter), candidate_count=len(rows),
                           selected_candidate_id=selected, candidates=rows, pareto=pareto))
        for j, record in enumerate(records):
            for key in ('path_xyz', 'path_zyx', 'radii'):
                arrays[f'profile_{i}_candidate_{j}_{key}'] = record[key]
    fields_seconds = time.perf_counter() - begin
    source_names = ('produce_r1.py', 'profile_r1.py', 'candidates_r2.py', 'path_rules_r1.py', 'pareto_r1.py')
    common = dict(schema='kv260.navigation.raw_comparison.v1',
        profile_backend=provider_kind, raw_nodes=len(data.coordinates_zyx),
        raw_undirected_edges=len(data.neighbors)//2, raw_cycles_preserved=True,
        input_sha256=context.metadata['input_sha256'], centerline_id=context.metadata['centerline_id'],
        target_kind=target.kind, target_metadata=target.metadata,
        safety_margin_mm=float(safety_margin_mm), minimum_bend_radius_mm=float(minimum_bend_radius_mm),
        scope_diameter_mm=float(scope_diameter_mm), radius_weight=2.,
        original_rules=dict(candidate_slack_mm=4., maximum_candidates=80, maximum_Pareto=8,
                            path_sample_mm=.8, gap_weight=8., bend_weight=8.),
        route_safety_certificate=False, audited_navigation_route_replaced=False,
        source_sha256={name: sha(HERE/name) for name in source_names},
        timing=dict(graph_seconds=graph_seconds, profile_seconds=profile_seconds,
                    candidate_and_report_seconds=fields_seconds, whole_API_seconds=time.perf_counter()-start))
    whole = dict(common, kind='original whole raw-skeleton instrument reachability', profiles=profiles)
    alternatives = dict(common, kind='original all-reachable-node candidates and Pareto alternatives', groups=groups)
    # Reject nonstandard JSON before attaching any result to the UI.
    json.dumps(whole, allow_nan=False)
    json.dumps(alternatives, allow_nan=False)
    return whole, alternatives, arrays


def save(output, whole, alternatives, arrays):
    output = Path(output)
    names = ('whole_instrument_profiles.json', 'whole_alternative_routes.json', 'whole_comparison_arrays.npz')
    if any((output/name).exists() for name in names):
        raise FileExistsError('Comparison evidence already exists')
    output.mkdir(parents=True, exist_ok=True)
    for name, value in zip(names[:2], (whole, alternatives)):
        (output/name).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n', encoding='utf-8')
    np.savez_compressed(output/names[2], **arrays)
    return {name: sha(output/name) for name in names}
