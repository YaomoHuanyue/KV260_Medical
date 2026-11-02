"""Frozen INT8 student evaluated on prespecified AeroPath manual-refined annotations."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,json,time
import numpy as np
import onnxruntime as ort
import SimpleITK as sitk
from airway.ct_segmentation import require_geometry,refine_airway,write_json,sha256
ROOT=Path(__file__).resolve().parents[1]

def scores(pred,truth):
    a=sitk.GetArrayViewFromImage(pred);b=sitk.GetArrayViewFromImage(truth);require_geometry(pred,truth)
    intersection=na=nb=0
    for z in range(len(a)):
        aa=a[z]>0;bb=b[z]>0;intersection+=int((aa&bb).sum());na+=int(aa.sum());nb+=int(bb.sum())
    return {'dice':2*intersection/(na+nb) if na+nb else None,'precision':intersection/na if na else None,'recall':intersection/nb if nb else None,'prediction_voxels':na,'reference_voxels':nb}

def main():
    p=argparse.ArgumentParser();p.add_argument('--case',choices=['1','2','3'],required=True);a=p.parse_args()
    data=ROOT/'resources/public_ct/aeropath'/a.case;out=ROOT/'outputs/ct_external_validation'/a.case;out.mkdir(parents=True,exist_ok=True)
    paths=[data/f'{a.case}_CT_HR{suffix}.nii.gz' for suffix in ['', '_label_airways','_label_lungs']]
    limit=time.monotonic()+1800
    while not all(f.exists() for f in paths):
        if time.monotonic()>limit:raise TimeoutError('Prespecified case download incomplete')
        time.sleep(10)
    image=sitk.ReadImage(str(paths[0]));canonical=sitk.DICOMOrient(image,'LPS')
    spacing=(.7617189884185791,.7617189884185791,2.5)
    size=[int(np.ceil((n-1)*s/t))+1 for n,s,t in zip(canonical.GetSize(),canonical.GetSpacing(),spacing)]
    grid=sitk.Image(size,sitk.sitkFloat32);grid.SetOrigin(canonical.GetOrigin());grid.SetDirection(canonical.GetDirection());grid.SetSpacing(spacing)
    ctimage=sitk.Resample(canonical,grid,sitk.Transform(),sitk.sitkLinear,-1000,sitk.sitkFloat32);ct=sitk.GetArrayFromImage(ctimage)
    model=ROOT/'outputs/ct_student_refined/int8/experimental_student_int8.onnx'
    opts=ort.SessionOptions();opts.intra_op_num_threads=4
    session=ort.InferenceSession(str(model),sess_options=opts,providers=['CPUExecutionProvider'])
    masks={n:np.zeros(ct.shape,np.uint8) for n in ['lung','airway']};start=time.perf_counter()
    for z in range(len(ct)):
        idx=np.clip(np.arange(z-2,z+3),0,len(ct)-1);x=(np.clip(ct[idx],-1000,400)+1000)/1400
        h,w=x.shape[-2:];x=np.pad(x[None],((0,0),(0,0),(0,(-h)%8),(0,(-w)%8)),mode='edge')
        y=session.run(None,{'ct_context':x})[0][0,:,:h,:w]>=0
        masks['lung'][z]=y[0];masks['airway'][z]=y[1]
    infer=time.perf_counter()-start
    raw=masks['airway'].copy();post_error=None;tick=time.perf_counter()
    try:masks['airway'],_=refine_airway(ctimage,raw,include_proximal=False)
    except RuntimeError as exc:post_error=str(exc);masks['airway']=np.zeros_like(raw)
    post=time.perf_counter()-tick;metrics={}
    for name,array,truth_path in [('lung',masks['lung'],paths[2]),('airway_raw',raw,paths[1]),('airway',masks['airway'],paths[1])]:
        pred=sitk.GetImageFromArray(array);pred.CopyInformation(ctimage)
        truth=sitk.ReadImage(str(truth_path));require_geometry(truth,image)
        pred=sitk.Resample(pred,image,sitk.Transform(),sitk.sitkNearestNeighbor,0,sitk.sitkUInt8)
        metrics[name]=scores(pred,truth);sitk.WriteImage(pred,str(out/f'{name}_mask.nii.gz'),True)
    report={'status':'completed','case':a.case,'model_sha256':sha256(model),'input_sha256':sha256(paths[0]),
        'source':'https://zenodo.org/records/10069289','license':'CC-BY-4.0','annotation_kind':'manual-refined, pulmonologist-verified dataset annotations',
        'student_trained_on_this_case':False,'used_for_threshold_tuning':False,'used_for_quantization_calibration':False,
        'teacher_training_overlap_excluded':False,'metrics':metrics,'nodule_metrics':None,'nodule_note':'No nodule ground truth in this dataset',
        'resampling_spacing_xyz_mm':list(spacing),'original_spacing_xyz_mm':list(image.GetSpacing()),'inference_seconds_pc':infer,'postprocess_seconds_pc':post,
        'postprocess_error':post_error,'scope':'three prespecified external cases; not a clinical validation or a benchmark-wide claim'}
    write_json(out/'report.json',report);print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
