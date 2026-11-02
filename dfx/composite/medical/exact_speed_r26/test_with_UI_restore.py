"""Exact-color trial; cooperate with the known UI and restore it on every exit."""
from pathlib import Path
import fcntl,hashlib,json,os,signal,subprocess,sys,time,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,r):
 p=HERE/n;assert not p.exists();p.write_text(json.dumps(r,indent=2)+'\n')
def free_lock():
 with open('/tmp/kv260-ct-pl.lock','rb') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
def main():
 assert os.geteuid()==0
 sys.path.insert(0,str(ROOT/'ui/production_r1'))
 from verify_release_r6 import verify
 release=verify('ui/active_release.json');descriptor_sha=sha(ROOT/'ui/active_release.json')
 boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
 expected=release['binary'].encode()+b'\0--root\0'+str(ROOT).encode()+b'\0'
 candidates=[]
 for p in Path('/proc').iterdir():
  if p.name.isdigit():
   try:
    if (p/'cmdline').read_bytes()==expected and sha(p/'exe')==release['UI_build']['binary_sha256']:candidates.append(int(p.name))
   except (FileNotFoundError,ProcessLookupError,PermissionError):pass
 assert len(candidates)==1,candidates
 pid=candidates[0];env={k:v for k,v in os.environ.items() if not k.startswith('KV260_')};env['PYTHONIOENCODING']='utf-8'
 save('trial_started.json',dict(UI_PID=pid,boot_id=boot,descriptor_sha256=descriptor_sha,source_sha256=sha(Path(__file__))))
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
    child=subprocess.Popen([str(ROOT/'.venv/bin/python'),str(HERE/name)],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
    code=child.wait()
   assert code==0,(name,code);trials.append(name);free_lock()
   if name=='accept.py':assert json.loads((HERE/'acceptance.json').read_text())['status']=='passed_exact_layers_opacity_recomposition_speedup','No speedup: do not promote'
 except Exception:
  error=traceback.format_exc();print(error,flush=True);save('trial_failure.json',dict(error=error))
 finally:
  if stopped:
   free_lock();sys.path.insert(0,str(ROOT/'dfx/edt_volume'))
   from volume_runtime import VolumeSession
   with VolumeSession(experimental=False) as session:session.return_to_scope()
   assert sha(ROOT/'ui/active_release.json')==descriptor_sha;verify('ui/active_release.json')
   with (HERE/'restored_UI.log').open('xb') as log:
    child=subprocess.Popen(['bash','ui/run.sh'],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   time.sleep(8);assert child.poll() is None
   assert Path(f'/proc/{child.pid}/cmdline').read_bytes()==expected
   assert sha(Path(f'/proc/{child.pid}/exe'))==release['UI_build']['binary_sha256']
   assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
   save('state_after_trial.json',dict(PID=child.pid,boot_id=boot,UI_binary_sha256=release['UI_build']['binary_sha256'],status='verified_formal_UI_restored',full_static_echo_and_C6_restore_passed=True,static_shell_reloaded=False,driver_unloaded=False,auto_start_added=False))
 save('trial_completed.json',dict(exit_code=0 if error is None else 1,trials=trials,original_UI_restored=stopped));return 0 if error is None else 1
if __name__=='__main__':sys.exit(main())
