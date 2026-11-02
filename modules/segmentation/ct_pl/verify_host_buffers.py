"""Exercise ARM vector packing, pool LUTs, dirty PS reuse and clean PL reuse."""
import sys, os, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from ct_pl.run import ROOT, backend
from ct_pl.stream_graph import StreamGraph, ContextPreparer
from ct_pl.verify_stream import inputs

def main():
    out=ROOT/'outputs/ct_accuracy_v2/board_host_buffers'
    out.mkdir(exist_ok=False)
    os.environ['CT_PL_STATUS_PATH']=str(out/'status.json')
    (out/'status.json').write_text(json.dumps(dict(status='running',pid=os.getpid())))
    graph=StreamGraph(ROOT/'outputs/ct_accuracy_v2/pl_model',None)
    inputs(graph) # All signed HU values, odd XY padding, Z boundaries and spacings.
    rng=np.random.default_rng(260);cases=0
    for c in range(1,65):
        for h,w in [(2,2),(6,10),(16,8)]:
            x=rng.integers(-128,128,(h,w,c),dtype=np.int8)
            for table in [rng.integers(-128,128,256,dtype=np.int8),np.arange(256,dtype=np.uint8).view(np.int8),np.maximum(np.arange(256,dtype=np.uint8).view(np.int8),-17).astype(np.int8)]:
                expected=table[x.reshape(h//2,2,w//2,2,c).max(axis=(1,3)).view(np.uint8)]
                got=np.empty_like(expected)
                graph.ops.ct_pool_transform(x.ctypes.data,got.ctypes.data,h,w,c,table.ctypes.data)
                np.testing.assert_array_equal(got,expected);cases+=1
    b=backend(output_pool=True)
    try:
        weight=np.zeros((16,16,1,1),np.int8)
        for i in range(16):weight[i,i,0,0]=1
        bias=np.zeros(16,np.int32);scale=np.ones(16,np.float32);qs=np.array(1,np.float32);qz=np.array(0,np.int8)
        base=b.allocate_activation((32,32,16));old=None
        for i in range(32):
            base[:]=rng.integers(-64,65,base.shape,dtype=np.int8)
            x=base.transpose(2,0,1)[None]
            got=b.conv_quantized(0,x,weight,bias,scale,qs,qz)
            np.testing.assert_array_equal(got,x)
            assert not got.flags.writeable
            again=b.conv_quantized(0,got,weight,bias,scale,qs,qz)
            np.testing.assert_array_equal(again,x)
            if old is not None:np.testing.assert_array_equal(old[0],old[1])
            old=(again,again.copy())
    finally:b.close()
    report=dict(status='completed',arm_pool_cases=cases,all_int16_hu_exact=True,odd_geometry_context_exact=True,dirty_ps_rewrites=32,clean_pl_chains=32,read_only_pl_outputs=True,live_leases_not_recycled=True)
    (out/'report.json').write_text(json.dumps(report,indent=2))
    (out/'status.json').write_text(json.dumps(dict(status='completed')))
    print(json.dumps(report),flush=True)
if __name__=='__main__':main()
