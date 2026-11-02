"""Deferred reader requests use owned source BOs directly; no PS tensor fallback."""
from pathlib import Path
import ctypes as C,hashlib,json
import numpy as np
from ct_pl.runtime import XRTInteger,pack_weights
from modules.segmentation.ct_pool_fusion_r1.R7_board_r1.backend import PoolXRT
from modules.segmentation.axis_tensor_reader_r3.graph_r1.reader_graph import ReaderInput
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

# Exact new physical and host proofs are required; the older R7 bit cannot
# satisfy this gate even though it implements the retained convolution API.
EVIDENCE={
 'reader_RTL':('results/tensor_reader_R3_RTL_20261022_r1/axis_rtl/verified_PC.json',
     ('actual_generated40RTL_full159_original_domains_both_schedules_passed','all330_full_frames_and8_actual_global_resets_verified')),
 'reader_IP':('results/tensor_reader_R3_IP_R2_20261022_r1/axis_hls/verified_PC.json',
     ('actual_Vivado_IPX_checksum_refresh_and_integrity_passed','all40_exported_RTL_exact_full330_frame8reset_qualified_R3')),
 'writer_RTL':('results/CT_pool_full493_RTL_20261021_r7/axis_rtl/verified_Windows.json',
     ('all986_full_transactions_1865450_words_exact','all8_actual_global_resets_and_recoveries')),
 'SYN':('results/tensor_reader_R3_C5_SYN_20261022_r1/axis_hls/verified_Windows.json',('actual_whole_C5_synthesis_qualified',)),
 'physical':('results/tensor_reader_R3_C5_ROUTE_20261022_r1/axis_route/verified_Windows.json',
     ('same_frozen_RP','routed_100MHz','all5_original_static_pr_verify_passed')),
 'ARM_host':('modules/segmentation/axis_tensor_reader_r3/host_r1/ARM_r1/paired_verified.json',
     ('all_owned_ARM_files_collected_and_SHA_verified_then_exact_root_removed',))}

