"""Native UI candidate with qualified PL stages; preserve accepted UI actions."""
from pathlib import Path
import csv,fcntl,hashlib,json,os,re,shutil,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.dont_write_bytecode=True;os.environ['PYTHONDONTWRITEBYTECODE']='1'
sys.path.insert(0,str(ROOT))
PATTERNS=('dfx/*/results/switch*.csv','modules/ct_preprocess/axis_hu_32_r2/host_r1/results/switch*.csv',
    'modules/reconstruction/axis_mc_8_r2/host_pooled_r2/results/switch*.csv',
    'modules/reconstruction/smooth_pipeline_r2/axis_tile1024_r1/host_D9_r1/hardware_r1/results/switch*.csv')


def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def snapshot_logs():return {p.relative_to(ROOT).as_posix():sha(p) for pattern in PATTERNS for p in ROOT.glob(pattern)}


def retain_stage_logs(output,stage,pid,before):
    if any(not (ROOT/n).is_file() or sha(ROOT/n)!=h for n,h in before.items()):
        raise RuntimeError('An existing DFX log changed during the candidate stage')
    directory=Path(output)/'dfx_audit'/stage;directory.mkdir(parents=True)
    owned=[]
    for pattern in PATTERNS:
        for p in ROOT.glob(pattern):
            n=p.relative_to(ROOT).as_posix()
            if n in before or not re.search('_'+str(pid)+r'\.csv$',n):continue
            destination=directory/p.name
            with p.open('rb') as src,destination.open('xb') as dst:
                shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
            digest=sha(p)
            if sha(destination)!=digest:raise RuntimeError('DFX log retention failed')
            owned.append(dict(source=n,file=destination.name,SHA256=digest,records=list(csv.DictReader(destination.open()))))
    # Segmentation already retains its D6/C5 logs inside its own result.
    with (directory/'switches.json').open('x',encoding='utf-8') as f:
        json.dump(dict(stage=stage,child_PID=pid,actual_logs=owned),f,indent=2);f.flush();os.fsync(f.fileno())
    for row in owned:
        p=ROOT/row['source']
        if sha(p)!=row['SHA256']:raise RuntimeError('Closed owned log changed')
        p.unlink()


def install():
    from modules.segmentation.streaming_stage_r1.entry import recover_pending
    recover_pending()  # Only abandoned, exact file transactions; never a live owner.
    from ui.releases.ct_bounded_outputs_r1.backend import install as parent_install
    backend=parent_install()
    inputs=json.loads((HERE/'derivation.json').read_text())
    for name in ('dispatcher','catalogue'):
        d=inputs[name];parent=ROOT/d['parent']
        if sha(parent)!=d['parent_SHA256']:raise RuntimeError('Accepted backend changed')
        original=parent.read_text()
        if name=='catalogue':
            import ast
            node=next(n for n in ast.parse(original).body if isinstance(n,ast.FunctionDef) and n.name=='catalogue')
            original=ast.get_source_segment(original,node)+'\n'
        for edit in d['literal_edits']:
            if original.count(edit['before'])!=edit['count']:raise RuntimeError('Dispatcher derivation changed')
            original=original.replace(edit['before'],edit['after'])
        target=HERE/('dispatch.py' if name=='dispatcher' else 'catalogue.py')
        if original!=target.read_text() or sha(target)!=d['output_SHA256']:raise RuntimeError('Unqualified candidate dispatcher')
        exec(compile(original,str(target),'exec'),backend.__dict__)
    backend.CANDIDATE_RUNS=HERE/'runs'
    backend._snapshot_candidate_logs=snapshot_logs
    backend._retain_candidate_stage_logs=retain_stage_logs
    def run(input_path,mode,source=None,lesion=0,diameter=1.,margin=.2,stop_file=None,minimum_bend=0.):
        (ROOT/'ui/runs').mkdir(parents=True,exist_ok=True)
        with (ROOT/'ui/runs/.runner.lock').open('a') as job:
            fcntl.flock(job,fcntl.LOCK_EX|fcntl.LOCK_NB)
            backend._candidate_job_fd=job.fileno()
            try:return backend._run_locked(input_path,mode,source,lesion,diameter,margin,stop_file,minimum_bend)
            finally:del backend._candidate_job_fd
    backend.run=run
    return backend


def main():
    install()
    import backend_selected_r1 as accepted
    return accepted.main()


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps(dict(event='error',text=str(error)),ensure_ascii=False),flush=True);sys.exit(1)
