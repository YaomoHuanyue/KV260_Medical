"""Actual completed C9 pose envelope consumed by native Qt and linked cameras."""
import numpy as np


def completed_frame(plan, view, frame, normal, scalar_sha, request, **timing):
    for key in ('width', 'height', 'sequence'):
        if view[key] != plan[key]:
            raise ValueError('Renderer and completed frame disagree: '+key)
    f, u, r = [np.asarray(view[key], float) for key in ('forward_lps', 'up_lps', 'right_lps')]
    if (any(v.shape != (3,) for v in (f, u, r)) or not np.isfinite([f, u, r]).all()
            or not np.allclose(np.cross(f, u), r, atol=1e-9, rtol=0)
            or not np.allclose([np.linalg.norm(v) for v in (f, u, r)], 1, atol=1e-9, rtol=0)):
        raise ValueError('Invalid completed normalized camera basis')
    expected_f = np.asarray(plan['forward'], float); expected_f /= np.linalg.norm(expected_f)
    expected_u = np.asarray(plan['up'], float); expected_u -= expected_f*np.dot(expected_u, expected_f)
    expected_u /= np.linalg.norm(expected_u)
    if not np.allclose([f, u], [expected_f, expected_u], atol=1e-9, rtol=0):
        raise ValueError('Completed camera was replaced by another orientation')
    if not isinstance(scalar_sha, str) or len(scalar_sha) != 64:
        raise ValueError('Scalar identity required')
    return dict(view, revision=plan['revision'], camera_lps=plan['camera'], arc_mm=plan['arc_mm'],
                pose_source='completed_PL_frame', requested_camera=request,
                path=str(frame), normal_frame_path=str(normal), normal_computation='PL',
                normal_backend='PL_C9', pl_module='surface_quality',
                branch_event=plan['branch_event'], hud=plan['hud'], hud_point=plan['hud_point'],
                renderer_scalar_sha256=scalar_sha, interactive=bool(request.get('interactive', False)),
                **timing)
