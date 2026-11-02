"""Exercise the real HDMI GUI and drain all workers before restoring the UI."""
from pathlib import Path
import fcntl,hashlib,json,os,signal,subprocess,sys,time,traceback
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
PRODUCTION=ROOT/'ui/production_r1';C=ROOT/'ui/releases/feature_completion_r6'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,r):
    p=HERE/'results'/n;assert not p.exists();p.write_text(json.dumps(r,indent=2)+'\n')
def free_lock():
    with open('/tmp/kv260-ct-pl.lock','rb') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
def restore_graphics():
    sys.path.insert(0,str(ROOT/'dfx/edt_volume'))
    from volume_runtime import VolumeSession
    with VolumeSession(experimental=False) as session:session.return_to_scope()
def drain(pid):
    os.kill(pid,signal.SIGTERM)
    for _ in range(900):
        if not Path(f'/proc/{pid}').exists():return
        time.sleep(.2)
    raise RuntimeError('Verified UI did not drain; no forced stop')
def sample_tree(pid):
    rows={}
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            s=dict(line.split(':',1) for line in (p/'status').read_text().splitlines() if ':' in line)
            rows[int(p.name)]=dict(parent=int(s['PPid']),RSS_KiB=int(s.get('VmRSS','0 kB').split()[0]),
                argv=[v.decode(errors='replace') for v in (p/'cmdline').read_bytes().split(b'\0')[:-1]])
        except (FileNotFoundError,ProcessLookupError,PermissionError):pass
    selected={pid}
    while True:
        more={p for p,r in rows.items() if r['parent'] in selected}
        if more<=selected:break
        selected|=more
    return {str(p):rows[p] for p in selected if p in rows}
