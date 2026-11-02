"""Actual C9 native GUI video, exact PS references, replay and review restore."""
from pathlib import Path
from time import monotonic,sleep
import fcntl,json,os,signal,subprocess,sys,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json
from modules.surface_route.quality_validation_r16 import verify_active_scene
from tools.surface_quality_trial_r16 import UI_environment
from tools.mesh_quality_recover_evidence_r17c import ready
from modules.navigation_media.test_native_UI_r4 import sample_tree
OUT=ROOT/'modules/navigation_media/results/active_C9_video_ARM_r18'

def free_lock():
    with Path('/tmp/kv260-ct-pl.lock').open('rb') as lock:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)

def close(record):
    pid=record['PID'];proc=Path(f'/proc/{pid}')
    assert proc.exists()
    assert (proc/'cmdline').read_bytes().rstrip(b'\0').split(b'\0')==[s.encode() for s in record['argv']]
    assert sha(proc/'exe')==record['binary_sha256']
    os.kill(pid,signal.SIGTERM);deadline=monotonic()+60
    while proc.exists() and monotonic()<deadline:
        # This supervisor's own child may have become a zombie; reap only it.
        try:
            done,_=os.waitpid(pid,os.WNOHANG)
            if done==pid:return
        except ChildProcessError:pass
        sleep(.25)
    if proc.exists():raise RuntimeError('Cooperative UI drain pending; no force stop')

def launch(scene,test=False,fallback=False):
    folder=OUT/('GUI' if test else 'fallback_review' if fallback else 'review');folder.mkdir(exist_ok=False)
    binary=ROOT/('ui/releases/feature_completion_r6/build_complete_scene_r17/medical_ui' if fallback else
        'ui/releases/feature_completion_r6/build_complete_scene_r18/medical_ui')
    build=json.loads((binary.parent/'build.json').read_text());assert sha(binary)==build['binary_sha256']
    for n,h in build['source_sha256'].items():assert sha(ROOT/n)==h,n
    argv=[str(binary),'--root',str(ROOT),'--input',str(ROOT/'fixtures/own_ct/CT-chest.nrrd'),'--evidence',str(folder)]
    env=UI_environment(scene)
    if test:env['KV260_MEDIA_UI_TEST']='1'
    with (folder/'UI.log').open('xb') as log:p=subprocess.Popen(argv,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,
        stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    record=dict(PID=p.pid,argv=argv,scene=str(scene),binary_sha256=sha(binary),
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),production_promoted=False,no_automatic_startup=True)
    write_json(folder/'started.json',record)
    return p,folder,record

