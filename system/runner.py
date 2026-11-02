from pathlib import Path
from contextlib import contextmanager
import hashlib,json,os,shutil,subprocess,sys,time,uuid
from .contracts import *

ROOT=Path(__file__).resolve().parents[1]
STAGES=('segmentation','reconstruction','navigation')
FIRMWARE={'segmentation':'ct_segmentation.bit.bin','reconstruction':'kv260_mc_smooth.bit.bin','navigation':'kv260_navigation.bit.bin'}

@contextmanager
def lock_file(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as f:
        if sys.platform=='win32':
            import msvcrt
            if f.tell()==0:f.write(b'0');f.flush()
            f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:
            if sys.platform=='win32':f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f,fcntl.LOCK_UN)

def firmware():
    p=Path('/sys/firmware/devicetree/base/fpga-region/firmware-name')
    return p.read_bytes().rstrip(b'\0').decode() if p.exists() else None

def release_digest():
    manifest=ROOT/'release.json';record=read_json(manifest)
    for rel,h in record['files'].items():
        if sha256(inside(ROOT,rel))!=h:raise ValueError(f'Integrated source/release changed: {rel}; publish a new release manifest')
    return sha256(manifest)

def import_masks(folder,source):
    folder=Path(folder).resolve();source=Path(source).resolve();case=load_case(folder)
    with lock_file(folder/'.lock'):
        dest=folder/'imported_masks'
        if dest.exists():raise FileExistsError('Imported masks already exist; use a new case to change inputs')
        report=read_json(source/'report.json')
        allowed=set(case['source_sha256'].values())|{case['ct']['sha256']}
        if report.get('status')!='completed' or report.get('input_sha256') not in allowed:raise ValueError('Completed mask report must identify this input CT by SHA256')
        masks=validate_masks(source,case['ct']['geometry']);tmp=folder/('.masks-'+uuid.uuid4().hex);tmp.mkdir()
        try:
            for name in CLASSES:shutil.copy2(source/f'{name}_mask.nii.gz',tmp/f'{name}_mask.nii.gz')
            shutil.copy2(source/'report.json',tmp/'source_report.json')
            artifact(tmp,case,'segmentation',{},dict(imported=True),dict(origin=str(source),source_report_sha256=sha256(source/'report.json'),masks=masks,fresh_inference=False))
            tmp.rename(dest)
        except Exception:shutil.rmtree(tmp);raise
    return dest

def run(folder,stages,options,from_masks=False):
    folder=Path(folder).resolve();case=load_case(folder)
    if not stages or any(s not in STAGES for s in stages) or len(set(stages))!=len(stages):raise ValueError('Invalid stage list')
    if stages!=sorted(stages,key=STAGES.index):raise ValueError('Stages must follow segmentation, reconstruction, navigation order')
    if from_masks and 'segmentation' in stages:raise ValueError('--from-masks cannot request segmentation')
    digest=release_digest()
    identity={'release_sha256':digest,'options':options,'from_imported_masks':from_masks}
    run_id=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:20]
    run_dir=folder/'runs'/run_id;run_dir.mkdir(parents=True,exist_ok=True)
    with lock_file(folder/'.lock'),lock_file(ROOT/'cases/.hardware.lock'):
        write_json(run_dir/'request.json',identity)
        status={'schema':'kv260.system.run.v1','case_id':case['case_id'],'run_id':run_id,'status':'running','requested_stages':stages,'completed':[],'firmware_switching':'manual_whole_bitstream_prototype','dfx_implemented':False}
        state_path=run_dir/'state.json'
        try:
            for stage in stages:
                masks=folder/'imported_masks' if from_masks else run_dir/'segmentation'
                dependencies={}
                if stage!='segmentation':
                    validate_artifact(masks,case,'segmentation');validate_masks(masks,case['ct']['geometry'])
                    dependencies['segmentation_artifact_sha256']=sha256(masks/'artifact.json')
                dest=run_dir/stage
                if dest.exists():
                    a=validate_artifact(dest,case,stage)
                    if a['dependencies']!=dependencies or a['parameters']!=options:raise ValueError('Completed stage dependencies/options changed')
                    status['completed'].append(stage);continue
                if firmware()!=FIRMWARE[stage]:
                    status.pop('active_stage',None)
                    status.update(status='needs_firmware',next_stage=stage,required_firmware=FIRMWARE[stage],loaded_firmware=firmware())
                    write_json(state_path,status);return status
                tmp=run_dir/('.'+stage+'-'+uuid.uuid4().hex);tmp.mkdir()
                request=dict(case=case,ct=str(inside(folder,case['ct']['path'])),output=str(tmp),options={**options,'mask_dir':str(masks)})
                req=run_dir/('worker_'+stage+'.json');write_json(req,request)
                status.update(active_stage=stage);write_json(state_path,status);start=time.perf_counter()
                env=os.environ.copy();env['PYTHONPATH']=str(ROOT);env['OPENBLAS_NUM_THREADS']='1';env['OMP_NUM_THREADS']='4'
                env['PYTHONNOUSERSITE']='1'
                with (run_dir/(stage+'.log')).open('w',encoding='utf-8') as log:
                    # Never time out/kill a PL worker while it might own active DMA BOs.
                    completed=subprocess.run([sys.executable,'-m','system.adapters',stage,str(req)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
                if completed.returncode:raise RuntimeError(f'{stage} failed ({completed.returncode}); see {run_dir/(stage+".log")}; partial output preserved at {tmp}')
                artifact(tmp,case,stage,dependencies,options,dict(release_sha256=digest,loaded_firmware=firmware(),wall_seconds=time.perf_counter()-start,fresh_compute=True))
                tmp.rename(dest);status['completed'].append(stage)
                status.pop('active_stage',None)
            status.update(status='completed');status.pop('active_stage',None);write_json(state_path,status);return status
        except Exception as e:
            status.update(status='failed',error=str(e));write_json(state_path,status);raise
