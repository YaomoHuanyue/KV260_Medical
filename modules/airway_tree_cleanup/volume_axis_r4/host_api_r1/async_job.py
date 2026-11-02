"""Nonblocking raw-volume PL backend. File I/O/control only; no PS cleanup.

Requires explicit source, CT and geometry identities and a board-qualified B7
binding. No module import launches a process, connects to hardware or loads a bit.
The native worker owns the PL lock, physical buffers and DFX safety fences.
"""
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,os,re,subprocess,time,uuid

class PLBackendError(RuntimeError):pass
def require(ok,message):
    if not ok:raise PLBackendError(message)
def sha(path):
    with path.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def digest(value):return type(value)is str and re.fullmatch('[0-9a-f]{64}',value)is not None
def read(path):
    require(path.stat().st_size<=2000000,'Oversized runtime metadata')
    return json.loads(path.read_text(encoding='utf8'))
def save(path,value):
    with path.open('x',encoding='utf8')as f:json.dump(value,f,indent=2);f.write('\n')
def tail(path):
    with path.open('rb')as f:f.seek(max(0,path.stat().st_size-4096));return f.read().decode(errors='replace')

@dataclass(frozen=True)
class RawVolume:
    path:Path
    shape_zyx:tuple
    SHA256:str
    CT_SHA256:str
    geometry_SHA256:str
    closing:int=1
    def validate(self):
        require(type(self.path)is type(Path())and self.path.is_absolute()and self.path.resolve(strict=True)==self.path,'Canonical absolute U8 source required')
        require(type(self.shape_zyx)is tuple and len(self.shape_zyx)==3 and all(type(v)is int and 1<=v<=512 for v in self.shape_zyx),'Bounded original ZYX shape required')
        require(all(digest(v)for v in [self.SHA256,self.CT_SHA256,self.geometry_SHA256]),'Explicit source/CT/geometry SHA identities required')
        require(type(self.closing)is int and -2147483648<=self.closing<=2147483647,'Closing count must fit hardware signed32; no clamp')
        require(self.path.stat().st_size==self.voxels,'U8 file size differs')
        # Native worker verifies the complete SHA before opening PL. Keep this
        # caller-side admission to metadata; no volume traversal on a UI thread.
    @property
    def voxels(self):
        result=1
        for n in self.shape_zyx:result*=n
        return result

class QualifiedBackend:
    def __init__(self,system_root,binding_path,binding_SHA256):
        self.root=Path(system_root);require(self.root.is_absolute()and self.root.resolve(strict=True)==self.root,'Canonical system root required')
        self.binding_path=Path(binding_path);require(digest(binding_SHA256)and sha(self.binding_path)==binding_SHA256,'Explicit B7 binding SHA mismatch')
        self.binding=read(self.binding_path);b=self.binding
        require(b.get('schema')=='kv260.B7.AXIS.board_runtime_binding.r1'and b.get('board_verified')is True and b.get('identity')==183 and b.get('ABI')==2,'B7 whole-volume board qualification missing')
        require(b.get('own139_voxel_exact')is True and b.get('C6_return_verified')is True,'Whole139/C6 qualification missing')
        self.worker=Path(b['worker']);self.enrollment=Path(b['enrollment'])
        for path,key in [(self.worker,'worker_SHA256'),(self.enrollment,'enrollment_SHA256')]:
            require(path.resolve(strict=True)==path and path.is_relative_to(self.root)and sha(path)==b[key],'Qualified executable/enrollment differs')
        require(self.worker.is_file()and os.access(self.worker,os.X_OK),'Executable unavailable')
        require(read(self.enrollment).get('firmware')=='medical_airway_U8_AXIS_B7_r1_partial.bin','Wrong B7 firmware enrollment')
    def submit(self,source):
        require(type(source)is RawVolume,'Explicit RawVolume descriptor required');source.validate()
        # Re-admit files before each submission; never keep a stale mutable alias.
        require(sha(self.worker)==self.binding['worker_SHA256']and sha(self.enrollment)==self.binding['enrollment_SHA256'],'Runtime artifacts changed')
        directory=self.root/'results'/('airway_AXIS_'+uuid.uuid4().hex);require(directory.parent.resolve(strict=True)==directory.parent,'Canonical results parent required');directory.mkdir(mode=0o700)
        return CleanupJob(self,source,directory)

