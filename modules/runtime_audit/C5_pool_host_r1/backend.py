"""Typed candidate graph backend; require physical qualification before ct_open."""
from pathlib import Path
import ctypes as C,hashlib,json,os
import numpy as np
from ct_pl.runtime import XRTInteger,pack_input,pack_weights
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def require_trial_admission(path,library):
    """No flag can enable a7bit old writer or an unqualified partial."""
    p=Path(path).resolve();library=Path(library).resolve()
    if not p.is_file():raise RuntimeError('Qualified C5 pool trial admission is required before opening hardware')
    if not p.is_relative_to(ROOT) or not library.is_relative_to(ROOT):raise ValueError('Candidate admission and library must be inside this integration project')
    record=json.loads(p.read_text());protected=json.loads((ROOT/'results/storage_cleanup_20261015/current_dependencies.json').read_text())
    def retained(file):
        file=file.resolve()
        if not file.is_relative_to(ROOT) or not file.is_file():raise RuntimeError('Missing qualified dependency')
        actual=sha(file)
        if protected.get('kv260_system/'+file.relative_to(ROOT).as_posix())!=actual:raise RuntimeError('Unsealed or changed qualification dependency')
        return actual
    retained(p)
    if record.get('schema')!='kv260.ct_pool.unique_log_hardware_trial.v1':raise RuntimeError('Unsupported logged pool trial admission')
    from modules.runtime_audit.C5_pool_host_r1.qualification import verify_log_host
    verify_log_host(record,retained)
    if record.get('library_SHA256')!=retained(library):raise RuntimeError('Candidate host library mismatch')
    if record.get('writer_control_address_bits')!=8 or record.get('pool_shape_offset')!=128:raise RuntimeError('Old C5 control ABI cannot run pool mode')
    required={
        'RTL':('all398_full_outputs_padding_status_and_next_marker_independently_exact',
            'real4_global_resets_each_mode_not_live_DFX_abort_qualification',
            'actual_321bit_AXIS_and_all_AXI_channels_random_backpressure_ID_bounds_guards_checked'),
        'SYN':('actual_whole_C5_synthesis_qualified',),
        'ARM_host':('all_owned_ARM_model_files_collected_and_SHA_verified_then_exact_task_root_removed',),
        'physical':('same_frozen_RP','routed_100MHz','all5_original_static_pr_verify_passed')}
    if set(record.get('evidence',{}))!=set(required):raise RuntimeError('All four hardware trial qualification proofs are required')
    proofs={}
    for role,fields in required.items():
        item=record['evidence'][role];file=(ROOT/item['path']).resolve()
        if retained(file)!=item['SHA256']:raise RuntimeError('Qualification proof hash mismatch: '+role)
        evidence=json.loads(file.read_text())
        if not all(evidence.get(k) is True for k in fields):raise RuntimeError('Incomplete qualification: '+role)
        proofs[role]=evidence
    if proofs['ARM_host'].get('result',{}).get('numeric_and_lifecycle_checks')!=311:raise RuntimeError('ARM host scope mismatch')
    physical=proofs['physical']
    if physical.get('schema')!='kv260.ct_pool.C5.physical.v1':raise RuntimeError('Pool-specific physical proof required')
    digest=record.get('partial_SHA256')
    if not isinstance(digest,str) or len(digest)!=64 or physical.get('partial_SHA256')!=digest:raise RuntimeError('Physical partial binding mismatch')
    release=ROOT/'dfx/medical/release'
    if sha(release/'medical_ct_partial.bin')!=digest or sha('/lib/firmware/medical_ct_partial.bin')!=digest:
        raise RuntimeError('Qualified pool partial is not installed')
    if Path('/run/kv260-dfx-medical-loaded.sha256').read_text().strip()!=record.get('static_SHA256'):
        raise RuntimeError('Wrong loaded static shell')
    if Path.cwd().resolve()!=ROOT/'dfx/medical':raise RuntimeError('Open the DFX session from its declared project directory')
    return record

