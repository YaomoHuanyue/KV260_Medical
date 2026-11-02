"""Isolated protocol-3 adapter; never used by the live UI until board acceptance."""
from pathlib import Path
import hashlib
import sys
import time
import numpy as np

SYSTEM = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SYSTEM / 'modules/navigation'))
from pl.route_runtime import RoutePlanner, encode_query, POINTS, NODES

AUDIT_TAG = 0x4155444954303031
AUDIT_FIELDS = ('bend_radius_mm', 'forward_adjusted_radius_mm',
                'forward_minimum_bend_radius_mm', 'spare_radius_mm', 'clearance_state')


def encode_audited_query(target, token, *, minimum_bend_radius_mm=0.,
                         forward_window_mm=10., **options):
    threshold, window = float(minimum_bend_radius_mm), float(forward_window_mm)
    if not np.isfinite([threshold, window]).all() or min(threshold, window) < 0:
        raise ValueError('Audit threshold and window must be finite and nonnegative')
    data = encode_query(target, token, **options)
    data[0, 6] = AUDIT_TAG
    data.view(np.float64)[1, 5:7] = threshold, window
    return data


def route_digest(route):
    """Bind stored PL statistics to the exact route geometry and radii."""
    digest = hashlib.sha256()
    for name, dtype in [('points_lps_mm', '<f8'), ('arc_mm', '<f8'), ('radius_mm', '<f4')]:
        digest.update(np.ascontiguousarray(route[name], dtype=dtype).tobytes())
    return digest.hexdigest()


def decode_audited_route(output, stats, c, target, *, scope_diameter_mm=1.,
                         safety_margin_mm=.2, minimum_bend_radius_mm=0.,
                         forward_window_mm=10.):
    if output.dtype != np.uint64 or output.ndim != 2 or output.shape[1] != 8 or len(output) < 2:
        raise ValueError('Invalid route output buffer')
    error = int(output[0, 0]) | int(stats['status'])
    if error:
        if error & 8:
            raise ValueError('Manual target is more than 5 mm from the centerline')
        raise RuntimeError('PL route protocol/capacity error ' + str(error))
    _, n, nids, desired, end, reason, reachable, smooth = map(int, output[0])
    v = output.view(np.float64)
    if v[1, 6] != 3.:
        raise ValueError('Expected audited protocol 3; legacy output has no PL statistics')
    offset = 2 + (nids + 7) // 8
    if n > POINTS or nids > NODES or offset + 2*n > len(output):
        raise ValueError('Invalid audited route lengths')
    if desired >= len(c.points_lps_mm) or reason not in range(5):
        raise ValueError('Invalid route endpoint/reason')
    rows = v[offset:offset + 2*n].reshape(n, 2, 8)
    route = dict(points_lps_mm=rows[:, 0, :3].copy(), arc_mm=rows[:, 0, 3].copy(),
                 radius_mm=rows[:, 0, 4].astype(np.float32),
                 centerline_point_ids=output[2:offset].ravel()[:nids].astype(np.int32))
    if np.any(route['centerline_point_ids'] < 0) or np.any(route['centerline_point_ids'] >= len(c.points_lps_mm)):
        raise ValueError('Invalid route centerline IDs')
    if not np.isfinite(v[1, :6]).all() or np.any(v[1, :6] < 0):
        raise ValueError('Invalid PL route summary')
    if not np.isfinite(np.r_[rows[:, 0, 5:8].ravel(), rows[:, 1, :3].ravel()]).all():
        raise ValueError('Invalid PL camera geometry')
    for j, name in enumerate(AUDIT_FIELDS):
        route[name] = rows[:, 1, 3+j].copy()
    geometry = np.r_[route['points_lps_mm'].ravel(), route['arc_mm'], route['radius_mm']]
    if not np.isfinite(geometry).all() or np.any(route['radius_mm'] < 0) or np.any(np.diff(route['arc_mm']) < 0):
        raise ValueError('Invalid PL route geometry')
    required, margin = map(float, v[1, 4:6])
    if not np.isfinite([required, margin]).all() or min(required, margin) < 0:
        raise ValueError('Invalid PL clearance parameters')
    stats.update(useful_output_words=offset + 2*n, useful_output_bytes=(offset + 2*n)*64,
                 edge_cache_reused=bool(v[1, 7]))
    actual = stats['kind'] == 'actual_kv260'
    reasons = {0: None, 1: 'disconnected_target_component', 2: 'insufficient_root_clearance',
               3: 'insufficient_route_clearance', 4: 'continuous_route_clearance_failed'}
    why = reasons[reason]
    status = ('limited_reach' if why and n > 1 else 'unreachable') if why else (
        'airway_approach' if target.kind == 'lesion_candidate' else 'route_found')
    minimum = float(v[1, 1]) if n else None
    finite_bends = route['bend_radius_mm'][np.isfinite(route['bend_radius_mm'])]
    min_bend = float(finite_bends.min()) if len(finite_bends) else None
    report = dict(schema='kv260.navigation.route.v1', backend='pl_route' if actual else 'native_route_model',
                  status=status, reason=why, target_kind=target.kind, target=target.metadata,
                  requested_endpoint_id=desired, selected_endpoint_id=end if end < len(c.points_lps_mm) else None,
                  requested_endpoint_lps_mm=c.points_lps_mm[desired].tolist(),
                  closest_centerline_gap_mm=float(v[1, 2]), final_target_gap_mm=float(v[1, 3]) if n else None,
                  length_mm=float(v[1, 0]), point_count=n, minimum_edt_radius_mm=minimum,
                  minimum_adjusted_radius_mm=max(0., minimum-margin) if n else None,
                  scope_diameter_mm=float(scope_diameter_mm), safety_margin_mm=float(safety_margin_mm),
                  required_radius_mm=required, resolution_margin_mm=margin,
                  minimum_bend_radius_mm=float(minimum_bend_radius_mm),
                  forward_window_mm=float(forward_window_mm),
                  measured_minimum_bend_radius_mm=min_bend,
                  max_discrete_curvature_per_mm=1./min_bend if min_bend is not None else 0.,
                  curvature_definition='reciprocal of discrete bend radius; turns <= 1e-6 rad omitted',
                  reachable_centerline_points=reachable, total_centerline_points=len(c.points_lps_mm),
                  smoothing_accepted=bool(smooth), quality_status='experimental_geometry_only',
                  warnings=list(c.metadata.get('warnings', [])),
                  planning_mode='clearance_estimate' if required > 0 else 'virtual_point_exploration',
                  target_points_lps_mm=target.points_lps_mm.tolist() if target.kind != 'lesion_candidate' else [],
                  pl_job=stats, ps_remaining='target loading, prefix requery policy, report formatting and UI',
                  route_audit=dict(protocol=3, backend='pl' if actual else 'CPU native HLS model',
                                   route_sha256=route_digest(route), forward_window_mm=float(forward_window_mm),
                                   required_radius_mm=required, resolution_margin_mm=margin,
                                   minimum_bend_radius_mm=float(minimum_bend_radius_mm)))
    validate_stored_audit(route, report)
    if why:
        report['warnings'].append('Displayed route is the reachable approach only; requested endpoint was not reached')
    if target.kind == 'lesion_candidate':
        report['warnings'].append('Route ends inside airway near candidate; it does not reach an external lesion')
    camera = dict(position_lps_mm=route['points_lps_mm'].copy() if n > 1 else np.empty((0, 3)),
                  forward_lps=rows[:, 0, 5:8].copy() if n > 1 else np.empty((0, 3)),
                  up_lps=rows[:, 1, :3].copy() if n > 1 else np.empty((0, 3)))
    return report, route, camera