def require_reader_admission(path,library):
    path=Path(path).resolve();library=Path(library).resolve()
    if path!=HERE/'admission.json' or library!=HERE/'ARM_r1/collected/output/libct_tensor_reader.so':
        raise RuntimeError('Use the exact R3 reader admission and compiled ARM library')
    if not path.is_file():raise RuntimeError('R3 full physical/ARM qualification is pending; refuse before XRT/CDLL')
    protected=json.loads((ROOT/'results/storage_cleanup_20261015/current_dependencies.json').read_text())
    def retained(p):
        p=Path(p).resolve()
        if not p.is_relative_to(ROOT) or not p.is_file() or p.is_symlink():raise RuntimeError('Missing R3 qualification dependency')
        digest=sha(p)
        if protected.get('kv260_system/'+p.relative_to(ROOT).as_posix())!=digest:raise RuntimeError('Unsealed or changed R3 qualification dependency')
        return digest
    retained(path);record=json.loads(path.read_text())
    if record.get('schema')!='kv260.ct_tensor_reader.R3.hardware_trial.v1' or record.get('reader_ABI')!=0xc5030001:
        raise RuntimeError('Wrong R3 hardware admission schema/ABI')
    if record.get('reader_control_address_bits')!=8 or record.get('writer_control_address_bits')!=8:
        raise RuntimeError('Full R3 control addresses required')
    if set(record.get('evidence',{}))!=set(EVIDENCE):raise RuntimeError('All exact R3 qualifications are required')
    values={}
    for role,(n,fields) in EVIDENCE.items():
        binding=record['evidence'][role]
        if binding!={'path':n,'SHA256':retained(ROOT/n)}:raise RuntimeError('Wrong qualification binding: '+role)
        v=json.loads((ROOT/n).read_text())
        if not all(v.get(k) is True for k in fields):raise RuntimeError('Incomplete R3 qualification: '+role)
        for dep,h in v.get('source_and_evidence_SHA256',{}).items():
            if retained(ROOT/dep)!=h:raise RuntimeError('Changed R3 qualification input: '+dep)
        values[role]=v
    arm=values['ARM_host']['verified'];physical=values['physical'];syn=values['SYN']
    for k in ('all128_reader_cases31_refusals_and_original311_checks_preserved','all726_actual_HLS_C_pipeline_calls_on_ARM',
              'actual_real_ARM_XRT_compile_link_and23_exports_verified','actual_unique_session_log_runtime_and_production_XRT_headers_verified',
              'no_mock_header_in_real_XRT_compile'):
        if arm.get(k) is not True:raise RuntimeError('Incomplete actual ARM reader host: '+k)
    if retained(library)!=record.get('library_SHA256') or sha(library)!=arm['library_SHA256']:
        raise RuntimeError('Actual R3 ARM host library mismatch')
    if syn['physical_RP_bits']!=1830 or physical['candidate_DCP_SHA256']!=record.get('candidate_DCP_SHA256'):
        raise RuntimeError('R3 physical interface/candidate mismatch')
    if physical['clock_MHz']!=100 or physical['WNS_ns']<0 or physical['WHS_ns']<0:
        raise RuntimeError('R3 original100MHz timing qualification required')
    digest=record.get('partial_SHA256')
    if physical.get('partial_SHA256')!=digest or physical['artifact_SHA256'].get('config_ct_tensor_r3_pblock_rp_partial.bin')!=digest:
        raise RuntimeError('R3 partial is not bound to physical proof')
    syn_archive=ROOT/'results/tensor_reader_R3_C5_SYN_20261022_r1/axis_hls/current_candidate.zip'
    physical_archive=ROOT/'results/tensor_reader_R3_C5_ROUTE_20261022_r1/axis_route/current_candidate.zip'
    if retained(syn_archive)!=syn['archive_SHA256'] or retained(physical_archive)!=physical['archive_SHA256']:
        raise RuntimeError('Changed exact R3 compiler output')
    for p in (ROOT/'dfx/medical/release/medical_ct_partial.bin',Path('/lib/firmware/medical_ct_partial.bin')):
        if sha(p)!=digest:raise RuntimeError('Qualified R3 partial is not installed')
    if Path('/run/kv260-dfx-medical-loaded.sha256').read_text().strip()!=record.get('static_SHA256'):
        raise RuntimeError('Wrong loaded static shell')
    if Path.cwd().resolve()!=ROOT/'dfx/medical':raise RuntimeError('Open R3 from its declared DFX project directory')
    return record

