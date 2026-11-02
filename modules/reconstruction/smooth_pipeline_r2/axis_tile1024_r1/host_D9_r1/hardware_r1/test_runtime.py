"""Exercise the production array/owner wrapper through the real D9 native algorithm."""
from pathlib import Path
import concurrent.futures
import ctypes as C
import hashlib
import json
import os
import sys
import threading

import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[5]
sys.path.insert(0,str(ROOT))
from modules.reconstruction.smooth_pipeline_r2.axis_tile1024_r1.host_D9_r1.hardware_r1.runtime import Session,EDGE


class NativeAdapter:
    """C API shape model; arithmetic is the unchanged compiled D9 host/kernel."""
    def __init__(self,path):
        self.lib=C.CDLL(str(path));self.calls=self.restores=self.closes=0
        self.fn=self.lib.mesh_smooth
        self.fn.argtypes=[C.c_void_p]*11+[C.c_uint32]*3+[C.c_float,C.c_uint32]
        self.lib.D8_host_stat.argtypes=[C.c_uint32];self.lib.D8_host_stat.restype=C.c_uint64
    def D9_run(self,handle,*args):
        self.calls+=1
        pointers=list(args[:11]);nv,nf,nnz,limit,iterations,all_work,phases,counters=args[11:]
        temporary=[]
        for i in range(5,10):
            if pointers[i] is None:
                temporary.append(np.zeros((nv,4),'<f4'));pointers[i]=temporary[-1].ctypes.data
        self.fn(*pointers,nv,nf,nnz,limit,iterations)
        counters[0]=self.lib.D8_host_stat(0);counters[1]=self.lib.D8_host_stat(1)
        counters[2]=counters[1]*64;counters[6]=123456;counters[7]=1
        return 0
    def D9_restore(self,handle):self.restores+=1;return 0
    def D9_close(self,handle):self.closes+=1;return 0
    def D9_error(self):return b'emulated C API error'


def main():
    platform='Windows' if os.name=='nt' else 'ARM'
    out=HERE/('runtime_wrapper_'+platform+'_r1.json');assert not out.exists()
    directories=[]
    if os.name=='nt':
        compiler=Path('F:/AMDDesignTools/2025.2.1/Vitis/tps/mingw/10.0.0/win64.o/nt/bin')
        directories.append(os.add_dll_directory(str(compiler)))
        library=HERE.parents[1]/'native_r1/build_Windows_r1/candidate.dll'
        reference=ROOT/'modules/reconstruction/smooth_pipeline_r2/axis_load4_r1/build_Windows/reference.dll'
    else:
        library=HERE.parents[1]/'arm_native_r1/build_r1/candidate.so'
        reference=ROOT/'modules/reconstruction/smooth_pipeline_r2/axis_load4_r1/host_D8_r1/arm_cross_r1/build_r1/reference.so'
    fake=NativeAdapter(library)
    session=Session();session.handle=1;session.owner=threading.get_ident();session.lib=fake
    nv=8;rows=[0];entries=[]
    for i in range(nv):
        neighbours=[j for j in (i-1,i+1) if 0<=j<nv]
        entries.extend((j,1/len(neighbours)) for j in neighbours);rows.append(len(entries))
    points=np.zeros((nv,4),'<f4');points[:,:3]=np.arange(nv*3,dtype='<f4').reshape(nv,3)/17
    frozen=np.zeros(nv,'<u4');frozen[[0,-1]]=1
    inputs=[points,np.array(rows,'<u4'),np.array(entries,dtype=EDGE),frozen,np.empty((0,4),'<u4')]
    initial=[np.full((nv,4),i+.125,'<f4') for i in range(5)]
    expected=[v.copy() for v in initial];report_ref=np.zeros(16,'<u4')
    ref=C.CDLL(str(reference)).mesh_smooth;ref.argtypes=[C.c_void_p]*11+[C.c_uint32]*3+[C.c_float,C.c_uint32]
    ref(*[v.ctypes.data for v in inputs+expected+[report_ref]],nv,0,len(entries),.25,2)
    actual=[v.copy() for v in initial];report=np.zeros(16,'<u4')
    metric=session.run_full(inputs,actual,report,nv,0,len(entries),.25,2)
    for a,b in zip(actual,expected):np.testing.assert_array_equal(a.view('<u4'),b.view('<u4'))
    np.testing.assert_array_equal(report,report_ref)
    assert metric['graph_requests']>0 and metric['graph_DMA_bytes']==metric['graph_beats']*64
    assert metric['all_five_work_banks_read_back']
    output=initial[0].copy();status=np.zeros(16,'<u4')
    metric=session.run(inputs,output,status,nv,0,len(entries),.25,2)
    np.testing.assert_array_equal(output.view('<u4'),expected[0].view('<u4'))
    assert not metric['all_five_work_banks_read_back'] and fake.calls==2
    negative=[]
    def reject(name,function):
        before=fake.calls
        try:function()
        except (ValueError,RuntimeError):negative.append(name)
        else:raise AssertionError('Expected rejection: '+name)
        assert fake.calls==before
    for value in (0,1_000_001,True,1.5):
        reject('invalid_vertices_'+str(value),lambda v=value:session.run(inputs,output,status,v,0,len(entries),.25,2))
    for value in (0,17,True,2.5):
        reject('invalid_iterations_'+str(value),lambda v=value:session.run(inputs,output,status,nv,0,len(entries),.25,v))
    for value in (-1,float('inf'),float('nan')):
        reject('invalid_limit_'+str(value),lambda v=value:session.run(inputs,output,status,nv,0,len(entries),v,2))
    for value in (output.astype('f8'),output[:,::2],output.ravel()[:-1]):
        reject('invalid_output_dtype_stride_or_size',lambda v=value:session.run(inputs,v,status,nv,0,len(entries),.25,2))
    read_only=output.copy();read_only.flags.writeable=False
    reject('readonly_output',lambda:session.run(inputs,read_only,status,nv,0,len(entries),.25,2))
    reject('input_output_alias',lambda:session.run(inputs,inputs[0],status,nv,0,len(entries),.25,2))
    reject('work_bank_alias',lambda:session.run_full(inputs,[output]*5,status,nv,0,len(entries),.25,2))
    reject('report_alias',lambda:session.run(inputs,output,output.view('<u4').ravel()[:16],nv,0,len(entries),.25,2))
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(lambda:reject('wrong_owner_thread',lambda:session.run(inputs,output,status,nv,0,len(entries),.25,2))).result()
    session.restore();session.restore();assert fake.restores==1
    session.__exit__(None,None,None);assert fake.closes==1 and fake.restores==1
    reject('closed_session',lambda:session.run(inputs,output,status,nv,0,len(entries),.25,2))
    record=dict(status='D9_production_wrapper_actual_native_algorithm_exact_reference_and_pre_native_refusals_passed',
        host=platform,full5_banks_and16_reports_exact_immutable_reference=True,
        final_bank_only_production_path_exact_same_reference=True,negative_cases=negative,
        actual_native_algorithm_used=True,XRT_and_C_API_adapter_emulated=True,PL_accessed=False,
        source_SHA256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (Path(__file__),HERE/'runtime.py',library,reference)},
        production_promoted=False,whole_goal_completed=False)
    with out.open('x',encoding='utf-8') as stream:json.dump(record,stream,indent=2);stream.write('\n')
    print('PASS',platform,'actual D9 native algorithm through production wrapper;',len(negative),'pre-native refusals')


if __name__=='__main__':
    if os.name=='nt':
        threading.stack_size(64*1024**2)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:executor.submit(main).result()
    else:main()