def main():
    assert os.geteuid()==0;sys.path.insert(0,str(PRODUCTION))
    from verify_release_r13 import verify
    old=verify('ui/active_release.json')
    state=json.loads((ROOT/'results/profile_R3_host_board_state_r1.json').read_text())
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip();assert boot==state['boot_id']
    pid=state['PID'];expected=old['binary'].encode()+b'\0--root\0'+str(ROOT).encode()+b'\0'
    assert Path(f'/proc/{pid}/cmdline').read_bytes()==expected
    assert sha(Path(f'/proc/{pid}/exe'))==old['UI_build']['binary_sha256']
    build=json.loads((C/'build_media_r4/build.json').read_text())
    for key in ('source_sha256','shared_source_sha256'):
        for n,d in build[key].items():assert sha(ROOT/n)==d,n
    assert sha(C/'build_media_r4/medical_ui')==build['binary_sha256']
    assert sha(Path('/usr/bin/ffmpeg'))==build['ffmpeg_sha256']
    save('native_UI_started_r4.json',dict(PID=os.getpid(),old_UI_PID=pid,boot_id=boot,source_sha256=sha(Path(__file__))))
    env={k:v for k,v in os.environ.items() if not k.startswith('KV260_')};env['PYTHONIOENCODING']='utf-8'
    stopped=False;error=None;trials=[];memory={};aggregate=0;samples=0
    try:
        drain(pid);stopped=True;free_lock();restore_graphics()
        for name,flag,filename in [('media','KV260_MEDIA_UI_TEST','navigation_media_UI.json'),
                                   ('depth','KV260_FAST_OPACITY_TEST','fast_opacity_UI.json')]:
            evidence=C/'evidence_media_r4'/name;assert not evidence.exists()
            with (HERE/'results'/('native_UI_'+name+'_r4.log')).open('xb') as log:
                child=subprocess.Popen(['bash','ui/releases/feature_completion_r6/run_media_r4.sh','--input',
                    str(ROOT/'fixtures/own_ct/CT-chest.nrrd'),'--evidence',str(evidence)],cwd=ROOT,
                    env=dict(env,**{flag:'1'}),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
                while child.poll() is None:
                    if name=='media':
                        rows=sample_tree(child.pid);aggregate=max(aggregate,sum(r['RSS_KiB'] for r in rows.values()));samples+=1
                        for p,r in rows.items():
                            item=memory.setdefault(p,dict(argv=r['argv'],peak_sampled_RSS_KiB=0))
                            item['peak_sampled_RSS_KiB']=max(item['peak_sampled_RSS_KiB'],r['RSS_KiB'])
                    time.sleep(.5)
            code=child.returncode;receipt=evidence/filename;r=json.loads(receipt.read_text())
            assert code==0,(name,code,r)
            if name=='media':
                assert r['status']=='passed_actual_GUI_single_and_linked_full_route_video_cancel_failure_view_restore'
                entries=r['exports'];assert [x['status'] for x in entries]==['setup_cancelled','completed','completed','cancelled','failed']
                assert entries[0]['camera_unchanged']
                assert all(x['restored'] and x['restored_camera']==r['before']['camera'] for x in entries[1:])
                assert all(x['restored_quality']==r['before']['quality'] and x['restored_dual']==r['before']['dual'] for x in entries[1:])
                assert entries[3]['cancel_requested_while_awaiting_PL']
                assert not entries[1]['cancel_requested_while_awaiting_PL'] and not entries[4]['cancel_requested_while_awaiting_PL']
                assert not entries[1]['linked_overview_enabled'] and entries[2]['linked_overview_enabled']
                assert all(x['overview_restored'] and x['restored_overview_camera']==r['before']['overview_camera'] for x in entries[1:])
                report=json.loads((Path(entries[2]['directory'])/'report.json').read_text())
                assert report['native_GUI_button'] and report['completed_PL_frames']==report['expected_route_frames']
                assert report['UI_ticks_during_export']>report['wall_seconds']*5
                assert not report['new_bitstream'] and report['additional_PL_resources']==0
            else:
                assert r['status']=='passed' and r['failed_cases']==0 and len(r['cases'])==48
                assert r['opacity_cache_passed'] and r['camera_invalidates_cache']
            trials.append(dict(name=name,receipt=receipt.relative_to(ROOT).as_posix(),sha256=sha(receipt)))
            print('completed',name,'status',r['status'],flush=True)
            free_lock();restore_graphics()
        save('native_UI_memory_r4.json',dict(status='observed_actual_native_GUI_export_subtree',samples=samples,
            sampling_interval_seconds=.5,max_sampled_simultaneous_process_RSS_MiB=aggregate/1024,
            aggregate_is_sampled_not_continuous_peak=True,per_process=memory,source_sha256=sha(Path(__file__))))
        save('native_UI_summary_r4.json',dict(status='passed_actual_HDMI_single_linked_native_video_and_R4_depth_cache_regression',
            trials=trials,source_sha256=sha(Path(__file__)),UI_binary_sha256=build['binary_sha256'],
            exact_worker_unchanged=True,medical_bitstream_changed=False))
    except Exception:
        error=traceback.format_exc();print(error,flush=True);save('native_UI_failed_r4.json',dict(error=error))
    finally:
        if stopped:
            free_lock();restore_graphics();verify('ui/active_release.json')
            with (HERE/'results/native_UI_restored_r4.log').open('xb') as log:
                child=subprocess.Popen(['bash','ui/run.sh'],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,
                    stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            time.sleep(8);assert child.poll() is None
            assert Path(f'/proc/{child.pid}/cmdline').read_bytes()==expected
            assert sha(Path(f'/proc/{child.pid}/exe'))==old['UI_build']['binary_sha256']
            save('native_UI_restored_r4.json',dict(PID=child.pid,boot_id=boot,UI_binary_sha256=old['UI_build']['binary_sha256'],
                original_manual_UI_restored=True,source_sha256=sha(Path(__file__))))
    save('native_UI_completed_r4.json',dict(exit_code=0 if error is None else 1,original_UI_restored=stopped))
    return 0 if error is None else 1
if __name__=='__main__':sys.exit(main())