class PoolXRT(XRTInteger):
    """Fullskip and pooled data retain separate native leases through NumPy views."""
    def __init__(self,library,admission):
        self.admission=require_trial_admission(admission,library)
        super().__init__(library,ROOT/'dfx/medical/release/dfx_medical.xclbin',pl_quantization=True,output_pool=True)
        self._bind_pool_api()

    def _bind_pool_api(self):
        L=self.lib;L.ct_pool_abi.argtypes=[];L.ct_pool_abi.restype=C.c_uint
        if L.ct_pool_abi()!=0xc5000001:raise RuntimeError('Wrong dual-output host ABI')
        L.ct_set_pool_lut.argtypes=[C.c_void_p,C.c_int,C.c_void_p];L.ct_set_pool_lut.restype=C.c_int
        L.ct_execute_pool_mapped.argtypes=[C.c_void_p,C.c_int,C.c_void_p,C.c_void_p,C.c_void_p,
            *([C.c_uint]*5),C.c_void_p,C.c_void_p,C.c_float,C.c_int]
        L.ct_execute_pool_mapped.restype=C.c_int
        self.pool_tables={};self.pool_uploaded=set();self.pool_calls=0
        self.pl_pool_fusion=self.pointwise_streaming=self.spatial_streaming=self.pl_activation_lut=True

    def configure_pool(self,index,table):
        if index in self.activation_tables:raise ValueError('Pool must precede activation LUT')
        value=np.asarray(table)
        if value.dtype!=np.int8 or value.shape!=(256,):raise ValueError('Expected256-entry INT8 pool LUT')
        value=np.ascontiguousarray(value).copy()
        if index in self.pool_tables and not np.array_equal(value,self.pool_tables[index]):raise ValueError('Cannot change configured pool LUT')
        self.pool_tables[index]=value

    def conv_quantized_pool(self,index,x,w,bias,scale,qscale,zero):
        with self.execution_lock:
            if not self.handle:raise RuntimeError('Pool backend is closed')
            if index not in self.pool_tables or index in self.activation_tables:raise RuntimeError('Pool LUT missing or activation order invalid')
            if x.dtype!=np.int8 or w.dtype!=np.int8 or x.ndim!=4 or x.shape[0]!=1 or w.ndim!=4:
                raise ValueError('Pool convolution requires NCHW INT8 tensors')
            ci,h,width=x.shape[1:];co,wi,k,kw=w.shape
            if not (2<=h<=512 and 2<=width<=512 and h%2==width%2==0 and 1<=ci<=64 and wi==ci and
                co in (8,16,24,32,40,48,56,64) and k==kw and k in (1,3)):
                raise ValueError('Unsupported pool convolution geometry')
            bias,scale,qscale,zero=map(np.asarray,(bias,scale,qscale,zero))
            if bias.dtype!=np.int32 or bias.shape!=(co,) or scale.dtype!=np.float32 or scale.shape!=(co,):raise ValueError('Pool bias/scale shape or precision mismatch')
            if qscale.dtype!=np.float32 or qscale.size!=1 or not np.isfinite(qscale.item()) or qscale.item()<=0 or zero.dtype!=np.int8 or zero.size!=1:
                raise ValueError('Invalid pool output quantization')
            if index not in self.ids:
                packed=pack_weights(w);idx=self.lib.ct_add_weights(self.handle,packed.ctypes.data,packed.nbytes)
                if idx<0:raise RuntimeError(self.lib.ct_error().decode())
                self.ids[index]=idx
            if index not in self.pool_uploaded:
                if self.lib.ct_set_pool_lut(self.handle,self.ids[index],self.pool_tables[index].ctypes.data):raise RuntimeError(self.lib.ct_error().decode())
                self.pool_uploaded.add(index)
            if index not in self.quant_params:self.quant_params[index]=(np.ascontiguousarray(bias),np.ascontiguousarray(scale))
            bp,sp=self.quant_params[index];inp=pack_input(x)
            full,full_handle=self._mapped_array((h,width,co));pooled,pool_handle=self._mapped_array((h//2,width//2,co))
            rc=self.lib.ct_execute_pool_mapped(self.handle,self.ids[index],inp.ctypes.data,full_handle,pool_handle,
                h,width,ci,co,k,bp.ctypes.data,sp.ctypes.data,float(qscale.item()),int(zero.item()))
            if rc:raise RuntimeError(self.lib.ct_error().decode())
            self.calls+=1;self.pool_calls+=1;self.hardware_seconds+=self.lib.ct_last_seconds(self.handle)
            full.flags.writeable=False;pooled.flags.writeable=False
            return full.transpose(2,0,1)[None],pooled.transpose(2,0,1)[None]
