"""Same own-CT frame protocol tests on Windows and ARM; no PL access."""
from pathlib import Path
import argparse
import copy
import json
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.surface_route.scene_runtime_r9 import SceneSnapshot, LatestFrameQueue
from modules.surface_route.frame_protocol_r9 import completed_frame
from modules.surface_route.bundle_r8 import sha, write_json, arrays
from modules.surface_route.bundle_reader_r9 import validate_geometry
from modules.surface_route.guidance_r5 import ScalarField
from dfx.surface_quality.prepare import unpack_scene


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--platform', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checks = []
    def passed(name):
        checks.append(dict(name=name, passed=True))
    def rejected(name, action):
        try:
            action()
        except ValueError as error:
            checks.append(dict(name=name, passed=True, rejected=str(error)))
        else:
            raise AssertionError('Not rejected: '+name)
    snapshot = SceneSnapshot(args.bundle)
    helper = ROOT/'dfx/surface/prepare.py'
    encoder = {'__file__': str(helper), '__name__': 'isolated_R9_test_encoder'}
    exec(compile(helper.read_text(encoding='utf-8'), str(helper), 'exec'), encoder)
    requests = []
    distances = [0., snapshot.guidance['events'][0]['junction_arc_mm'], float(snapshot.route['arc_mm'][-1])]
    for sequence, distance in enumerate(distances, 1):
        pose = snapshot.pose(distance, 17., -6.)
        request = dict(revision=snapshot.revision, sequence=sequence, width=640, height=363,
                       arc_mm=float(np.float32(distance)), camera=np.asarray(pose['position_lps_mm'],np.float32).tolist(),
                       forward=np.asarray(pose['forward_lps'],np.float32).tolist(),
                       up=np.asarray(pose['up_lps'],np.float32).tolist(), interactive=True)
        plan = snapshot.frame_plan(request)
        params, view = encoder['frame_parameters'](plan['camera'], plan['forward'], plan['up'],
            snapshot.meta['geometry'], np.zeros(3), plan['width'], plan['height'], plan['sequence'])
        completed = completed_frame(plan, view, '/run/kv260-ui-runtime/pl_scope_123.rgba',
            '/run/kv260-ui-runtime/pl_scope_123.rgba.normal.rgba',
            snapshot.meta['renderer_scalar_sha256'], request)
        assert completed['camera_lps'] == request['camera']
        assert completed['normal_computation'] == 'PL' and completed['normal_backend'] == 'PL_C9'
        assert completed['pose_source'] == 'completed_PL_frame'
        assert 0 <= completed['arc_mm'] <= snapshot.route['arc_mm'][-1]
        assert completed['hud']['current_diameter_mm'] == 2*float(snapshot.route['radius_mm'][plan['hud_point']])
        requests.append(dict(request=request, frame=completed, encoded_parameters=params.tolist()))
        passed('Qt_float32_manual_pose_and_normal_pair_at_'+str(sequence))
    request = requests[-1]['request']
    rejected('genuine_progress_outside_route', lambda: snapshot.frame_plan(dict(request, arc_mm=distances[-1]+.001)))
    rejected('boolean_progress', lambda: snapshot.frame_plan(dict(request, arc_mm=True)))
    rejected('NaN_progress', lambda: snapshot.frame_plan(dict(request, arc_mm=float('nan'))))
    rejected('stale_revision', lambda: snapshot.frame_plan(dict(request, revision='0'*64)))
    rejected('wrong_actual_camera_position', lambda: snapshot.frame_plan(dict(request, camera=[0.,0.,0.])))
    plan = snapshot.frame_plan(request)
    _, view = encoder['frame_parameters'](plan['camera'], plan['forward'], plan['up'],
        snapshot.meta['geometry'], np.zeros(3), plan['width'], plan['height'], plan['sequence'])
    bad = copy.deepcopy(view);bad['forward_lps'] = (-np.asarray(view['forward_lps'])).tolist()
    rejected('renderer_replaced_actual_manual_orientation', lambda: completed_frame(plan,bad,'x','y','0'*64,request))
    rejected('renderer_wrong_sequence', lambda: completed_frame(plan,dict(view,sequence=999),'x','y','0'*64,request))
    rejected('renderer_wrong_dimensions', lambda: completed_frame(plan,dict(view,width=384),'x','y','0'*64,request))
    queue = LatestFrameQueue(snapshot)
    for seq in (11,12,13):queue.submit(dict(request,sequence=seq))
    assert queue.take()['sequence']==13 and queue.finish(snapshot.revision,13)
    passed('latest_pending_pose_and_scene_revision_queue')
    mesh=arrays(args.bundle/'mesh.npz');scalar,_=unpack_scene(snapshot.scenes[-1])
    field=ScalarField(scalar,snapshot.meta['geometry'],snapshot.meta['bits'])
    bad_camera={key:values.copy() for key,values in snapshot.camera.items()}
    bad_camera['up_lps']=bad_camera['up_lps'][:1]
    rejected('camera_axis_broadcast_shape', lambda: validate_geometry(field,mesh['points'],mesh['faces'],
        snapshot.meta['identity']['mesh_proof'],snapshot.route,snapshot.report,bad_camera,snapshot.guidance))
    output=dict(status='complete_scene_Qt_float32_actual_pose_protocol_passed', platform=args.platform,
        checks=checks,count=len(checks),requests=requests,revision=snapshot.revision,PL_access=False,
        source_sha256={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in [
            Path(__file__),ROOT/'modules/surface_route/bundle_reader_r9.py',
            ROOT/'modules/surface_route/scene_runtime_r9.py',ROOT/'modules/surface_route/frame_protocol_r9.py']})
    write_json(args.output,output)
    print(len(checks),'R9 pose/protocol checks passed',flush=True)


if __name__=='__main__':main()
