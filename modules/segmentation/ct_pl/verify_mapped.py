"""Board verification of leased XRT buffers, fan-out and exact graph outputs."""
import sys,json,time,gc,argparse,hashlib,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import SimpleITK as sitk
from ct_pl.run import ROOT,backend
from ct_pl.stream_graph import StreamGraph,MappedGraph,ContextPreparer
from airway.ct_geometry import prepare_grid
from airway.ct_segmentation import write_json


def parameters(folder):
    plan=json.loads((folder/'graph.json').read_text());arrays=dict(np.load(folder/'tensors.npz'));result={}
    for i,n in enumerate(plan['nodes'][:-1]):
        if n['op']=='Conv':
            c=n['integer'];q=plan['nodes'][i+1];assert q['op']=='QuantizeLinear'
            result[c['id']]=(arrays[c['bias']],arrays[c['input_scale']]*arrays[c['weight_scale']],*[arrays[k] for k in q['inputs'][1:]])
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);os.environ['CT_PL_STATUS_PATH']=str(a.output/'status.json')
    write_json(a.output/'status.json',dict(status='running',pid=os.getpid()))
    original=sitk.ReadImage(str(ROOT/'data/CT-chest.nrrd'));rows=[];layers=[]
    try:
        for model in ['ct_pl/model','outputs/ct_accuracy_v2/pl_model']:
            folder=ROOT/model;params=parameters(folder);vectors=np.load(folder/'layer_vectors.npz');b=backend(output_pool=True)
            try:
                retained=[]
                for id in range(18):
                    x,w,acc=[vectors[f'{n}_{id}'] for n in ['x','w','y']]
                    bias,scale,qs,qz=params[id]
                    expected=np.clip(np.rint((acc+bias[None,:,None,None]).astype(np.float32)*scale[None,:,None,None]/qs)+qz,-128,127).astype(np.int8)
                    got=b.conv_quantized(id,x,w,*params[id]);np.testing.assert_array_equal(got,expected)
                    retained.append((got,expected));layers.append(dict(model=model,layer=id,exact=True))
                # Every output is still readable after subsequent layers execute.
                for got,expected in retained:np.testing.assert_array_equal(got,expected)
                del got,expected,retained
                plan=json.loads((folder/'graph.json').read_text());physical='preprocessing' in plan
                image=prepare_grid(original) if physical else original;ct=sitk.GetArrayFromImage(image)
                graph=MappedGraph(folder,b);copied=StreamGraph(folder,b);prepare=ContextPreparer(graph,ct,image.GetSpacing()[2] if physical else None)
                original_call=b.conv_quantized;phases=np.zeros(7)
                def timed(*args):
                    result=original_call(*args)
                    phases[:]+=np.array([b.lib.ct_last_phase(b.handle,i) for i in range(7)])
                    return result
                b.conv_quantized=timed
                for z in [0,90,len(ct)-1,0,90,len(ct)-1]:
                    x=prepare(z);b.output_pool=False;reference=copied(x)
                    b.output_pool=True;phases[:]=0;tick=time.perf_counter();got=graph(x);elapsed=time.perf_counter()-tick
                    np.testing.assert_array_equal(got,reference)
                    row=dict(model=model,slice=z,seconds=elapsed,phases_seconds=dict(zip(['input_copy','input_sync','control','pl_wait','output_sync','output_copy','output_prepare_sync'],phases.tolist())),output_pool_bytes=b.lib.ct_output_pool_bytes(b.handle),logits_exact=True)
                    rows.append(row);print(json.dumps(row),flush=True)
                # Keep a non-contiguous output view across close: its lease must
                # retain the context/device, then release it when all views die.
                b.output_pool=True;id=0
                held=b.conv_quantized(id,vectors['x_0'],vectors['w_0'],*params[id])[:,:,::2,::2]
                saved=held.copy();b.close();gc.collect();np.testing.assert_array_equal(held,saved)
                del held;saved=None;gc.collect()
            finally:b.close()
            reopened=backend();reopened.close()
        sources={n:hashlib.sha256((ROOT/'ct_pl'/n).read_bytes()).hexdigest() for n in ['xrt_bridge.cpp','runtime.py','run.py','stream_graph.py','native_graph.py','build/libct_xrt.so']}
        report=dict(status='completed',loaded_bit_bin_sha256=Path('/run/kv260-ct-loaded.sha256').read_text().strip(),sources=sources,layers=layers,rows=rows,retained_outputs_exact=True,view_survives_backend_close=True,hardware_lock_released_after_last_view=True)
        write_json(a.output/'validation.json',report);write_json(a.output/'status.json',dict(status='completed'))
    except Exception as exc:
        write_json(a.output/'status.json',dict(status='failed',error=str(exc)));raise

if __name__=='__main__':main()
