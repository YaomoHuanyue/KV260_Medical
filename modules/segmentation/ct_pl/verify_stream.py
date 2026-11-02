"""Exact input LUT, edge geometry, deferred fan-out and full graph regression."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import SimpleITK as sitk
from ct_pl.stream_graph import StreamGraph,ContextPreparer,Deferred
from ct_pl.quantized_runtime import Quantized,Concatenated
from ct_pl.verify_quantized_graph import Recorded,NativeReplay,tensor
from ct_pl.runtime import Graph
from airway.ct_geometry import prepare_grid
ROOT=Path(__file__).resolve().parents[1]


def inputs(graph):
    # Every possible signed HU, plus replicated Z boundaries and odd XY edges.
    ct=np.arange(65536,dtype=np.uint16).view(np.int16).reshape(1,256,256)
    for data in [ct,np.tile(ct[:,:253,:251],(3,1,1))]:
        for spacing in [None,1.0,2.5,5.0]:
            prepare=ContextPreparer(graph,data,spacing)
            for z,got in prepare.slices():
                expected=graph.quantize(tensor(data,z,spacing),prepare.scale,prepare.zero)
                np.testing.assert_array_equal(got.data,expected)
    raw=np.arange(256,dtype=np.uint8).view(np.int8).reshape(1,16,4,4)
    scale=np.array(.13,np.float32);zero=np.array(-17,np.int8)
    q=Quantized(raw,scale,zero);before=raw.copy()
    lazy=graph.resize(graph.relu(q))
    plain=Quantized(np.maximum(raw,zero).repeat(2,2).repeat(2,3),scale,zero)
    target=np.array(.21,np.float32)
    np.testing.assert_array_equal(graph.quantize(lazy,target,zero),graph.quantize(plain,target,zero))
    both=Concatenated([lazy,plain],1)
    expected=np.concatenate([graph.quantize(plain,target,zero)]*2,axis=1)
    np.testing.assert_array_equal(graph.quantize(both,target,zero),expected)
    np.testing.assert_array_equal(raw,before)


def main():
    original=sitk.ReadImage(str(ROOT/'data/CT-chest.nrrd'));rows=[]
    for model in ['ct_pl/model','outputs/ct_accuracy_v2/pl_model']:
        folder=ROOT/model;plan=json.loads((folder/'graph.json').read_text())
        image=prepare_grid(original) if 'preprocessing' in plan else original
        ct=sitk.GetArrayFromImage(image);spacing=image.GetSpacing()[2] if 'preprocessing' in plan else None
        inputs(StreamGraph(folder,None))
        for z in [0,20,60,90,120,len(ct)-1]:
            recorded=Recorded();expected=Graph(folder,recorded)(tensor(ct,z,spacing))
            replay=NativeReplay(recorded.values);graph=StreamGraph(folder,replay)
            got=graph(ContextPreparer(graph,ct,spacing)(z))
            np.testing.assert_array_equal(got,expected)
            assert replay.layers==18
            row=dict(model=model,slice=z,convolution_inputs_exact=18,logits_exact=True)
            rows.append(row);print(json.dumps(row),flush=True)
    sources={n:hashlib.sha256((ROOT/'ct_pl'/n).read_bytes()).hexdigest() for n in ['stream_graph.py','graph_ops.cpp','quantized_runtime.py']}
    (ROOT/'ct_pl/build/stream_validation.json').write_text(json.dumps(dict(status='passed',all_int16_hu_exact=True,edge_padding_and_physical_context_exact=True,sources=sources,rows=rows),indent=2)+'\n')

if __name__=='__main__':main()
