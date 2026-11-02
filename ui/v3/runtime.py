"""V3 launcher (same checks as the V2 launcher; V2 stays intact as rollback). Backend admissions and firmware remain independent."""
from pathlib import Path
import argparse,hashlib,json,os,signal,subprocess,time

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
ENTRY=b'#!/usr/bin/env bash\nset -euo pipefail\nROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"\nexec "$ROOT/.venv/bin/python" -B "$ROOT/ui/v3/runtime.py" "$@"\n'

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def atomic(p,raw):
    p.parent.mkdir(parents=True,exist_ok=True);pending=p.with_name(p.name+'.v3_pending')
    with pending.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    pending.chmod(0o644);os.replace(pending,p)

def save(p,data):atomic(p,(json.dumps(data,indent=2,ensure_ascii=False)+'\n').encode())

def verify(installed=False):
    d=json.loads((HERE/'manifest.json').read_bytes())
    assert d['schema']=='kv260.native_UI_V3.v1' and d['auto_start'] is False
    assert d['silent_PS_fallback'] is False and d['new_bitstream'] is False
    for name,h in {**d['files_sha256'],**d['backend_files_sha256'],d['binary']:d['binary_sha256']}.items():
        p=(ROOT/name).resolve(strict=True);assert p.is_relative_to(ROOT) and sha(p)==h,name
    if installed:
        for name,h in d.get('installed_backend_files_sha256',{}).items():assert sha(ROOT/name)==h,name
        assert Path('/run/kv260-dfx-medical-loaded.sha256').read_text().strip()==d['static_sha256'],'Load the accepted medical static shell first'
        for name,h in d['installed_firmware_sha256'].items():assert sha(Path('/lib/firmware')/name)==h,name
    return d

def proc(pid):
    p=Path('/proc')/str(pid);v=(p/'stat').read_text().rsplit(')',1)[1].split()
    return dict(PID=pid,ticks=int(v[19]),state=v[0])

def running():
    rows=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            exe=(p/'exe').resolve(strict=True)
            if exe.name.startswith('medical_ui') and exe.is_relative_to(ROOT):
                v=proc(int(p.name))
                if v['state']!='Z':rows.append(dict(v,exe=str(exe),SHA256=sha(exe)))
        except (FileNotFoundError,ProcessLookupError):pass
    return rows

def environment():
    runtime=Path('/run/kv260-ui-runtime');runtime.mkdir(mode=0o700,exist_ok=True);runtime.chmod(0o700)
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),LD_PRELOAD='/usr/lib/aarch64-linux-gnu/mali/wayland/libMali.so.9.0',
             QT_QPA_PLATFORM='eglfs',QT_QPA_EGLFS_INTEGRATION='eglfs_kms',QT_QPA_EGLFS_KMS_CONFIG=str(ROOT/'ui/kms.json'),
             QT_QPA_EGLFS_KMS_ATOMIC='0',QT_QPA_EGLFS_FORCE888='1',KV260_SCOPE_MODULE='surface',
             OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
    for key in list(env):
        if key.startswith('KV260_') and key!='KV260_SCOPE_MODULE':env.pop(key)
    return env

