"""Real own-CT cross-binding failures and interactive dispatch regressions."""
from pathlib import Path
import argparse
import copy
import json
import shutil
import sys
import tempfile
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.surface_route.prepare_bundles_r8 import load_case
from modules.surface_route.bundle_r8 import build_bundle, verify_bundle, sha, write_json, validate_geometry
from modules.surface_route.guidance_r5 import ScalarField
from modules.surface_route.scene_runtime_r8 import SceneSnapshot, LatestFrameQueue


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--root-only', type=Path, required=True)
    p.add_argument('--platform', choices=['Windows', 'ARM'], required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    checks = []

    def rejected(name, operation, error=ValueError):
        try:
            operation()
        except error as exc:
            checks.append(dict(name=name, passed=True, rejected=str(exc)))
        else:
            raise AssertionError('Did not reject: '+name)

    data = load_case('network_probability_high_ported', 1., a.platform)
    field = ScalarField(data['scalar'], data['geometry'], data['bits'])
    def geometry(**changes):
        args = dict(points=data['points'], faces=data['faces'], mesh_proof=data['mesh_proof'],
                    route=data['route'], report=data['report'], camera=data['camera'], guidance=data['guidance'])
        args.update(changes)
        return validate_geometry(field, **args)
    camera = {k: v.copy() for k, v in data['camera'].items()}
    camera['position_lps_mm'][2, 0] += .1
    rejected('cross_route_camera', lambda: geometry(camera=camera))
    guide = copy.deepcopy(data['guidance']); guide['scalar_sha256'] = '0'*64
    rejected('cross_scalar_guidance', lambda: geometry(guidance=guide))
    route = {k: v.copy() for k, v in data['route'].items()}; route['radius_mm'][0] += .1
    rejected('stale_route_audit', lambda: geometry(route=route))
    proof = dict(data['mesh_proof'], renderer_scalar_sha256='0'*64)
    rejected('cross_scalar_mesh', lambda: geometry(mesh_proof=proof))
    points = data['points'].copy(); points[0, 0] += .1
    rejected('changed_triangle_coordinates', lambda: geometry(points=points))
    with tempfile.TemporaryDirectory(prefix='kv260_complete_bundle_r8_') as temp:
        output = Path(temp)/'invalid'
        bad = dict(data, targets={})
        rejected('missing_exit_packet_no_publication', lambda: build_bundle(output, **bad))
        if output.exists() or list(Path(temp).iterdir()):
            raise AssertionError('Rejected input published partial files')
        tampered = Path(temp)/'tampered'
        shutil.copytree(a.bundle, tampered)
        file = tampered/'airway.vertices'
        with file.open('r+b') as stream:
            first = stream.read(1); stream.seek(0); stream.write(bytes([first[0]^1]))
        rejected('post_publication_payload_corruption', lambda: verify_bundle(tampered))
    scene = SceneSnapshot(a.bundle)
    rejected('wrong_expected_revision', lambda: verify_bundle(a.bundle, '0'*64))
    event = scene.guidance['events'][0]
    at = float(event['junction_arc_mm'])
    pose = scene.pose(at, 23., -8.)
    request = dict(revision=scene.revision, sequence=1, width=640, height=363, arc_mm=at,
                   camera=pose['position_lps_mm'], forward=pose['forward_lps'], up=pose['up_lps'])
    plan = scene.frame_plan(request)
    assert plan['branch_event'] == event['id']
    np.testing.assert_array_equal(plan['forward'], pose['forward_lps'])
    assert not np.allclose(plan['forward'], scene.pose(at)['forward_lps'])
    assert plan['hud']['current_diameter_mm'] == float(2*scene.route['radius_mm'][plan['hud_point']])
    checks.append(dict(name='actual_manual_camera_exit_and_HUD_single_revision', passed=True))
    rejected('stale_frame_revision', lambda: scene.frame_plan(dict(request, revision='0'*64)))
    rejected('invalid_AXIS_viewport', lambda: scene.frame_plan(dict(request, width=639)))
    rejected('nonfinite_progress', lambda: scene.frame_plan(dict(request, arc_mm=float('nan'))))
    rejected('unlinked_actual_camera_position', lambda: scene.frame_plan(dict(request, camera=[0., 0., 0.])))
    queue = LatestFrameQueue(scene)
    queue.submit(request); assert queue.take()['sequence'] == 1
    queue.submit(dict(request, sequence=2)); queue.submit(dict(request, sequence=3))
    assert queue.take() is None
    rejected('scene_switch_while_frame_inflight', lambda: queue.replace(scene), RuntimeError)
    rejected('wrong_completion_sequence', lambda: queue.finish(scene.revision, 2))
    assert queue.finish(scene.revision, 1) is False
    assert queue.take()['sequence'] == 3
    assert queue.finish(scene.revision, 3) is True
    rejected('repeated_sequence', lambda: queue.submit(dict(request, sequence=3)))
    queue.replace(scene); assert queue.pending is None and queue.last_sequence == -1
    checks.append(dict(name='latest_only_queue_discards_old_frames_and_drains_scene_switch', passed=True))
    root = SceneSnapshot(a.root_only)
    assert not root.guidance['events'] and len(root.scenes) == 1 and set(root.scenes) == {-1}
    rejected('root_only_camera_motion', lambda: root.pose(0.))
    checks.append(dict(name='root_only_has_no_false_forward_exit', passed=True))
    write_json(a.output, dict(status='complete_scene_binding_and_interactive_dispatch_tests_passed',
        cases=checks, count=len(checks), platform=a.platform, PL_access=False,
        source_sha256={n: sha(ROOT/n) for n in [
            'modules/surface_route/bundle_r8.py', 'modules/surface_route/prepare_bundles_r8.py',
            'modules/surface_route/scene_runtime_r8.py', 'modules/surface_route/test_bundle_r8.py']},
        bundle_sha256=sha(a.bundle/'scene.json'), root_bundle_sha256=sha(a.root_only/'scene.json')))
    print(len(checks), 'binding/dispatch checks passed', flush=True)


if __name__ == '__main__':
    main()
