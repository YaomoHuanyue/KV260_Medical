"""Profile a real full-size slice after full-volume benchmarks have finished."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,json,time,resource,os
import numpy as np
import SimpleITK as sitk
from ct_pl.run import backend,tensor,ROOT
from ct_pl.runtime import Graph
from ct_pl.quantized_runtime import QuantizedGraph
from ct_pl.native_graph import NativeGraph
from airway.ct_geometry import prepare_grid
from airway.ct_segmentation import write_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--model-dir',type=Path,default=ROOT/'outputs/ct_accuracy_v2/pl_model');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    os.environ['CT_PL_STATUS_PATH']=str(a.output/'status.json')
    write_json(a.output/'status.json',{'status':'running','pid':os.getpid(),'action':'profile'})
    original=sitk.ReadImage(str(ROOT/'data/CT-chest.nrrd'))
    plan=json.loads((a.model_dir/'graph.json').read_text());physical='preprocessing' in plan
    image=prepare_grid(original) if physical else original;ct=sitk.GetArrayFromImage(image)
    x=tensor(ct,90,image.GetSpacing()[2] if physical else None)
    b=backend();rows=[];original_conv=b.conv;original_quantized=b.conv_quantized;calls=[]
    def timed_call(fn,id,x,w,*params):
        before=b.hardware_seconds;tick=time.perf_counter();y=fn(id,x,w,*params)
        calls.append(dict(layer=id,input_shape=list(x.shape),weights_shape=list(w.shape),host_and_pl_seconds=time.perf_counter()-tick,pl_wait_seconds=b.hardware_seconds-before))
        return y
    def timed(id,x,w):return timed_call(original_conv,id,x,w)
    def timed_quantized(id,x,w,*params):return timed_call(original_quantized,id,x,w,*params)
    try:
        reference=None
        for name,cls in [('original',Graph),('quantized_activations',QuantizedGraph),('native_nhwc',NativeGraph)]:
            g=cls(a.model_dir,b);b.conv=original_conv;b.conv_quantized=original_quantized;g(x)
            for repeat in range(3):
                calls=[];b.conv=timed;b.conv_quantized=timed_quantized;tick=time.perf_counter();y=g(x);elapsed=time.perf_counter()-tick
                if reference is None:reference=y.copy()
                else:np.testing.assert_array_equal(y,reference)
                conv=sum(c['host_and_pl_seconds'] for c in calls);pl=sum(c['pl_wait_seconds'] for c in calls)
                row=dict(scheduler=name,repeat=repeat+1,seconds=elapsed,pl_wait_seconds=pl,packing_sync_copy_seconds=conv-pl,ps_graph_seconds=elapsed-conv,layers=calls,logits_exact=True)
                rows.append(row);print(json.dumps({k:v for k,v in row.items() if k!='layers'}),flush=True)
        write_json(a.output/'profile.json',dict(status='completed',native_requantization=not b.pl_quantization,pl_requantization=b.pl_quantization,model_sha256=plan['source_sha256'],loaded_bit_bin_sha256=Path('/run/kv260-ct-loaded.sha256').read_text().strip(),buffer_mode=os.environ.get('CT_PL_BO_MODE','cacheable'),slice=90,rows=rows,process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            note='Sequential isolated single-slice timings; PL wait includes polling. Peak RSS belongs to both scheduler variants in one process.'))
        write_json(a.output/'status.json',{'status':'completed','action':'profile'})
    finally:b.close()

if __name__=='__main__':main()
