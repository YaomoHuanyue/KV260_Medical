"""Board regression: separate contexts for baseline/fused parameter caches."""
import sys,json,os,time,hashlib,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import SimpleITK as sitk
from ct_pl.run import ROOT,backend
from ct_pl.stream_graph import MappedGraph,ContextPreparer
from ct_pl.fused_graph import FusedGraph
from airway.ct_geometry import prepare_grid
from airway.ct_segmentation import write_json

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'outputs/ct_accuracy_v2/board_pl_profile_fusion256');args=parser.parse_args()
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    os.environ['CT_PL_STATUS_PATH']=str(out/'status.json')
    write_json(out/'status.json',dict(status='running',pid=os.getpid()))
    original=sitk.ReadImage(str(ROOT/'data/CT-chest.nrrd'));rows=[]
    try:
        for model in ['ct_pl/model','outputs/ct_accuracy_v2/pl_model']:
            folder=ROOT/model;plan=json.loads((folder/'graph.json').read_text());physical='preprocessing' in plan
            image=prepare_grid(original) if physical else original
            ct=sitk.GetArrayFromImage(image);spacing=image.GetSpacing()[2] if physical else None
            references={}
            for name,cls in [('mapped',MappedGraph),('fused',FusedGraph)]:
                b=backend(output_pool=True)
                try:
                    g=cls(folder,b);prep=ContextPreparer(g,ct,spacing);g(prep(90))
                    actual=b.conv_quantized;calls=[]
                    def timed(id,x,*args):
                        digest=hashlib.sha256(x.tobytes()).hexdigest()
                        t=time.perf_counter();got=actual(id,x,*args);dt=time.perf_counter()-t
                        phases={n:b.lib.ct_last_phase(b.handle,i) for i,n in enumerate(['input_copy','input_sync','control','pl_wait','output_sync','output_copy','output_prepare_sync'])}
                        calls.append(dict(layer=id,input_sha256=digest,seconds=dt,phases=phases));return got
                    b.conv_quantized=timed
                    for z in [0,90,len(ct)-1]:
                        calls.clear();got=g(prep(z));hashes=[c['input_sha256'] for c in calls]
                        if name=='mapped':references[z]=(got.copy(),hashes)
                        else:
                            np.testing.assert_array_equal(got,references[z][0]);assert hashes==references[z][1]
                        rows.append(dict(model=model,scheduler=name,slice=z,logits_exact=True,all_18_inputs_exact=True,layers=list(calls),fused_layers=getattr(g,'fused_layers',[])))
                        print(model,name,z,'exact',flush=True)
                    # Separate timing loop excludes validation hashes and copies.
                    b.conv_quantized=actual;timings=[]
                    for repeat in range(3):
                        prep.planes.clear();t=time.perf_counter();x=prep(90);input_time=time.perf_counter()-t
                        hw=b.hardware_seconds;t=time.perf_counter();g(x)
                        timings.append(dict(graph_seconds=time.perf_counter()-t,pl_wait_seconds=b.hardware_seconds-hw,input_seconds=input_time))
                    rows.append(dict(model=model,scheduler=name,timings=timings))
                finally:b.close()
        sources={n:hashlib.sha256((ROOT/'ct_pl'/n).read_bytes()).hexdigest() for n in ['fused_graph.py','runtime.py','xrt_bridge.cpp','run.py','build/libct_xrt.so']}
        write_json(out/'profile.json',dict(status='completed',rows=rows,sources=sources,loaded_bit_bin_sha256=Path('/run/kv260-ct-loaded.sha256').read_text().strip()))
        write_json(out/'status.json',dict(status='completed'))
    except Exception as exc:
        write_json(out/'status.json',dict(status='failed',error=str(exc)));raise
if __name__=='__main__':main()
