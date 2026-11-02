"""Explicit manual HDMI review of R14c; never changes the default launcher."""
from pathlib import Path
import fcntl,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json
from modules.surface_route.active_actions_r14 import verify_active_scene


def main():
    checkpoint=json.loads((ROOT/'modules/surface_route/work_checkpoint_r14c.json').read_text())
    assert not checkpoint['production_promoted']
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert boot==checkpoint['current_board_state']['boot_id']
    for n,h in checkpoint['current_board_state']['preserved_defaults_sha256'].items():assert sha(ROOT/n)==h,n
    for p in Path('/proc').iterdir():
        try:
            if p.name.isdigit() and (p/'comm').read_text().strip()=='medical_ui':raise RuntimeError('Another UI is active')
        except FileNotFoundError:pass
    with Path('/tmp/kv260-ct-pl.lock').open('rb') as lock:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    binary=ROOT/'ui/releases/feature_completion_r6/build_complete_scene_r14b/medical_ui'
    build=json.loads((binary.parent/'build.json').read_text())
    assert sha(binary)==build['binary_sha256']
    for n,h in build['source_sha256'].items():assert sha(ROOT/n)==h,n
    actual=json.loads((ROOT/'modules/surface_route/results/native_active_surface_GUI_ARM_r14c/acceptance.json').read_text())
    scene=Path(actual['actual_UI']['scene']);verify_active_scene(scene)
    out=ROOT/'modules/surface_route/results/native_active_surface_review_ARM_r14c';out.mkdir(exist_ok=False)
    runtime=Path('/run/kv260-ui-runtime');runtime.mkdir(mode=0o700,exist_ok=True);runtime.chmod(0o700)
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),LD_PRELOAD='/usr/lib/aarch64-linux-gnu/mali/wayland/libMali.so.9.0',
        QT_QPA_PLATFORM='eglfs',QT_QPA_EGLFS_INTEGRATION='eglfs_kms',QT_QPA_EGLFS_KMS_CONFIG=str(ROOT/'ui/kms.json'),
        QT_QPA_EGLFS_KMS_ATOMIC='0',QT_QPA_EGLFS_FORCE888='1',KV260_SCOPE_MODULE='surface',
        KV260_COMPLETE_SCENE=str(scene),OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8')
    for n in list(env):
        if n.startswith('KV260_') and (n.endswith('_TEST') or n.endswith('_UI_TEST')):env.pop(n)
    argv=[str(binary),'--root',str(ROOT),'--input',str(ROOT/'fixtures/own_ct/CT-chest.nrrd'),'--evidence',str(out)]
    with (out/'UI.log').open('xb') as log:
        p=subprocess.Popen(argv,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    write_json(out/'started.json',dict(PID=p.pid,argv=argv,boot_id=boot,scene=str(scene),binary_sha256=sha(binary),
        launcher_sha256=sha(Path(__file__)),production_promoted=False,autostart_created=False))
    print(json.dumps(dict(PID=p.pid,scene=str(scene),manual_review=True)),flush=True)


if __name__=='__main__':main()
