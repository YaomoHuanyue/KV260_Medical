"""Strict indexed-color board trial, with current immutable UI restored."""
from pathlib import Path
import fcntl,hashlib,json,os,signal,subprocess,sys,time,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,r):
    p=HERE/name;assert not p.exists();p.write_text(json.dumps(r,indent=2)+'\n')
def free_lock():
    with open('/tmp/kv260-ct-pl.lock','rb') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
def main():
    assert os.geteuid()==0
    sys.path.insert(0,str(ROOT/'ui/production_r1'))
    from verify_release_r4 import verify
    release=verify('ui/active_release.json')
    state=json.loads((ROOT/'dfx/composite/medical/exact_speed_r21/state_after_isolated_trial.json').read_text())
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip();assert boot==state['boot_id']
    pid=state['PID'];expected=release['binary'].encode()+b'\0--root\0'+str(ROOT).encode()+b'\0'
    assert Path(f'/proc/{pid}/cmdline').read_bytes()==expected
    assert sha(Path(f'/proc/{pid}/exe'))==state['UI_binary_sha256']==release['UI_build']['binary_sha256']
    build=json.loads((HERE/'build.json').read_text())
    for key in ('source_sha256','shared_source_sha256','library_sha256'):
        for n,d in build[key].items():assert sha(ROOT/n)==d,n
    assert sha(HERE/'worker')==build['binary_sha256']
    save('trial_started.json',dict(PID=os.getpid(),boot_id=boot,UI_PID=pid,source_sha256=sha(Path(__file__))))
    env={k:v for k,v in os.environ.items() if not k.startswith('KV260_')};env['PYTHONIOENCODING']='utf-8'
    stopped=False;error=None;trials=[]
    try:
        os.kill(pid,signal.SIGTERM)
        for _ in range(900):
            if not Path(f'/proc/{pid}').exists():stopped=True;break
            time.sleep(.2)
        assert stopped,'UI did not drain; no forced DMA termination'
        free_lock()
        for name in ('screen.py','accept.py','test_RAM_transport.py','test_scene_change.py'):
            with (HERE/(name+'.log')).open('xb') as log:
                child=subprocess.Popen([str(ROOT/'.venv/bin/python'),str(HERE/name)],cwd=ROOT,env=env,
                    stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
                code=child.wait()
            assert code==0,(name,code)
            trials.append(name);free_lock()
            if name=='accept.py':
                a=json.loads((HERE/'acceptance.json').read_text())
                assert a['status']=='passed_exact_layers_opacity_recomposition_speedup','R22 failed exactness or speed gate'
    except Exception:
        error=traceback.format_exc();print(error,flush=True);save('trial_failure.json',dict(error=error))
    finally:
        if stopped:
            free_lock();sys.path.insert(0,str(ROOT/'dfx/edt_volume'))
            from volume_runtime import VolumeSession
            with VolumeSession(experimental=False) as session:session.return_to_scope()
            verify('ui/active_release.json')
            with (HERE/'restored_UI.log').open('xb') as log:
                child=subprocess.Popen(['bash','ui/run.sh'],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,
                    stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            time.sleep(8);assert child.poll() is None
            assert Path(f'/proc/{child.pid}/cmdline').read_bytes()==expected
            assert sha(Path(f'/proc/{child.pid}/exe'))==state['UI_binary_sha256'];free_lock()
            save('state_after_trial.json',dict(status='formal_R14_UI_restored_after_R22',PID=child.pid,boot_id=boot,
                UI_binary_sha256=state['UI_binary_sha256'],PL_lock_free=True,full_static_echo_and_C6_restore_passed=True,
                static_shell_reloaded=False,driver_unloaded=False,auto_start_added=False))
    save('trial_completed.json',dict(exit_code=0 if error is None else 1,trials=trials,original_UI_restored=stopped))
    return 0 if error is None else 1
if __name__=='__main__':sys.exit(main())