def launch(args):
    assert os.geteuid()==0 and os.uname().machine=='aarch64'
    d=verify(installed=True);old=running();assert len(old)<=1
    selected=args.result;ct=args.input or str(ROOT/'fixtures/own_ct/CT-chest.nrrd')
    if old:
        assert args.replace_running,'Project UI already running; use the current window'
        row=old[0];p=Path('/proc')/str(row['PID'])
        assert row['SHA256'] in {d['binary_sha256'],*d['superseded_ui_sha256']},'Unknown running UI; leave it untouched'
        argv=[os.fsdecode(v) for v in (p/'cmdline').read_bytes().rstrip(b'\0').split(b'\0')]
        # Preserve the currently displayed case, not just the original start arguments.
        scenes=[]
        for fd in (p/'fd').iterdir():
            try:
                f=fd.resolve(strict=True)
                if f.name=='ct.f32' and (f.parent/'scene.json').is_file():scenes.append(f.parent/'scene.json')
            except FileNotFoundError:pass
        scenes=list(set(scenes))
        if len(scenes)==1:
            scene=json.loads(scenes[0].read_bytes())
            selected=selected or scene.get('result')
            current_input=scene.get('input') or scene.get('input_path')
            if args.input is None and isinstance(current_input,str) and Path(current_input).is_file():ct=current_input
        if args.input is None and len(scenes)!=1 and '--input' in argv:ct=argv[argv.index('--input')+1]
        if selected is None and '--result' in argv:selected=argv[argv.index('--result')+1]
    cp=Path(ct).resolve(strict=True);assert cp.is_relative_to(ROOT)
    if selected:
        sp=Path(selected).resolve(strict=True);assert sp.is_relative_to(ROOT) and (sp/'pipeline.json').is_file();selected=str(sp)
    for lock in [ROOT/'ui/runs/.runner.lock']:
        import fcntl
        with lock.open('rb') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    evidence=HERE/'session';evidence.mkdir(exist_ok=True)
    if old:
        assert proc(row['PID'])['ticks']==row['ticks'] and sha(p/'exe')==row['SHA256']
        os.kill(row['PID'],signal.SIGTERM)
        start=time.monotonic()
        while p.exists():
            assert time.monotonic()-start<60,'Current UI is busy; it was not forcibly killed'
            time.sleep(.1)
    argv=[str(ROOT/d['binary']),'--root',str(ROOT),'--input',str(cp),'--evidence',str(evidence)]
    if selected:argv+=['--result',selected]
    logpath=evidence/'UI.log'
    if logpath.exists():os.replace(logpath,evidence/'previous_UI.log')
    with logpath.open('xb') as log:
        child=subprocess.Popen(argv,cwd=ROOT,env=environment(),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    identity=proc(child.pid);start=time.monotonic()
    save(evidence/'starting.json',dict(identity,argv=argv,binary_SHA256=d['binary_sha256']))
    while True:
        assert child.poll() is None,'V3 exited; keep UI.log and do not delete the previous release'
        assert proc(child.pid)['ticks']==identity['ticks'] and sha(Path('/proc')/str(child.pid)/'exe')==d['binary_sha256']
        text=logpath.read_text(errors='replace')
        if 'R2277 prepare finished 0 failed false' in text:break
        assert time.monotonic()-start<240,'V3 preparation still pending; keep the live process and evidence'
        time.sleep(.3)
    if args.activate:
        atomic(ROOT/'ui/run.sh',ENTRY);(ROOT/'ui/run.sh').chmod(0o755)
        save(ROOT/'ui/active_release.json',d)
    state_path=ROOT/'tools/storage_runtime_identity.json'
    if state_path.is_file():
        state=json.loads(state_path.read_bytes());state.update(UI_PID=identity['PID'],UI_start_ticks=identity['ticks'],
            argv=argv,binary_sha256=d['binary_sha256'],current_release=d['name'],actual_selected_result=selected)
        state['files_sha256']={n:sha(ROOT/n) for n in ['ui/run.sh','ui/active_release.json',d['binary'],'ui/v3/runtime.py','ui/v3/manifest.json']}
        save(state_path,state)
    result=dict(passed=True,owner=identity,argv=argv,binary_SHA256=d['binary_sha256'],
                accepted_ELF_unchanged=True,activated=args.activate,prior_UI=old,prepare_seconds=time.monotonic()-start,
                new_FPGA_build=False,automatic_startup_added=False)
    save(evidence/'started.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--verify-only',action='store_true');p.add_argument('--installed',action='store_true')
    p.add_argument('--input');p.add_argument('--result');p.add_argument('--replace-running',action='store_true');p.add_argument('--activate',action='store_true')
    a=p.parse_args()
    if a.verify_only:verify(a.installed);print('V3 manifest verified; no PL/UI started')
    else:launch(a)