class ReaderXRT(PoolXRT):
    def __init__(self,library,admission):
        self.admission=require_reader_admission(admission,library)
        XRTInteger.__init__(self,library,ROOT/'dfx/medical/release/dfx_medical.xclbin',pl_quantization=True,output_pool=True)
        self._bind_pool_api();self._bind_reader_api()

    def _bind_reader_api(self):
        L=self.lib;L.ct_reader_abi.argtypes=[];L.ct_reader_abi.restype=C.c_uint
        if L.ct_reader_abi()!=0xc5030001:raise RuntimeError('Wrong native tensor reader ABI')
        L.ct_set_reader_lut.argtypes=[C.c_void_p,C.c_int,C.c_void_p,C.c_uint];L.ct_set_reader_lut.restype=C.c_int
        L.ct_execute_reader_mapped.argtypes=[C.c_void_p,C.c_int,*([C.c_void_p]*4),*([C.c_uint]*9),
            C.c_void_p,C.c_void_p,C.c_float,C.c_int]
        L.ct_execute_reader_mapped.restype=C.c_int
        self.reader_tables={};self.reader_calls=0;self.pl_tensor_reader=True

    def conv_quantized_reader(self,index,x,w,bias,scale,qscale,zero):
        return self._reader_conv(index,x,w,bias,scale,qscale,zero,False)

    def conv_quantized_pool_reader(self,index,x,w,bias,scale,qscale,zero):
        return self._reader_conv(index,x,w,bias,scale,qscale,zero,True)

    def _reader_conv(self,index,x,w,bias,scale,qscale,zero,pooling):
        with self.execution_lock:
            if not self.handle:raise RuntimeError('Reader backend is closed')
            if not isinstance(x,ReaderInput) or not isinstance(w,np.ndarray) or w.dtype!=np.int8 or w.ndim!=4:
                raise ValueError('Typed deferred reader and INT8 convolution weights required')
            _,ci,h,width=x.shape;co,wi,k,kw=map(int,w.shape);padded=(co+7)//8*8
            if not (1<=co<=64 and wi==ci and k==kw and k in (1,3)):raise ValueError('Unsupported reader convolution shape')
            if pooling and (h<2 or width<2 or h%2 or width%2 or co%8 or index not in self.pool_tables or index in self.activation_tables):
                raise ValueError('Unsupported reader dual-output pool configuration')
            bias,scale,qscale,zero=map(np.asarray,(bias,scale,qscale,zero))
            if bias.dtype!=np.int32 or bias.shape!=(co,) or scale.dtype!=np.float32 or scale.shape!=(co,):
                raise ValueError('Reader bias/scale precision or shape mismatch')
            if not np.isfinite(scale).all() or qscale.dtype!=np.float32 or qscale.size!=1 or not np.isfinite(qscale.item()) or qscale.item()<=0 or zero.dtype!=np.int8 or zero.size!=1:
                raise ValueError('Invalid reader output quantization')
            # Weight and <=512-byte LUT uploads happen once per fixed layer.
            # No pack_input, repeat, concatenate or bulk transform is called.
            if index not in self.ids:
                packed=pack_weights(w);idx=self.lib.ct_add_weights(self.handle,packed.ctypes.data,packed.nbytes)
                if idx<0:raise RuntimeError(self.lib.ct_error().decode())
                self.ids[index]=idx
            idx=self.ids[index]
            if index in self.reader_tables:
                if not np.array_equal(x.tables,self.reader_tables[index]):raise ValueError('Cannot change reader LUT/branch count for a fixed layer')
            else:
                if self.lib.ct_set_reader_lut(self.handle,idx,x.tables.ctypes.data,x.mode):raise RuntimeError(self.lib.ct_error().decode())
                self.reader_tables[index]=x.tables
            if pooling and index not in self.pool_uploaded:
                if self.lib.ct_set_pool_lut(self.handle,idx,self.pool_tables[index].ctypes.data):raise RuntimeError(self.lib.ct_error().decode())
                self.pool_uploaded.add(index)
            if index not in self.quant_params:
                if index in self.activation_tables and index not in self.activation_uploaded:
                    fn=self.lib.ct_set_activation_lut;fn.argtypes=[C.c_void_p,C.c_int,C.c_void_p];fn.restype=C.c_int
                    if fn(self.handle,idx,self.activation_tables[index].ctypes.data):raise RuntimeError(self.lib.ct_error().decode())
                    self.activation_uploaded.add(index)
                bp=np.zeros(padded,np.int32);sp=np.zeros(padded,np.float32);bp[:co]=bias;sp[:co]=scale;self.quant_params[index]=(bp,sp)
            bp,sp=self.quant_params[index];a=x.sources[0];b=x.sources[1] if x.mode==2 else None
            full,full_handle=self._mapped_array((h,width,padded))
            pool,pool_handle=self._mapped_array((h//2,width//2,co)) if pooling else (None,None)
            rc=self.lib.ct_execute_reader_mapped(self.handle,idx,a.data.ctypes.data,b.data.ctypes.data if b else None,
                full_handle,pool_handle,h,width,a.channels,b.channels if b else 0,a.factor,b.factor if b else 1,co,k,x.mode,
                bp.ctypes.data,sp.ctypes.data,float(qscale.item()),int(zero.item()))
            if rc:raise RuntimeError(self.lib.ct_error().decode())
            self.calls+=1;self.reader_calls+=1;self.pool_calls+=int(pooling);self.hardware_seconds+=self.lib.ct_last_seconds(self.handle)
            full.flags.writeable=False;out=full[:,:,:co].transpose(2,0,1)[None]
            if pool is None:return out
            pool.flags.writeable=False;return out,pool.transpose(2,0,1)[None]
