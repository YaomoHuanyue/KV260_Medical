"""Exercise the actual Qt export button, then restore the accepted manual UI."""
from pathlib import Path
import argparse,fcntl,hashlib,json,os,signal,subprocess,sys,time,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];UI=ROOT/'ui/releases/feature_completion_r6'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())

def lock_free():
    with open('/tmp/kv260-ct-pl.lock','rb') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)

def restore_scope():
    sys.path.insert(0,str(ROOT/'dfx/edt_volume'));from volume_runtime import VolumeSession
    with VolumeSession(experimental=False) as s:s.return_to_scope()

def main():
    assert os.geteuid()==0
    p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);a=p.parse_args()
    out=HERE/'results/UI_r1';evidence=UI/'evidence_reports_r1';assert not out.exists() and not evidence.exists()
    state_path=(ROOT/a.state).resolve();source=(ROOT/a.source).resolve()
    assert state_path.is_relative_to(ROOT) and source.is_relative_to(ROOT)
    state=read(state_path);pid=state['PID'];boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert boot==state['boot_id']
    sys.path.insert(0,str(ROOT/'ui/production_r1'));from verify_release_r15 import verify
    release=verify('ui/active_release.json');argv=[release['binary'].encode(),b'--root',str(ROOT).encode()]
    assert Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')[:-1]==argv
    assert sha(Path(f'/proc/{pid}/exe'))==state['UI_binary_sha256']==release['UI_build']['binary_sha256']
    assert not Path(f'/proc/{pid}/task/{pid}/children').read_text().strip(),'Preserve an active GUI job'
    build=read(UI/'build_reports_r1/build.json')
    assert sha(UI/'build_reports_r1/medical_ui')==build['binary_sha256']
    for key in ('source_sha256','shared_source_sha256'):
        for n,d in build[key].items():assert sha(ROOT/n)==d,n
    sys.path.insert(0,str(ROOT));from modules.report_export.reports import validate
    ct=ROOT/'fixtures/own_ct/CT-chest.nrrd';snapshot=validate(source,sha(ct))
    assert snapshot['whole'] and snapshot['selected']
    out.mkdir();stopped=False;child=None;error=None;trials=[]
    env={k:v for k,v in os.environ.items() if not k.startswith('KV260_')}
    def save(name,data):
        path=out/name;assert not path.exists();path.write_text(json.dumps(data,indent=2)+'\n')
    try:
        save('started.json',dict(UI_PID=pid,boot_id=boot,source_sha256=sha(Path(__file__)),
            state_receipt=a.state.as_posix(),state_sha256=sha(state_path),candidate_binary_sha256=build['binary_sha256']))
        assert Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')[:-1]==argv
        assert sha(Path(f'/proc/{pid}/exe'))==state['UI_binary_sha256']
        os.kill(pid,signal.SIGTERM)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            try:current=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')[:-1]
            except (FileNotFoundError,ProcessLookupError):current=[]
            if current!=argv:stopped=True;break
            time.sleep(.1)
        assert stopped,'UI did not drain; no candidate test started'
        lock_free();restore_scope()
        for kind,flag in [('export','KV260_SURFACE_EXPORT_UI_TEST'),('depth','KV260_FAST_OPACITY_TEST')]:
            ev=evidence/kind
            options={flag:'1'}
            if kind=='export':options['KV260_COMPLETE_REPORTS_SOURCE']=str(source)
            start=time.perf_counter()
            with (out/(kind+'.log')).open('xb') as log:
                child=subprocess.Popen(['bash','ui/releases/feature_completion_r6/run_reports_r1.sh',
                    '--input',str(ct),'--evidence',str(ev)],cwd=ROOT,env=dict(env,**options),
                    stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
                code=child.wait()
            receipt=ev/('export_UI.json' if kind=='export' else 'fast_opacity_UI.json');result=read(receipt)
            assert code==0,(kind,code,result)
            if kind=='export':
                assert result['status']=='passed_actual_Qt_export_control_and_async_colored_bundle'
                assert result['source']==str(source) and result['heartbeat_ticks_during_export']>=2
                folder=Path(result['event']['path']);assert folder.is_relative_to(ROOT/'ui/exports')
                report=read(folder/'report.json');assert report['schema']=='kv260.export.v5'
                complete=read(folder/'reports/index.json')
                assert complete['full_profile_state']=='exported' and complete['selected_route_state']=='exported_with_original_audit'
                assert complete['profile_query_count']==len(snapshot['whole']['profiles'])
                assert complete['source_result_files_sha256']==snapshot['files']
                assert complete['chart']['reachable_rows']==[v for v in snapshot['whole']['profiles'] if v.get('reachable')]
                for name,digest in report['files'].items():assert sha(folder/name)==digest,name
                for name,digest in snapshot['files'].items():
                    assert sha(source/name)==digest
                    if name.startswith('navigation/') or name=='selected_pipeline.json':assert sha(folder/'reports'/name)==digest
                assert report['complete_reports_sha256']==sha(folder/'reports/index.json')
                assert read(folder/'catalogue_bundle_report.json')['schema']=='kv260.export.v4'
                assert read(folder/'surfaces/report.json')['status']=='completed'
            else:assert result['status']=='passed' and result['failed_cases']==0 and len(result['cases'])==48
            trials.append(dict(kind=kind,receipt=receipt.relative_to(ROOT).as_posix(),sha256=sha(receipt),
                elapsed_seconds=time.perf_counter()-start))
            print('Actual report UI test passed:',kind,flush=True);lock_free();restore_scope()
        save('acceptance.json',dict(status='actual_Qt_complete_report_bundle_export_and_48_opacity_cases_passed',
            trials=trials,binary_sha256=build['binary_sha256'],source_result_files_unchanged=True,
            new_bitstream=False,production_promoted=False,physical_mouse_verified=False))
    except Exception:
        error=traceback.format_exc();print(error,flush=True);save('failure.json',dict(error=error))
    finally:
        if stopped and (child is None or child.poll() is not None):
            lock_free();restore_scope();verify('ui/active_release.json')
            with (out/'restored.log').open('xb') as log:
                restored=subprocess.Popen(['bash','ui/run.sh'],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,
                    stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            time.sleep(4);assert restored.poll() is None
            assert Path(f'/proc/{restored.pid}/cmdline').read_bytes().split(b'\0')[:-1]==argv
            assert sha(Path(f'/proc/{restored.pid}/exe'))==state['UI_binary_sha256']
            assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
            save('restored.json',dict(status='accepted_R15_UI_and_C6_restored_after_report_UI_trial',PID=restored.pid,
                previous_UI_PID=pid,boot_id=boot,UI_binary_sha256=state['UI_binary_sha256'],
                default_descriptor_sha256=sha(ROOT/'ui/active_release.json'),manual_entry_sha256=sha(ROOT/'ui/run.sh'),
                no_static_reload_or_driver_unload=True))
            print('Accepted R15 UI restored PID',restored.pid,flush=True)
    if error:raise RuntimeError('Candidate test failed; logs retained')
if __name__=='__main__':main()
