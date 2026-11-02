"""Isolated accepted-medical runtime; restore exact reviewed binary/scene."""
from pathlib import Path
import fcntl,hashlib,json,os,subprocess,sys,time,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SHA=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def write(p,r):
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(r,f,indent=2);f.write('\n')

def main():
    assert os.geteuid()==0 and sys.platform=='linux'
    binding=json.loads((HERE/'trial_binding_r79d.json').read_text())
    for n,h in binding['source_sha256'].items():assert SHA(ROOT/n)==h,n
    prior_path=ROOT/binding['board_UI_binding'];assert SHA(prior_path)==binding['board_UI_binding_sha256']
    prior=json.loads(prior_path.read_text());state=prior['UI'];scene=Path(state['scene'])
    out=HERE/'board';trial=json.loads((out/'trial_terminal.json').read_text())
    assert not (out/'restored_UI.json').exists()
    def identity():
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==prior['boot_id']
        assert SHA(scene)==binding['scene_sha256']
        assert Path('/run/kv260-dfx-medical-loaded.sha256').read_text().strip()==prior['medical_shell_marker_content']
        for n,h in prior['files_sha256'].items():assert SHA(ROOT/n)==h,n
    identity()
    assert not Path(f"/proc/{state['PID']}/cmdline").exists()
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:cmd=(proc/'cmdline').read_bytes().split(b'\0')
        except (OSError,ProcessLookupError):continue
        assert not cmd or not cmd[0] or Path(os.fsdecode(cmd[0])).name!='medical_ui',proc.name
    with open('/tmp/kv260-ct-pl.lock','rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(lock,fcntl.LOCK_UN)
    sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'dfx/edt_volume'))
    from volume_runtime import VolumeSession
    with VolumeSession(experimental=False) as lifecycle:lifecycle.return_to_scope()
    assert Path(sys.modules['runtime'].__file__).resolve()==ROOT/'dfx/medical/runtime.py'
    from tools.surface_quality_trial_r16 import UI_environment
    from tools.mesh_quality_recover_evidence_r17c import ready
    identity();folder=out/'review';folder.mkdir(exist_ok=False)
    argv=list(state['argv']);argv[argv.index('--evidence')+1]=str(folder)
    with (folder/'UI.log').open('xb') as log:
        ui=subprocess.Popen(argv,cwd=ROOT,env=UI_environment(scene),stdin=subprocess.DEVNULL,
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    restored=dict(state,PID=ui.pid,argv=argv,previous_UI_PID=state['PID'],boot_id=prior['boot_id'],
        status='same_reviewed_UI_restored_after_R7_packed_trial',trial_exit_code=trial['exit_code'],
        static_shell_reloaded=False,ZOCL_unloaded=False,forced_kill_or_reset=False,new_experimental_firmware_loaded=True,
        no_automatic_startup=True,physical_display_review_repeated=False,
        files_sha256=prior['files_sha256'],medical_shell_marker_content=prior['medical_shell_marker_content'],
        source_and_evidence_sha256={p.relative_to(ROOT).as_posix():SHA(p) for p in
            [Path(__file__),HERE/'trial_with_UI_restore_r79d.py',HERE/'trial_binding_r79d.json',prior_path,out/'trial_terminal.json']})
    write(folder/'started.json',restored);time.sleep(3);ready(restored,seconds=60)
    assert ui.poll() is None;identity();assert SHA(Path(f'/proc/{ui.pid}/exe'))==state['binary_sha256']
    write(out/'restored_UI.json',restored);print(restored['status'],ui.pid,flush=True)

if __name__=='__main__':
    try:main()
    except BaseException as error:
        failure=HERE/'board_r71/restore_failure.json'
        if not failure.exists():write(failure,dict(status='restoration_requires_inspection_preserve_processes',error=repr(error),traceback=traceback.format_exc()))
        raise
