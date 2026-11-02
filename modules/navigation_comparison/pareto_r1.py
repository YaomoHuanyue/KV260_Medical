"""Stable Pareto report selection over independently audited route records.

This module does not calculate or certify paths. The route producer must supply
the complete candidate set; a table of eight nearest leaves is insufficient.
"""
import math
import numpy as np

KEYS = ('path_length_mm', 'gap_mm', 'bend_radians', 'minimum_diameter_mm')
FIELDS = (
    ('airway_endpoint_xyz_mm', 'endpoint_xyz_mm'),
    ('airway_to_lesion_gap_mm', 'gap_mm'),
    ('route_length_mm', 'path_length_mm'),
    ('route_turn_cost_radians', 'bend_radians'),
    ('minimum_route_diameter_mm', 'minimum_diameter_mm'),
    ('weighted_score', 'score'),
)


def select(records, limit=8):
    """Preserve original strict dominance, duplicate handling and stable order."""
    records = list(records)
    if not records:
        return []
    values = np.asarray([[record[key] for key in KEYS] for record in records], dtype=np.float64)
    if not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError('Route comparison metrics must be finite and nonnegative')
    for record in records:
        if not math.isfinite(float(record['score'])):
            raise ValueError('Weighted route score must be finite')
        endpoint = np.asarray(record['endpoint_xyz_mm'], dtype=np.float64)
        if endpoint.shape != (3,) or not np.isfinite(endpoint).all():
            raise ValueError('Route endpoint must contain three finite LPS coordinates')
    # Axis 0 is the possible dominator; axis 1 is the candidate. Wider is better.
    no_worse = np.all(values[:, None, :3] <= values[None, :, :3], axis=2)
    no_worse &= values[:, None, 3] >= values[None, :, 3]
    better = np.any(values[:, None, :3] < values[None, :, :3], axis=2)
    better |= values[:, None, 3] > values[None, :, 3]
    keep = np.flatnonzero(~np.any(no_worse & better, axis=0))
    front = [records[int(index)] for index in keep]
    front.sort(key=lambda record: (record['gap_mm'], record['path_length_mm'], record['bend_radians']))
    return [{output: record[source] for output, source in FIELDS}
            for record in front[:max(1, int(limit))]]
