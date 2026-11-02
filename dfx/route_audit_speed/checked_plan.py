"""Existing prefix-query policy, using PL bend samples without PS recalculation."""
import numpy as np
from scipy.spatial import cKDTree
from protocol import validate_stored_audit
from navigation.planner import Target


def checked_plan(planner, target, minimum_bend_radius_mm=0., **options):
    threshold = float(minimum_bend_radius_mm)
    if not np.isfinite(threshold) or threshold < 0:
        raise ValueError('Invalid minimum bend radius')

    def plan(t):
        result = planner.plan(t, minimum_bend_radius_mm=threshold, **options)
        validate_stored_audit(result[1], result[0])
        br = result[1]['bend_radius_mm']
        violations = np.flatnonzero(br+1e-5 < threshold) if threshold else np.empty(0, int)
        return (*result, violations)

    report, route, camera, violations = plan(target)
    original = dict(report)
    retries = 0
    # Retain the existing policy: PS selects a preceding original centerline
    # endpoint; the complete replacement path/camera/audit is produced by PL.
    while len(violations) and retries < 8:
        before = max(0, int(violations[0])-2)
        ids, c = route['centerline_point_ids'], planner.c
        raw_arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(c.points_lps_mm[ids], axis=0), axis=1))] if len(ids) else np.empty(0)
        eligible = ids[raw_arc <= float(route['arc_mm'][before])*.8] if len(ids) else ids
        end = int(eligible[-1]) if len(eligible) else c.root
        report, route, camera, violations = plan(Target('manual_point', c.points_lps_mm[[end]], {}))
        retries += 1
    if len(violations):
        raise RuntimeError('PL bend-constrained prefix could not be verified')
    if retries:
        for key in ('target_kind', 'target', 'requested_endpoint_id', 'requested_endpoint_lps_mm', 'closest_centerline_gap_mm'):
            report[key] = original[key]
        p = route['points_lps_mm']
        report['final_target_gap_mm'] = float(cKDTree(target.points_lps_mm).query(p[-1])[0]) if len(p) else None
        report['status'] = 'limited_reach' if len(p) > 1 else 'unreachable'
        report['reason'] = 'insufficient_bend_radius'
        report['warnings'].append('Bend limit stopped the approach before the first unverified turn')
    computation = 'PL discrete geometry' if report['route_audit']['backend'] == 'pl' else 'CPU native HLS model'
    report.update(bend_constraint_enabled=threshold > 0, bend_constraint_passed=True,
                  bend_audit=computation+'; PS prefix-query policy', bend_prefix_queries=retries)
    return report, route, camera
