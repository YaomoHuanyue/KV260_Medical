"""Bound idle UI drain, complete old-R4 trial, isolated interpreter restoration."""
from pathlib import Path
import argparse,fcntl,hashlib,json,os,signal,subprocess,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SHA=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def write(p,r):
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(r,f,indent=2);f.write('\n')

def main():
    assert sys.platform=='linux' and os.geteuid()==0
    p=argparse.ArgumentParser();p.add_argument('--check-only',action='store_true');args=p.parse_args()
    binding=json.loads((HERE/'trial_binding_r79d.json').read_text())
    for n,h in binding['source_sha256'].items():assert SHA(ROOT/n)==h,n
    prior_path=ROOT/binding['board_UI_binding'];assert SHA(prior_path)==binding['board_UI_binding_sha256']
    prior=json.loads(prior_path.read_text());state=prior['UI'];pid=state['PID'];argv=[s.encode() for s in state['argv']]
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip();assert boot==prior['boot_id']
    marker=Path('/run/kv260-dfx-medical-loaded.sha256')
    def identity():
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
        assert SHA(Path(state['scene']))==binding['scene_sha256']
        for n,h in prior['files_sha256'].items():assert SHA(ROOT/n)==h,n
        assert marker.read_text().strip()==prior['medical_shell_marker_content']
    def idle_UI():
        assert Path(f'/proc/{pid}/cmdline').read_bytes().rstrip(b'\0').split(b'\0')==argv
        assert SHA(Path(f'/proc/{pid}/exe'))==state['binary_sha256']
        assert not Path(f'/proc/{pid}/task/{pid}/children').read_text().strip(),'Active GUI job; no signal or PL access'
    identity();idle_UI()
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8')
    subprocess.run([sys.executable,str(HERE/'benchmark_r79d.py'),'--preflight-only'],cwd=ROOT,env=env,check=True)
    if args.check_only:
        print('Same reviewed idle UI, fully verified R7 firmware, all packed host gates and full PS/CT inputs preflight passed; no signal or PL access',flush=True);return
    out=HERE/'board';out.mkdir(exist_ok=True)
    assert not (out/'started.json').exists() and not (out/'restored_UI.json').exists()
    write(out/'started.json',dict(status='manual_full_R7_packed_trial_starting',PID=os.getpid(),
        previous_UI_PID=pid,original_UI=state,boot_id=boot,binding_sha256=SHA(HERE/'trial_binding_r79d.json'),new_firmware_built=True))
    stopped=False;trial=None
    try:
        identity();idle_UI();os.kill(pid,signal.SIGTERM)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            try:current=Path(f'/proc/{pid}/cmdline').read_bytes().rstrip(b'\0').split(b'\0')
            except (FileNotFoundError,ProcessLookupError):current=[]
            if current!=argv:stopped=True;break
            time.sleep(.1)
        assert stopped,'Idle UI drain not complete; no forced kill or hardware trial'
        with open('/tmp/kv260-ct-pl.lock','rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(lock,fcntl.LOCK_UN)
        print('Idle UI drained; running full R7 packed/PS1/PS4 comparison',flush=True)
        trial=subprocess.run([sys.executable,str(HERE/'benchmark_r79d.py')],cwd=ROOT,env=env).returncode
    finally:
        if stopped:
            result=out/'own_CT_benchmark_r79d.json'
            write(out/'trial_terminal.json',dict(exit_code=trial,trial_result_sha256=SHA(result) if result.exists() else None,
                ordinary_UI_drained=True,forced_kill_or_reset=False,Windows_network_modified=False))
            # Fresh interpreter prevents the profile runtime named "runtime"
            # from shadowing the accepted medical restoration runtime.
            restored=subprocess.run([sys.executable,str(HERE/'restore_UI_r79d.py')],cwd=ROOT,env=env).returncode
            assert restored==0,'Restoration failure preserved; inspect existing processes, no forced recovery'
    assert trial==0,'Trial failed; same reviewed UI restored and failure preserved'

if __name__=='__main__':main()
