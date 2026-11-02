"""Board A/B validation of PS pool fusion against the previous scheduler."""
import sys, os, json, hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import SimpleITK as sitk
from ct_pl.run import ROOT, backend
from ct_pl.fused_graph import FusedGraph
from ct_pl.stream_graph import ContextPreparer
from airway.ct_geometry import prepare_grid

def main():
    out=ROOT/'outputs/ct_accuracy_v2/board_host_overlap_validation'
    out.mkdir(parents=True,exist_ok=False)
    os.environ['CT_PL_STATUS_PATH']=str(out/'status.json')
    (out/'status.json').write_text(json.dumps(dict(status='running',pid=os.getpid())))
    original=sitk.ReadImage(str(ROOT/'data/CT-chest.nrrd'));rows=[]
    previous=json.loads((ROOT/'outputs/ct_accuracy_v2/board_pl_profile_tripixel768/profile.json').read_text())
    previous_inputs={(r['model'],r['slice']):[v['input_sha256'] for v in r['layers']] for r in previous['rows'] if r.get('scheduler')=='fused' and 'slice' in r}
    for model in ['ct_pl/model','outputs/ct_accuracy_v2/pl_model']:
        folder=ROOT/model;physical='preprocessing' in json.loads((folder/'graph.json').read_text())
        image=prepare_grid(original) if physical else original;ct=sitk.GetArrayFromImage(image)
        reference={}
        for fusion in [0,1]:
            os.environ['CT_PS_POOL_FUSION']=str(fusion);b=backend(output_pool=True)
            try:
                g=FusedGraph(folder,b);prep=ContextPreparer(g,ct,image.GetSpacing()[2] if physical else None)
                assert len(g.fused_pools)==3*fusion
                actual=b.conv_quantized;inputs=[]
                def capture(id,x,*args):
                    inputs.append(hashlib.sha256(x.tobytes()).hexdigest())
                    return actual(id,x,*args)
                b.conv_quantized=capture
                for z in [0,90,len(ct)-1]:
                    inputs.clear();got=g(prep(z))
                    if not fusion:reference[z]=(got.copy(),list(inputs))
                    else:
                        np.testing.assert_array_equal(got,reference[z][0]);assert inputs==reference[z][1]
                        assert inputs==previous_inputs[(model,z)]
                        g.return_quantized=True;quantized=g(prep(z));g.return_quantized=False
                        np.testing.assert_array_equal(got>=0,quantized.data>=quantized.zero)
                        del quantized # Return its XRT lease before opening the next model.
                        rows.append(dict(model=model,slice=z,logits_exact=True,convolution_inputs_exact=18,pool_fusions=3,previous_release_inputs_exact=True,direct_masks_exact=True))
                    print(model,'fusion',fusion,'slice',z,'exact',flush=True)
            finally:b.close()
    report=dict(status='completed',rows=rows,loaded_bit_bin_sha256=Path('/run/kv260-ct-loaded.sha256').read_text().strip())
    (out/'report.json').write_text(json.dumps(report,indent=2))
    (out/'status.json').write_text(json.dumps(dict(status='completed')))
if __name__=='__main__':main()
