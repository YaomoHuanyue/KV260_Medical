"""Compare fused HLS-C writer and every downstream conv input to original graph."""
import sys,ctypes,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import SimpleITK as sitk
from ct_pl.fused_graph import FusedGraph
from ct_pl.stream_graph import ContextPreparer
from ct_pl.verify_quantized_graph import Recorded,NativeReplay,tensor
from ct_pl.runtime import Graph
from airway.ct_geometry import prepare_grid
ROOT=Path(__file__).resolve().parents[1]

class FusedReplay(NativeReplay):
    pl_activation_lut=True
    def __init__(self,values):
        super().__init__(values);self.tables={}
        self.native=ctypes.CDLL(str(ROOT/'ct_pl/build/fusion/ct_native.dll'))
        self.native.ct_native_fused.argtypes=[ctypes.c_void_p]*3+[ctypes.c_uint]*4
        self.native.ct_native_fused.restype=ctypes.c_int
    def configure_activation(self,id,table):self.tables[id]=table
    def allocate_activation(self,shape):return np.empty(shape,np.int8)
    def conv_quantized(self,id,x,w,bias,scale,qscale,zero):
        if id not in self.tables:return super().conv_quantized(id,x,w,bias,scale,qscale,zero)
        acc=self.conv(id,x,w);_,co,h,width=acc.shape;padded=(co+7)//8*8
        packed=np.zeros((h,width,padded),np.int32);packed[:,:,:co]=acc[0].transpose(1,2,0)
        parameters=np.zeros(padded*8+256,np.uint8)
        p=parameters[:padded*8].view(np.uint32).reshape(padded,2)
        p[:co,0]=bias.view(np.uint32);p[:co,1]=scale.view(np.uint32)
        parameters[padded*8:]=self.tables[id].view(np.uint8)
        out=np.empty((h,width,padded),np.int8)
        rc=self.native.ct_native_fused(packed.ctypes.data,out.ctypes.data,parameters.ctypes.data,h*width*padded//8,co,int(qscale.view(np.uint32).item()),int(zero.item())&0xffffffff)
        assert rc==0
        return out[:,:,:co].transpose(2,0,1)[None]

def main():
    original=sitk.ReadImage(str(ROOT/'data/CT-chest.nrrd'));rows=[]
    for model in ['ct_pl/model','outputs/ct_accuracy_v2/pl_model']:
        folder=ROOT/model;plan=json.loads((folder/'graph.json').read_text())
        physical='preprocessing' in plan;image=prepare_grid(original) if physical else original
        ct=sitk.GetArrayFromImage(image);spacing=image.GetSpacing()[2] if physical else None
        for z in [0,60,90,len(ct)-1]:
            recorded=Recorded();expected=Graph(folder,recorded)(tensor(ct,z,spacing))
            replay=FusedReplay(recorded.values);g=FusedGraph(folder,replay)
            got=g(ContextPreparer(g,ct,spacing)(z))
            np.testing.assert_array_equal(got,expected)
            assert replay.layers==18 and len(g.fused_layers)==8
            row=dict(model=model,slice=z,convolution_inputs_exact=18,logits_exact=True,fused_layers=g.fused_layers)
            rows.append(row);print(json.dumps(row),flush=True)
    sources={n:hashlib.sha256((ROOT/'ct_pl'/n).read_bytes()).hexdigest() for n in ['conv.cpp','fused_graph.py','runtime.py','xrt_bridge.cpp']}
    (ROOT/'ct_pl/build/fusion/graph_validation.json').write_text(json.dumps(dict(status='passed',sources=sources,rows=rows),indent=2)+'\n')
if __name__=='__main__':main()