def validate_stored_audit(route, report):
    audit = report.get('route_audit', {})
    if audit.get('protocol') != 3 or audit.get('route_sha256') != route_digest(route):
        raise ValueError('PL audit belongs to a different route')
    for name in ('required_radius_mm', 'resolution_margin_mm', 'minimum_bend_radius_mm', 'forward_window_mm'):
        if audit.get(name) != report.get(name):
            raise ValueError('PL audit belongs to different instrument parameters')
    n = len(route['arc_mm'])
    values = [np.asarray(route[name]) for name in AUDIT_FIELDS]
    if any(value.shape != (n,) for value in values):
        raise ValueError('Invalid PL audit sample count')
    bends, minimum, forward_bend, spare, state = values
    for radius in (bends, forward_bend):
        if np.any(np.isnan(radius)) or np.any(radius <= 0):
            raise ValueError('Invalid PL bend radius')
    if not np.isfinite(np.r_[minimum, spare, state]).all() or np.any(minimum < 0):
        raise ValueError('Invalid PL clearance statistics')
    if not np.allclose(spare, minimum-report['required_radius_mm'], atol=1e-9, rtol=0):
        raise ValueError('Inconsistent PL spare radius')
    threshold = report['minimum_bend_radius_mm']
    expected = np.where((spare < -1e-5) | ((threshold > 0) & (forward_bend+1e-5 < threshold)),
                        2, np.where(spare < .4, 1, 0))
    if not np.array_equal(state, expected):
        raise ValueError('Inconsistent PL clearance state')


def hud_from_pl(route, report):
    """Format verified statistics; no CPU curvature/window-minimum computation."""
    validate_stored_audit(route, report)
    rows = []
    for r, minimum, bend, spare, state in zip(route['radius_mm'], route['forward_adjusted_radius_mm'],
                                             route['forward_minimum_bend_radius_mm'], route['spare_radius_mm'],
                                             route['clearance_state']):
        rows.append(dict(current_diameter_mm=float(2*r), forward_adjusted_diameter_mm=float(2*minimum),
                         spare_radius_mm=float(spare), forward_minimum_bend_radius_mm=float(bend) if np.isfinite(bend) else None,
                         state=('clear', 'caution', 'blocked')[int(state)]))
    return dict(lookahead_mm=report['route_audit']['forward_window_mm'], samples=rows,
                kind='segmentation_geometry_estimate', computation=report['route_audit']['backend'])


class AuditRoutePlanner(RoutePlanner):
    def plan(self, target, *, minimum_bend_radius_mm=0., forward_window_mm=10., **options):
        start = time.perf_counter()
        data = encode_audited_query(target, self.token, minimum_bend_radius_mm=minimum_bend_radius_mm,
                                    forward_window_mm=forward_window_mm, **options)
        output, stats = self.session.run_route(data, 1)
        result = decode_audited_route(output, stats, self.c, target,
                                      scope_diameter_mm=options.get('scope_diameter_mm', 1.),
                                      safety_margin_mm=options.get('safety_margin_mm', .2),
                                      minimum_bend_radius_mm=minimum_bend_radius_mm,
                                      forward_window_mm=forward_window_mm)
        result[0]['pl_job']['plan_adapter_total_seconds'] = time.perf_counter()-start
        return result
