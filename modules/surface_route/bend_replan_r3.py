"""Original bend-prefix policy on freshly reviewed replacement-surface routes.

The archived optimized native audit is a PS baseline. Injecting an actual C4
auditor changes only bend/window statistics, never the physical-wall planner.
"""
from pathlib import Path
import ctypes
import hashlib
import sys
import numpy as np
from .audit import round_down_float32
from .replan_r1 import replan

SYSTEM = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SYSTEM/'modules/navigation'))
sys.path.insert(0, str(SYSTEM/'dfx/route_audit_speed'))
from dfx.route_audit_speed.protocol import AUDIT_FIELDS, route_digest, validate_stored_audit
from dfx.route_audit_speed.checked_plan import checked_plan as original_checked_plan

SHA = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
LIBRARIES = {
    'win32': ('build/audit_reference.dll', '69ed15a767d1a9e0998f463b6dc21f597cfe18bb36614a9102c4ed9d625fac78'),
    'linux': ('host/libaudit_reference.so', '0b763dc0fc69809fedbdc0f97471e584277583c8a62b3aff3e076f049411863a'),
}


class NativeAuditor:
    backend = 'optimized_PS_native_archived_float64_atan'

    def __init__(self):
        relative, digest = LIBRARIES[sys.platform]
        self.library = SYSTEM/'dfx/route_audit/archive/float_atan_r1'/relative
        if SHA(self.library) != digest:
            raise ValueError('Native audit baseline changed')
        self.lib = ctypes.CDLL(str(self.library))
        self.lib.audit_native.argtypes = [ctypes.c_void_p]*3+[ctypes.c_uint]+[ctypes.c_double]*4+[ctypes.c_void_p]
        self.lib.audit_native.restype = ctypes.c_int

    def __call__(self, points, arcs, radii, parameters):
        p, a, r, v = audit_input(points, arcs, radii, parameters)
        out = np.empty((len(p), 5), np.float64)
        code = self.lib.audit_native(p.ctypes.data, a.ctypes.data, r.ctypes.data,
                                     len(p), *v, out.ctypes.data)
        if code:
            raise ValueError('Native audit rejected input: '+str(code))
        return out


def audit_input(points, arcs, radii, parameters):
    p = np.ascontiguousarray(points, '<f8')
    a = np.ascontiguousarray(arcs, '<f8')
    r = np.ascontiguousarray(radii, '<f4')
    v = np.asarray(parameters, np.float64)
    if (p.shape != (len(a), 3) or a.ndim != 1 or r.shape != a.shape
            or len(a) > 4096 or v.shape != (4,)
            or not np.isfinite(np.r_[p.ravel(), a, r, v]).all()
            or np.any(r < 0) or np.any(np.diff(a) < 0) or np.any(v < 0)):
        raise ValueError('Invalid bounded physical audit inputs')
    return p, a, r, v.tolist()


class SurfaceBendPlanner:
    def __init__(self, centerline, region, oracle, auditor=None):
        self.c, self.region, self.oracle = centerline, region, oracle
        self.auditor = auditor if auditor is not None else NativeAuditor()
        self.history = []

    def plan(self, target, *, minimum_bend_radius_mm=0., forward_window_mm=10., **options):
        threshold, window = float(minimum_bend_radius_mm), float(forward_window_mm)
        if not np.isfinite([threshold, window]).all() or min(threshold, window) < 0:
            raise ValueError('Finite nonnegative bend threshold/window required')
        # The unchanged base planner reviews every node, edge and smoothed
        # curve again, including every prefix query chosen by the old policy.
        report, route, camera, diagnostics = replan(self.c, target, self.region,
            self.oracle, minimum_bend_radius_mm=0., **options)
        curve = diagnostics['curve_audit']
        actual = route['radius_mm'].copy()
        conservative = np.maximum(0., curve['effective_distance_mm']-1e-6)
        bounds = curve.get('accepted_lower_bound_mm', np.empty(0))
        if len(bounds):
            conservative[:-1] = np.minimum(conservative[:-1], bounds)
            conservative[1:] = np.minimum(conservative[1:], bounds)
        route['actual_wall_distance_mm'] = actual
        route['radius_mm'] = round_down_float32(conservative)
        report.update(minimum_bend_radius_mm=threshold, forward_window_mm=window,
            nonzero_bend_prefix_policy_integration_pending=False,
            requested_endpoint_lps_mm=self.c.points_lps_mm[report['requested_endpoint_id']].tolist(),
            warnings=list(self.c.metadata.get('warnings', [])),
            radius_semantics='conservative float32 lower bound from actual triangle walls, crop planes and accepted continuous segments; actual_wall_distance_mm retained separately')
        values = [window, report['resolution_margin_mm'], report['required_radius_mm'], threshold]
        rows = np.asarray(self.auditor(route['points_lps_mm'], route['arc_mm'], route['radius_mm'], values))
        if rows.shape != (len(actual), 5) or rows.dtype != np.float64:
            raise ValueError('Invalid audit output shape/type')
        for i, name in enumerate(AUDIT_FIELDS):
            route[name] = rows[:, i].copy()
        report['route_audit'] = dict(protocol=3, backend=self.auditor.backend,
            route_sha256=route_digest(route), forward_window_mm=window,
            resolution_margin_mm=report['resolution_margin_mm'],
            required_radius_mm=report['required_radius_mm'], minimum_bend_radius_mm=threshold)
        validate_stored_audit(route, report)
        finite = route['bend_radius_mm'][np.isfinite(route['bend_radius_mm'])]
        report['measured_minimum_bend_radius_mm'] = float(finite.min()) if len(finite) else None
        self.history.append(dict(target_kind=target.kind, target_points_lps_mm=target.points_lps_mm.copy(),
            report=report.copy(), route={k:v.copy() for k,v in route.items()},
            camera={k:v.copy() for k,v in camera.items()}, diagnostics=diagnostics))
        return report, route, camera


def checked_replan(planner, target, **options):
    """Call the source-bound original controller, retaining its 80%/8 rule."""
    planner.history = []
    report, route, camera = original_checked_plan(planner, target, **options)
    # The historic label treats every non-PL implementation as an HLS model.
    # This adapter is a physical-wall PS planner with injected audit statistics.
    report['bend_audit'] = planner.auditor.backend+'; unchanged original PS prefix-query policy'
    report['prefix_query_policy'] = dict(source='dfx/route_audit_speed/checked_plan.py',
        source_sha256=SHA(SYSTEM/'dfx/route_audit_speed/checked_plan.py'),
        first_violation_preceding_samples=2, preceding_original_arc_fraction=.8,
        maximum_requeries=8, geometry_and_camera_rebuilt_for_each_query=True)
    report['query_trace'] = [dict(target_kind=x['target_kind'],
        requested_endpoint_id=x['report']['requested_endpoint_id'],
        selected_endpoint_id=x['report']['selected_endpoint_id'],
        point_count=len(x['route']['arc_mm']), length_mm=x['report']['length_mm'],
        bend_violations=int(np.count_nonzero(x['route']['bend_radius_mm']+1e-5 < report['minimum_bend_radius_mm'])))
        for x in planner.history]
    report['bend_scope'] = 'original sampled discrete-turn estimate; not continuous-curvature or instrument-contact certification'
    validate_stored_audit(route, report)
    return report, route, camera