class CleanupJob:
    def __init__(self,backend,source,directory):
        self.backend,self.source,self.directory=backend,source,directory;self.result_value=None;self.started=time.monotonic();self.stop_after_stage=False;self.verifier=None;self.verification=None
        z,y,x=source.shape_zyx;job=dict(nx=x,ny=y,nz=z,closing=source.closing,tag=int(uuid.uuid4().hex[:7],16),input=str(source.path),input_SHA256=source.SHA256,output=str(directory/'mask.u8'),report=str(directory/'PL.json'))
        path=directory/'job.json';save(path,job);self.job=job
        args=[str(backend.worker),str(backend.enrollment),backend.binding['enrollment_SHA256'],str(path),sha(path)]
        with(directory/'stdout.log').open('xb')as out,(directory/'stderr.log').open('xb')as err:
            self.process=subprocess.Popen(args,cwd=backend.root,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
        save(directory/'owner.json',dict(PID=self.process.pid,argv=args,backend='PL_B7_U8_AXIS',source_SHA256=source.SHA256,CT_SHA256=source.CT_SHA256,geometry_SHA256=source.geometry_SHA256,stop_policy='after stage only; no signal/free while active'))
    def request_stop_after_stage(self):
        self.stop_after_stage=True
        marker=self.directory/'stop_after_stage.json'
        if not marker.exists():save(marker,dict(requested=True,active_PL_transaction_cancelled=False))
    def poll(self):
        """Return None while active, otherwise verified output metadata; never wait."""
        if self.result_value is not None:return self.result_value
        code=self.process.poll()
        if code is None:return None
        if code!=0:
            with(self.directory/'stderr.log').open('rb')as f:f.seek(max(0,(self.directory/'stderr.log').stat().st_size-4096));message=f.read().decode(errors='replace')
            raise PLBackendError('PL worker refused/failed; no PS fallback: '+message)
        if self.verification is None:
            self.verifier=ThreadPoolExecutor(max_workers=1,thread_name_prefix='B7-output-verify')
            self.verification=self.verifier.submit(self._verify_output)
            return None
        if not self.verification.done():return None
        try:self.result_value=self.verification.result()
        finally:self.verifier.shutdown(wait=False)
        return self.result_value
    def _verify_output(self):
        report=read(self.directory/'PL.json');mask=self.directory/'mask.u8'
        require(report.get('backend')=='PL_B7_U8_AXIS'and report.get('passed')is True and report.get('C6_restored')is True and report.get('all_three_done_idle')is True and report.get('guard_bytes_verified')is True,'Incomplete actual PL/DFX completion record')
        require(report.get('voxels')==self.source.voxels and mask.stat().st_size==self.source.voxels and sha(mask)==report.get('mask_SHA256'),'PL output extent/hash differs')
        require(sha(self.source.path)==self.source.SHA256,'Source changed during transaction; refuse acceptance')
        require(report.get('status')in [0,5,6],'Unknown PL result status')
        outcome={0:'mask_ready',5:'empty_input',6:'empty_after_closing'}[report['status']]
        value=dict(schema='kv260.B7.AXIS.async_result.r1',backend='PL_B7_U8_AXIS',outcome=outcome,structure_available=report['status']==0,mask=str(mask),shape_zyx=self.source.shape_zyx,source_SHA256=self.source.SHA256,CT_SHA256=self.source.CT_SHA256,geometry_SHA256=self.source.geometry_SHA256,PL=report,elapsed_seconds=time.monotonic()-self.started,stop_after_stage=self.stop_after_stage,accepted_model_or_navigation_modified=False,silent_PS_fallback=False)
        save(self.directory/'verified_result.json',value);return value
    def status(self):
        result=self.poll()
        if result is not None:return dict(phase='completed',result=result)
        if self.verification is not None:return dict(phase='verifying_output',seconds=time.monotonic()-self.started,stop_after_stage=self.stop_after_stage)
        text=tail(self.directory/'stderr.log');started='B7_RUNNING 'in tail(self.directory/'stdout.log')
        return dict(phase='retained_fault'if 'B7_RETAINED_FAULT'in text else'running_PL'if started else'preparing',seconds=time.monotonic()-self.started,stop_after_stage=self.stop_after_stage,cancellation_policy='wait for current stage, no process signal')
