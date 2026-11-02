"""Compare every quantized convolution input and final logits on real CT slices."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,ctypes,hashlib,json,time
import numpy as np
import SimpleITK as sitk
from ct_pl.runtime import Graph,TorchInteger
from ct_pl.quantized_runtime import QuantizedGraph
from ct_pl.native_graph import NativeGraph
from airway.ct_geometry import prepare_grid,make_context

ROOT=Path(__file__).resolve().parents[1]

def tensor(ct,z,spacing_z=None):
    x=make_context(ct,z,spacing_z) if spacing_z is not None else (np.clip(ct[np.clip(np.arange(z-2,z+3),0,len(ct)-1)].astype(np.float32),-1000,400)+1000)/1400
    h,w=x.shape[-2:]
    return np.pad(x[None],((0,0),(0,0),(0,(-h)%8),(0,(-w)%8)),mode='edge')

class Recorded:
    def __init__(self):self.backend=TorchInteger();self.values={}
    def conv(self,id,x,w):
        raw=self.backend.conv(id,x,w)
        _,co,h,width=raw.shape
        packed=np.zeros((h,width,(co+7)//8*8),np.int32)
        packed[:,:,:co]=raw[0].transpose(1,2,0)
        y=packed[:,:,:co].transpose(2,0,1)[None]
        self.values[id]=(x.copy(),y.copy(order='K'))
        return y

class Replay:
    def __init__(self,values):self.values=values;self.layers=0
    def conv(self,id,x,w):
        expected,y=self.values[id]
        np.testing.assert_array_equal(x,expected,err_msg=f'Quantized layer {id} input differs')
        self.layers+=1;return y.copy(order='K')

class NativeReplay(Replay):
    def __init__(self,values):
        super().__init__(values)
        self.lib=ctypes.CDLL(str(ROOT/'ct_pl/build/ct_postprocess.dll'))
        self.fn=self.lib.ct_quantize_acc
        self.fn.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_float,ctypes.c_int]
        self.fn.restype=None
    def conv_quantized(self,id,x,w,bias,scale,qscale,zero):
        acc=self.conv(id,x,w);_,co,h,width=acc.shape;padded=(co+7)//8*8
        packed=np.zeros((h,width,padded),np.int32);packed[:,:,:co]=acc[0].transpose(1,2,0)
        bp=np.zeros(padded,np.int32);sp=np.zeros(padded,np.float32);bp[:co]=bias;sp[:co]=scale
        out=np.empty((h,width,padded),np.int8)
        self.fn(packed.ctypes.data,out.ctypes.data,h*width,padded,bp.ctypes.data,sp.ctypes.data,float(qscale.item()),int(zero.item()))
        return out[:,:,:co].transpose(2,0,1)[None]

def main():
    p=argparse.ArgumentParser();p.add_argument('--slices',type=int,nargs='+',default=[20,60,90,120]);a=p.parse_args()
    original=sitk.ReadImage(str(ROOT/'data/CT-chest.nrrd'));rows=[]
    for model in ['ct_pl/model','outputs/ct_accuracy_v2/pl_model']:
        folder=ROOT/model;plan=json.loads((folder/'graph.json').read_text())
        physical='preprocessing' in plan;image=prepare_grid(original) if physical else original
        ct=sitk.GetArrayFromImage(image)
        for z in a.slices:
            x=tensor(ct,z,image.GetSpacing()[2] if physical else None)
            recorded=Recorded();old=Graph(folder,recorded)
            tick=time.perf_counter();expected=old(x);elapsed=time.perf_counter()-tick
            for kind,cls,graph_cls in [('numpy_int8',Replay,QuantizedGraph),('native_fused_int8',NativeReplay,QuantizedGraph),('native_nhwc',NativeReplay,NativeGraph)]:
                replay=cls(recorded.values);new=graph_cls(folder,replay)
                got=new(x);np.testing.assert_array_equal(got,expected)
                row=dict(model=model,slice=z,scheduler=kind,convolution_inputs_exact=replay.layers,logits_exact=True,reference_seconds=elapsed)
                rows.append(row);print(json.dumps(row),flush=True)
    output=ROOT/'ct_pl/build/quantized_graph_validation.json'
    output.write_text(json.dumps(dict(status='passed',source_sha256=hashlib.sha256((ROOT/'ct_pl/quantized_runtime.py').read_bytes()).hexdigest(),native_postprocess_sha256=hashlib.sha256((ROOT/'ct_pl/postprocess.hpp').read_bytes()).hexdigest(),native_graph_sha256=hashlib.sha256((ROOT/'ct_pl/native_graph.py').read_bytes()).hexdigest(),native_ops_sha256=hashlib.sha256((ROOT/'ct_pl/graph_ops.cpp').read_bytes()).hexdigest(),rows=rows),indent=2)+'\n')

if __name__=='__main__':main()
