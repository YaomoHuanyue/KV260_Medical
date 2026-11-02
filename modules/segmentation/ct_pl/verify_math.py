"""Reference integer graph and actual-model layer vectors, generated before hardware testing."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,json,time
import numpy as np
import onnxruntime as ort
import SimpleITK as sitk
from ct_pl.runtime import Graph,TorchInteger
from airway.ct_segmentation import write_json,write_like,agreement,refine_airway,preview,sha256
from ct_student import context
from airway.ct_geometry import make_context,largest_airway_component
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--model-dir',type=Path,default=ROOT/'ct_pl/model');p.add_argument('--onnx',type=Path,default=ROOT/'outputs/ct_student_refined/int8/experimental_student_int8.onnx');p.add_argument('--reference-dir',type=Path,default=ROOT/'outputs/ct_student_refined/int8');p.add_argument('--output',type=Path,default=ROOT/'outputs/ct_integer_reference');a=p.parse_args()
    out=a.output;out.mkdir(parents=True,exist_ok=True)
    graph=Graph(a.model_dir,TorchInteger());image=sitk.ReadImage(str(ROOT/'data/CT-chest.nrrd'));ct=sitk.GetArrayFromImage(image)
    physical='preprocessing' in graph.plan
    tensor=lambda z:(make_context(ct,z,image.GetSpacing()[2]) if physical else context(ct,z))[None]
    data={};oracle=TorchInteger()
    def capture(id,x,w,acc):
        h,width=x.shape[-2:];small=x[:,:,h//2-4:h//2+4,width//2-5:width//2+6].copy()
        data[f'x_{id}']=small;data[f'w_{id}']=w;data[f'y_{id}']=oracle.conv(id,small,w)
    opts=ort.SessionOptions();opts.intra_op_num_threads=4
    session=ort.InferenceSession(str(a.onnx),sess_options=opts,providers=['CPUExecutionProvider'])
    x=tensor(90);logits=graph(x,capture);onnx_logits=session.run(None,{'ct_context':x})[0]
    np.savez_compressed(a.model_dir/'layer_vectors.npz',**data)
    math={'real_model_layers':len(data)//3,'slice':90,'max_abs_logit_difference_vs_ort':float(np.max(np.abs(logits-onnx_logits))),
        'threshold_disagreement_fraction_vs_ort':float(np.mean((logits>=0)!=(onnx_logits>=0))),
        'note':'Graph implements explicit INT32 accumulation and FP32 scales; optimized ORT may differ at quantization rounding boundaries.'}
    write_json(out/'math_validation.json',math);print(json.dumps(math),flush=True)
    masks={n:np.zeros(ct.shape,np.uint8) for n in ['lung','airway','nodule']};begin=time.perf_counter()
    for z in range(len(ct)):
        pred=graph(tensor(z))[0]>=0
        for c,n in enumerate(masks):masks[n][z]=pred[c]
        if z%16==0:print('slice',z,flush=True)
    infer=time.perf_counter()-begin;write_like(masks['airway'],image,out/'airway_mask_network.nii.gz')
    tick=time.perf_counter();masks['airway'],info=largest_airway_component(masks['airway']) if physical else refine_airway(image,masks['airway'],include_proximal=False);post=time.perf_counter()-tick
    compared={}
    for n,m in masks.items():
        write_like(m,image,out/f'{n}_mask.nii.gz')
        ref=sitk.GetArrayFromImage(sitk.ReadImage(str(a.reference_dir/f'{n}_mask.nii.gz')))
        compared[n]=agreement(m,ref)
    preview(image,masks,out/'ct_overlay.png')
    write_json(out/'report.json',{'status':'completed','input_sha256':sha256(ROOT/'data/CT-chest.nrrd'),'backend':'PC integer software reference',
        'inference_seconds':infer,'postprocess_seconds':post,'agreement_with_onnx':compared,'math':math,'pl_inference_implemented':False,'generalization_validated':False})

if __name__=='__main__':main()
