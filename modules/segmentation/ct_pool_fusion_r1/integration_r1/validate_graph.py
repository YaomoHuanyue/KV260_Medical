"""Original graph versus candidate C-HLS writer; never claim native as board PL."""
from pathlib import Path
import argparse,ctypes as C,hashlib,json,os,subprocess,sys,time
import numpy as np
import SimpleITK as sitk
HERE=Path(__file__).resolve().parent;CORE=HERE.parent;ROOT=CORE.parents[2]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'modules/segmentation'),str(HERE)]
import project_storage
from ct_pl.runtime import Graph,pack_input,pack_weights
from ct_pl.stream_graph import ContextPreparer
from airway.ct_geometry import prepare_grid,make_context
from pool_graph import PoolGraph
MODEL=ROOT/'modules/segmentation/outputs/ct_accuracy_v2/pl_model'
COMPILER=Path('F:/AMDDesignTools/2025.2.1/Vitis/tps/mingw/10.0.0/win64.o/nt/bin/g++.exe')
BUILD=HERE/'build_native';LIBRARY=BUILD/'candidate.dll'

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def array_sha(value):return hashlib.sha256(memoryview(np.ascontiguousarray(value)).cast('B')).hexdigest()

def sources():
    return [Path(__file__),HERE/'pool_graph.py',HERE/'pool_graph_head.py',HERE/'executor_derivation.json',
        HERE/'native_pool_bridge.cpp',CORE/'adapter_r6/writer_pool.cpp',CORE/'shared_pipeline_r6.hpp',CORE/'pool_stream.hpp',
        *[ROOT/'modules/segmentation/ct_pl'/n for n in ('conv.cpp','stream_types.hpp','native_bridge.cpp','graph_ops.cpp',
            'postprocess.cpp','postprocess.hpp','runtime.py','quantized_runtime.py','native_graph.py','stream_graph.py','fused_graph.py')],
        ROOT/'modules/segmentation/airway/ct_geometry.py',MODEL/'graph.json',MODEL/'tensors.npz',CORE/'model_tables.json']

def save(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)

def build():
    project_storage.check(150_000_000);assert not BUILD.exists();BUILD.mkdir()
    base=ROOT/'modules/segmentation/ct_pl'
    argv=[str(COMPILER),'-std=c++17','-O3','-shared','-DCT_NATIVE','-ffp-contract=off','-fno-fast-math',
        '-static-libgcc','-static-libstdc++','-Wno-unknown-pragmas',str(CORE/'adapter_r6/writer_pool.cpp'),
        *[str(base/n) for n in ('native_bridge.cpp','graph_ops.cpp','postprocess.cpp')],
        str(HERE/'native_pool_bridge.cpp'),'-o',str(LIBRARY)]
    with (BUILD/'compile.log').open('xb') as f:result=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT)
    assert result.returncode==0,(BUILD/'compile.log').read_text(errors='replace')
    save(BUILD/'compiled.json',dict(library_SHA256=sha(LIBRARY),compiler_argv=argv,
        source_and_evidence_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in sources()},
        native_simulation_not_hardware=True,whole_goal_completed=False))
    print('PASS original convolution and R6 writer C simulation DLL compiled; not XRT or hardware',flush=True)

