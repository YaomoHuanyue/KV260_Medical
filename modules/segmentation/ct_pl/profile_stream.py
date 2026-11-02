"""Compare the validated native and streaming schedules on the loaded PL image."""
import sys,json,time,os,hashlib,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import SimpleITK as sitk
from ct_pl.run import ROOT,backend,tensor
from ct_pl.native_graph import NativeGraph
from ct_pl.stream_graph import StreamGraph,MappedGraph,ContextPreparer
from airway.ct_geometry import prepare_grid
from airway.ct_segmentation import write_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--schedulers',nargs='+',choices=['native','stream','mapped'],default=['native','stream']);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    os.environ['CT_PL_STATUS_PATH']=str(a.output/'status.json')
    write_json(a.output/'status.json',dict(status='running',pid=os.getpid()))
    folder=ROOT/'outputs/ct_accuracy_v2/pl_model';plan=json.loads((folder/'graph.json').read_text())
    image=prepare_grid(sitk.ReadImage(str(ROOT/'data/CT-chest.nrrd')))
    ct=sitk.GetArrayFromImage(image);spacing=image.GetSpacing()[2]
    b=backend(output_pool='mapped' in a.schedulers);original=b.conv_quantized;calls=[];rows=[]
    def timed(*args):
        tick=time.perf_counter();hw=b.hardware_seconds;result=original(*args)
        elapsed=time.perf_counter()-tick
        phases={name:b.lib.ct_last_phase(b.handle,i) for i,name in enumerate(['input_copy','input_sync','control','pl_wait','output_sync','output_copy','output_prepare_sync'])} if hasattr(b.lib,'ct_last_phase') else {}
        calls.append(dict(layer=args[0],host_and_pl_seconds=elapsed,pl_wait_seconds=b.hardware_seconds-hw,phases_seconds=phases))
        return result
    try:
        reference=None
        for name in a.schedulers:
            cls={'native':NativeGraph,'stream':StreamGraph,'mapped':MappedGraph}[name];b.output_pool=name=='mapped'
            g=cls(folder,b)
            prepare=ContextPreparer(g,ct,spacing) if name in ['stream','mapped'] else lambda z:tensor(ct,z,spacing)
            b.conv_quantized=original;g(prepare(90));b.conv_quantized=timed
            for repeat in range(3):
                if name in ['stream','mapped']:prepare.planes.clear() # Include a cold context cache.
                calls.clear();tick=time.perf_counter();x=prepare(90);input_seconds=time.perf_counter()-tick
                tick=time.perf_counter();got=g(x);elapsed=time.perf_counter()-tick
                if reference is None:reference=got.copy()
                else:np.testing.assert_array_equal(got,reference)
                conv=sum(c['host_and_pl_seconds'] for c in calls);hw=sum(c['pl_wait_seconds'] for c in calls)
                row=dict(scheduler=name,repeat=repeat+1,input_seconds=input_seconds,graph_seconds=elapsed,pl_wait_seconds=hw,packing_sync_copy_seconds=conv-hw,ps_graph_seconds=elapsed-conv,logits_exact=True,layers=list(calls))
                rows.append(row);print(json.dumps({k:v for k,v in row.items() if k!='layers'}),flush=True)
        sources={n:hashlib.sha256((ROOT/'ct_pl'/n).read_bytes()).hexdigest() for n in ['stream_graph.py','graph_ops.cpp','runtime.py','native_graph.py','xrt_bridge.cpp','quantized_runtime.py','run.py','build/libct_graph_ops.so','build/libct_xrt.so']}
        write_json(a.output/'profile.json',dict(status='completed',model_sha256=plan['source_sha256'],loaded_bit_bin_sha256=Path('/run/kv260-ct-loaded.sha256').read_text().strip(),slice=90,rows=rows,sources=sources,note='Single-slice, cold context cache; overlap is measured only in the full-volume report. PL wait includes polling.'))
        write_json(a.output/'status.json',dict(status='completed'))
    except Exception as exc:
        write_json(a.output/'status.json',dict(status='failed',error=str(exc)));raise
    finally:b.close()

if __name__=='__main__':main()
