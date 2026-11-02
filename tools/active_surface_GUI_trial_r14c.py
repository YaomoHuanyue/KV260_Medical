"""Actual Qt controls, changed target, selected C9 frames and same-input replay."""
from pathlib import Path
import fcntl,json,os,subprocess,sys,traceback
from time import perf_counter
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json
from modules.surface_route.active_actions_r14 import verify_active_scene
from modules.surface_route.capabilities_r14c import prepare as prepare_capabilities
from modules.surface_route.scene_runtime_r9 import SceneSnapshot


def replay(actual,output):
    scene=verify_active_scene(actual['scene']);snap=SceneSnapshot(scene['complete_surface']['bundle'])
    frame=actual['actual_PL_frame'];request=dict(frame['requested_camera']);request['revision']=snap.revision
    plan=snap.frame_plan(request);assert plan['branch_event']==frame['branch_event']
    helper=ROOT/'dfx/surface/prepare.py';encoder={'__file__':str(helper),'__name__':'active_R14_GUI_frame_encoder'}
    exec(compile(helper.read_text(encoding='utf-8'),str(helper),'exec'),encoder)
    params,_=encoder['frame_parameters'](plan['camera'],plan['forward'],plan['up'],snap.meta['geometry'],np.zeros(3),
        request['width'],request['height'],request['sequence'])
    sys.path.insert(0,str(ROOT/'dfx/surface_quality'))
    from quality_runtime import QualitySession,PSReference
    samples=[]
    with QualitySession() as session:
        upload=session.load(plan['scene']);cpu=PSReference(plan['scene']);expected,one=cpu.render(params,1)
        for repeat in range(3):
            start=perf_counter();software,seconds=cpu.render(params,4);ps=perf_counter()-start
            np.testing.assert_array_equal(software,expected)
            start=perf_counter();hardware,timing=session.render(params);pl=perf_counter()-start
            np.testing.assert_array_equal(hardware,expected)
            assert timing['four_4096_byte_DMA_guards_passed'] and timing['input_and_tokens_checked']
            samples.append(dict(PS4_full_call_seconds=ps,PL_full_API_seconds=pl,PL_job=timing))
    hardware.tofile(output/'replayed_actual_UI_PL.u64');params.tofile(output/'replayed_actual_UI_request.i32')
    ps=float(np.median([s['PS4_full_call_seconds'] for s in samples]));pl=float(np.median([s['PL_full_API_seconds'] for s in samples]))
    assert ps>pl
    return dict(width=request['width'],height=request['height'],sequence=request['sequence'],branch_event=plan['branch_event'],
        revision=snap.revision,all_depth_normal_target_outline_words_exact_PS1_PS4_actual_PL=True,
        actual_manual_UI_camera_replayed=True,PS4_median_seconds=ps,PL_median_seconds=pl,PL_over_PS4_speedup=ps/pl,
        upload=upload,samples=samples,PL_pixels_sha256=sha(output/'replayed_actual_UI_PL.u64'),
        full_static_1MiB_echo_and_C6_restore_passed=True)


def main():
    checkpoint=json.loads((ROOT/'modules/surface_route/work_checkpoint_r13.json').read_text());boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert boot==checkpoint['current_board_state']['boot_id']
    for n,h in checkpoint['current_board_state']['preserved_defaults_sha256'].items():assert sha(ROOT/n)==h,n
    for p in Path('/proc').iterdir():
        try:
            if p.name.isdigit() and (p/'comm').read_text().strip()=='medical_ui':raise RuntimeError('Another UI is active')
        except FileNotFoundError:pass
    with Path('/tmp/kv260-ct-pl.lock').open('rb') as lock:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    binary=ROOT/'ui/releases/feature_completion_r6/build_complete_scene_r14b/medical_ui';build=json.loads((binary.parent/'build.json').read_text())
    assert sha(binary)==build['binary_sha256']
    for n,h in build['source_sha256'].items():assert sha(ROOT/n)==h,n
    output=ROOT/'modules/surface_route/results/native_active_surface_GUI_ARM_r14c';output.mkdir(exist_ok=False)
    scene=ROOT/'modules/surface_route/results/native_scene_ARM_r9/network_probability_high_ported_bend_1p0/scene.json'
    scene=prepare_capabilities(scene,ROOT/'modules/surface_route/results/capability_scene_ARM_r14c')
    runtime=Path('/run/kv260-ui-runtime');runtime.mkdir(mode=0o700,exist_ok=True);runtime.chmod(0o700)
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),LD_PRELOAD='/usr/lib/aarch64-linux-gnu/mali/wayland/libMali.so.9.0',
        QT_QPA_PLATFORM='eglfs',QT_QPA_EGLFS_INTEGRATION='eglfs_kms',QT_QPA_EGLFS_KMS_CONFIG=str(ROOT/'ui/kms.json'),
        QT_QPA_EGLFS_KMS_ATOMIC='0',QT_QPA_EGLFS_FORCE888='1',KV260_SCOPE_MODULE='surface',
        KV260_COMPLETE_SCENE=str(scene),KV260_ACTIVE_SURFACE_UI_TEST='1',OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8')
    for name in ('KV260_COMPLETE_SCENE_GUI_TEST','KV260_SELECTED_PATH_UI_TEST','KV260_WHOLE_COMPARISON_UI_TEST'):env.pop(name,None)
    argv=[str(binary),'--root',str(ROOT),'--input',str(ROOT/'fixtures/own_ct/CT-chest.nrrd'),'--evidence',str(output)]
    try:
        with (output/'UI.log').open('xb') as log:
            process=subprocess.Popen(argv,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
            write_json(output/'started.json',dict(PID=process.pid,argv=argv,boot_id=boot,binary_sha256=sha(binary)))
            code=process.wait()
        actual=json.loads((output/'active_surface_UI.json').read_text());assert code==0 and actual['status']=='passed_actual_Qt_active_comparison_selected_path_C9_manual_camera_and_linked_reference'
        assert all(row['passed'] for row in actual['checks'])
        result=replay(actual,output)
        assert boot==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        assert Path('/run/kv260-dfx-medical-loaded.sha256').read_text().strip()==checkpoint['current_board_state']['medical_shell_marker_sha256']
        for n,h in checkpoint['current_board_state']['preserved_defaults_sha256'].items():assert sha(ROOT/n)==h,n
        with Path('/tmp/kv260-ct-pl.lock').open('rb') as lock:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        active=verify_active_scene(actual['scene']);active_root=Path(actual['scene']).parent.parent
        comparison=Path(active['complete_surface']['comparison']['receipt']).parent.parent
        files={p.relative_to(ROOT).as_posix():sha(p) for folder in {output,active_root,comparison} for p in folder.rglob('*') if p.is_file()}
        write_json(output/'acceptance.json',dict(status='actual_HDMI_current_surface_comparison_target_change_selected_C9_and_PS_PL_replay_passed',
            actual_UI=actual,replayed_actual_UI_frame=result,boot_id=boot,production_promoted=False,new_bitstream=False,
            source_closure_sha256=build['source_closure_sha256'],adapter_closure_sha256=sha(ROOT/'modules/surface_route/native_UI_source_closure_r14c.json'),UI_binary_sha256=sha(binary),test_source_sha256=sha(Path(__file__)),
            physical_user_review=False,evidence_sha256=files));print('R14 actual UI and same-input replay passed',flush=True)
    except BaseException as error:write_json(output/'failure.json',dict(error=str(error),traceback=traceback.format_exc()));raise


if __name__=='__main__':main()