class NativeBackend:
    pl_activation_lut=True;pl_pool_fusion=True
    backend_kind='native_HLS_C_simulation_not_PL_hardware'
    def __init__(self,library,record=None):
        self.lib=library;self.record=record;self.values={} if record is None else record.values
        self.weights={};self.activation={};self.pool_tables={};self.calls=0;self.pool_calls=0;self.trace=[]
        p=C.c_void_p;u=C.c_uint
        for name,types in (
            ('ct_native',[p,p,p,u,u,u,u,u]),('ct_native_quant',[p,p,p,u,u,u,u]),
            ('ct_native_fused',[p,p,p,u,u,u,u]),('ct_native_pool',[p,p,p,p,p,u,u,u,u,u])):
            function=getattr(library,name);function.argtypes=types;function.restype=C.c_int
    def allocate_activation(self,shape):return np.empty(shape,np.int8)
    def configure_activation(self,index,table):self.activation[index]=np.ascontiguousarray(table,dtype=np.int8)
    def configure_pool(self,index,table):
        if index in self.activation:raise ValueError('Pool must consume unactivated quantized writer output')
        self.pool_tables[index]=np.ascontiguousarray(table,dtype=np.int8)
    def conv(self,index,x,w):
        if self.record is not None:
            expected,acc=self.values[index];np.testing.assert_array_equal(x,expected,err_msg=f'Layer{index} input differs')
            result=acc.copy(order='K')
        else:
            ci,h,width=x.shape[1:];co=w.shape[0];kernel=w.shape[2]
            if index not in self.weights:self.weights[index]=pack_weights(w)
            packed=pack_input(x);out=np.empty((h,width,(co+7)//8*8),np.int32)
            status=self.lib.ct_native(packed.ctypes.data,self.weights[index].ctypes.data,out.ctypes.data,h,width,ci,co,kernel)
            if status:raise RuntimeError('Original native convolution failed: '+str(status))
            result=out[:,:,:co].transpose(2,0,1)[None]
            self.values[index]=(x.copy(),result.copy(order='K'))
        self.calls+=1;self.trace.append(dict(layer=index,input_SHA256=array_sha(x),shape=list(x.shape)))
        return result
    def _parameters(self,index,x,w,bias,scale):
        acc=self.conv(index,x,w);_,co,h,width=acc.shape;padded=(co+7)//8*8
        packed=np.zeros((h,width,padded),np.int32);packed[:,:,:co]=acc[0].transpose(1,2,0)
        parameters=np.zeros(padded*8+(256 if index in self.activation else 0),np.uint8)
        values=parameters[:padded*8].view(np.uint32).reshape(padded,2)
        values[:co,0]=np.asarray(bias,np.int32).view(np.uint32);values[:co,1]=np.asarray(scale,np.float32).view(np.uint32)
        if index in self.activation:parameters[padded*8:]=self.activation[index].view(np.uint8)
        return packed,parameters,h,width,co,padded
    def conv_quantized(self,index,x,w,bias,scale,qscale,zero):
        packed,parameters,h,width,co,padded=self._parameters(index,x,w,bias,scale)
        out=np.empty((h,width,padded),np.int8)
        fn=self.lib.ct_native_fused if index in self.activation else self.lib.ct_native_quant
        status=fn(packed.ctypes.data,out.ctypes.data,parameters.ctypes.data,h*width*padded//8,co,
            int(np.asarray(qscale,np.float32).view(np.uint32).item()),int(zero.item())&0xffffffff)
        if status:raise RuntimeError('Original quantized writer failed: '+str(status))
        out.flags.writeable=False;return out[:,:,:co].transpose(2,0,1)[None]
    def conv_quantized_pool(self,index,x,w,bias,scale,qscale,zero):
        if index not in self.pool_tables:raise RuntimeError('Pool LUT not configured')
        packed,parameters,h,width,co,padded=self._parameters(index,x,w,bias,scale)
        full=np.empty((h,width,padded),np.int8);small=np.empty((h//2,width//2,padded),np.int8)
        status=self.lib.ct_native_pool(packed.ctypes.data,full.ctypes.data,small.ctypes.data,parameters.ctypes.data,
            self.pool_tables[index].ctypes.data,h,width,co,int(np.asarray(qscale,np.float32).view(np.uint32).item()),int(zero.item())&0xffffffff)
        if status:raise RuntimeError('R6 writer pool failed: '+str(status))
        self.pool_calls+=1;full.flags.writeable=False;small.flags.writeable=False
        return full[:,:,:co].transpose(2,0,1)[None],small[:,:,:co].transpose(2,0,1)[None]

def pair(library):
    reference=NativeBackend(library);candidate=NativeBackend(library,reference)
    old=Graph(MODEL,reference);new=PoolGraph(MODEL,candidate,library=LIBRARY)
    assert len(new.fused_layers)==8 and [row['conv_id'] for row in new.pl_fused_pools]==[1,3,5]
    assert not any(node['op'] in ('MaxPool','PoolQuantize') for node in new.nodes)
    return reference,candidate,old,new

def compare(reference,candidate,old,new,expected_input,candidate_input):
    reference.values.clear();reference.trace=[];candidate.trace=[]
    previous=(reference.calls,candidate.calls,candidate.pool_calls)
    expected=old(expected_input);actual=new(candidate_input)
    np.testing.assert_array_equal(actual,expected)
    assert reference.trace==candidate.trace
    assert (reference.calls-previous[0],candidate.calls-previous[1],candidate.pool_calls-previous[2])==(18,18,3)
    return dict(original18_inputs_and_final_float32_logits_exact=True,convolution_inputs=candidate.trace,
        native_R6_writer_pool_calls=3,logits_SHA256=array_sha(actual))

def check_compiled():
    compiled=json.loads((BUILD/'compiled.json').read_text());assert sha(LIBRARY)==compiled['library_SHA256']
    for name,digest in compiled['source_and_evidence_SHA256'].items():assert sha(ROOT/name)==digest,name

def run(preflight=False):
    project_storage.check(110_000_000);check_compiled()
    scope=os.add_dll_directory(str(COMPILER.parent));library=C.CDLL(str(LIBRARY))
    folder=HERE/('preflight_native' if preflight else 'whole139_native');assert not folder.exists();folder.mkdir()
    reference,candidate,old,new=pair(library);rows=[];started=time.perf_counter()
    bindings={p.relative_to(ROOT).as_posix():sha(p) for p in sources()}
    if preflight:
        random=np.random.default_rng(260)
        for h,w in ((8,8),(16,24),(32,32)):
            x=random.random((1,5,h,w),dtype=np.float32)
            rows.append(dict(shape=[h,w],**compare(reference,candidate,old,new,x,x)))
        class MissingCapability:pass
        try:PoolGraph(MODEL,MissingCapability(),library=LIBRARY)
        except RuntimeError as e:assert 'fallback is disabled' in str(e)
        else:raise AssertionError('Non-PL pool capability admitted')
        try:new.pool(None)
        except RuntimeError:pass
        else:raise AssertionError('PS pool fallback admitted')
        input_SHA=None
    else:
        gate=json.loads((HERE/'preflight_native/verified.json').read_text());assert gate['all3_shapes_exact']
        source=ROOT/'fixtures/own_ct/CT-chest.nrrd';image=prepare_grid(sitk.ReadImage(str(source)))
        ct=sitk.GetArrayFromImage(image);assert ct.shape==(139,512,512)
        prepare=ContextPreparer(new,ct,image.GetSpacing()[2]);input_SHA=sha(source)
        for z in range(len(ct)):
            reference_input=make_context(ct,z,image.GetSpacing()[2])[None]
            row=dict(slice=z,**compare(reference,candidate,old,new,reference_input,prepare(z)))
            rows.append(row);save(folder/f'slice{z:03d}.json',row)
            print(json.dumps(dict(slice=z+1,total=139,all18_inputs_exact=True,logits_exact=True,
                pool_calls=candidate.pool_calls,elapsed_seconds=time.perf_counter()-started)),flush=True)
        assert len(rows)==139 and candidate.pool_calls==417 and candidate.calls==2502
    for name,digest in bindings.items():assert sha(ROOT/name)==digest,name
    save(folder/'verified.json',dict(status='native_graph_preflight_passed' if preflight else 'native_original_full139_graph_R6_pool_exact_not_board',
        all3_shapes_exact=preflight,full139_test_completed=not preflight,cases=rows,input_SHA256=input_SHA,
        source_and_evidence_SHA256=bindings,library_SHA256=sha(LIBRARY),seconds=time.perf_counter()-started,
        original_graph_and_model_unchanged=True,original_full_skip_retained_and_all3_pool_nodes_replaced=True,
        native_R6_writer_pool_used_no_PS_pool_fallback=True,
        native_HLS_C_not_real_RTL_or_DFX_or_board_acceleration=True,
        actual_RTL_RM100MHz_all5PR_ARM_BO_lifetimes_board139_and_strongestPS_speed_still_required=True,
        PL_accessed=False,production_promoted=False,whole_goal_completed=False))
    scope.close();print('PASS',folder.name,'all18 inputs and logits exact; native C simulation only',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('build','preflight','full'));args=parser.parse_args()
    if args.action=='build':build()
    else:run(args.action=='preflight')