def main():
    assert os.geteuid()==0
    parent=json.loads((ROOT/'modules/surface_route/work_checkpoint_r17.json').read_text());state=parent['current_board_state']
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip();assert boot==state['boot_id']
    for n,h in state['preserved_defaults_sha256'].items():assert sha(ROOT/n)==h,n
    old=state['UI'];ready(old);scene=Path(old['scene']);verify_active_scene(scene)
    build=json.loads((ROOT/'ui/releases/feature_completion_r6/build_complete_scene_r18/build.json').read_text())
    assert sha(ROOT/'ui/releases/feature_completion_r6/build_complete_scene_r18/medical_ui')==build['binary_sha256']
    OUT.mkdir(exist_ok=False);closed=False;process=None;test_record=None;review=None;passed=False
    samples=0;peak=0;per_process={};replays=[];acceptances=[]
    try:
        close(old);closed=True;free_lock();write_json(OUT/'old_UI_closed.json',dict(record=old,signal='SIGTERM',forced=False))
        process,gui,test_record=launch(scene,True);begin=monotonic()
        while process.poll() is None:
            rows=sample_tree(process.pid);samples+=1;peak=max(peak,sum(r['RSS_KiB'] for r in rows.values()))
            for pid,r in rows.items():
                item=per_process.setdefault(pid,dict(argv=r['argv'],peak_sampled_RSS_KiB=0))
                item['peak_sampled_RSS_KiB']=max(item['peak_sampled_RSS_KiB'],r['RSS_KiB'])
            if monotonic()-begin>900:raise RuntimeError('Actual GUI trial exceeds budget; cooperative drain required')
            sleep(.5)
        actual=json.loads((gui/'navigation_media_UI.json').read_text())
        assert process.returncode==0 and actual['status']=='passed_actual_GUI_single_and_linked_full_route_video_cancel_failure_view_restore',actual
        entries=actual['exports'];assert [r['status'] for r in entries]==['setup_cancelled','completed','completed','cancelled','failed']
        assert entries[0]['camera_unchanged']
        for row in entries[1:]:
            assert row['restored'] and row['restored_camera']==actual['before']['camera']
            assert row['overview_restored'] and row['restored_overview_camera']==actual['before']['overview_camera']
            assert row['restored_quality']==actual['before']['quality'] and row['restored_dual']==actual['before']['dual']
        assert entries[3]['cancel_requested_while_awaiting_PL'] and not entries[4]['cancel_requested_while_awaiting_PL']
        write_json(OUT/'memory.json',dict(samples=samples,sampling_interval_seconds=.5,
            max_sampled_simultaneous_process_RSS_MiB=peak/1024,aggregate_is_sampled_not_continuous_peak=True,per_process=per_process))
        free_lock()
        for i,row in enumerate(entries[1:3]):
            directory=Path(row['directory']);assert directory.is_relative_to(ROOT/'ui/exports/navigation_media')
            argv=[str(ROOT/'.venv/bin/python'),'modules/navigation_media/verify_active_export_r18.py',str(directory)]
            with (OUT/f'verify_{i}.log').open('xb') as log:subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            acceptance=json.loads((directory/'acceptance.json').read_text());acceptances.append(dict(directory=str(directory),
                acceptance_sha256=sha(directory/'acceptance.json'),report_sha256=sha(directory/'report.json')))
            print('Full decode and PS1/PS4 exact completed',i,flush=True)
        from tools.active_surface_GUI_trial_r15 import replay
        report=json.loads((Path(entries[1]['directory'])/'report.json').read_text())
        refs=[r for r in report['frame_trace'] if 'reference_png' in r and not r['hold']]
        import numpy as np
        for i,row in enumerate(refs):
            folder=OUT/f'C9_{i}';folder.mkdir()
            result=replay(dict(scene=str(scene),actual_PL_frame=row['completed_frame']),folder)
            d=Path(entries[1]['directory']);m=row['completed_frame']
            expected=np.fromfile(d/m['depth_reference'],'<u4').astype(np.uint64)|(
                np.fromfile(d/m['normal_reference'],'<u4').astype(np.uint64)<<np.uint64(32))
            np.testing.assert_array_equal(np.fromfile(folder/'replayed_actual_UI_PL.u64','<u8'),expected)
            result['replay_equals_actual_saved_video_raw_words']=True
            write_json(folder/'acceptance.json',result);replays.append(result)
            print('Actual C9 replay exact, speedup',result['PL_over_PS4_speedup'],flush=True)
        free_lock();passed=True
    except BaseException as error:
        write_json(OUT/'failure.json',dict(error=str(error),traceback=traceback.format_exc()));raise
    finally:
        if closed:
            if process is not None and process.poll() is None:close(test_record);process.wait(timeout=5)
            free_lock();p,folder,review=launch(scene,fallback=not passed)
            sleep(3);ready(review,seconds=60)
            write_json(folder/'live.json',dict(review,status='manual_review_live_after_supported_prepare_drain'))
    for n,h in state['preserved_defaults_sha256'].items():assert sha(ROOT/n)==h,n
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
    assert Path('/run/kv260-dfx-medical-loaded.sha256').read_text().strip()==state['medical_shell_marker_sha256']
    write_json(OUT/'acceptance.json',dict(status='current_C9_single_linked_video_timeline_decode_PS1_PS4_PL_replay_cancel_failure_restore_passed',
        UI_receipt_sha256=sha(OUT/'GUI/navigation_media_UI.json'),exports=acceptances,actual_PL_replays=replays,current_UI=review,
        preserved_defaults_sha256=state['preserved_defaults_sha256'],medical_shell_marker_sha256=state['medical_shell_marker_sha256'],
        new_bitstream=False,production_promoted=False,static_shell_reload=False,driver_unload=False,
        physical_new_button_verified=False,whole_goal_completed=False,test_source_sha256=sha(Path(__file__))))
    print('R18 current C9 native video accepted and review restored',flush=True)
if __name__=='__main__':main()
