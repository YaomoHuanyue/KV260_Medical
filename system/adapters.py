"""Each worker imports only one frozen module, preventing airway package clashes."""
from pathlib import Path
import argparse,json,sys,time
from types import SimpleNamespace
import numpy as np
import SimpleITK as sitk
from .contracts import CLASSES,read_json,write_json,sha256,geometry,validate_masks

ROOT=Path(__file__).resolve().parents[1]

def segmentation(case,ct,output,options):
    module=ROOT/'modules/segmentation';sys.path.insert(0,str(module))
    (module/'outputs/xrt').mkdir(parents=True,exist_ok=True)
    from ct_pl.run import worker
    worker(SimpleNamespace(input=ct,output=output,model_dir=module/'outputs/ct_accuracy_v2/pl_model',
        scheduler='fused',slice_workers=2,repeats=1,save_airway_logits=True,
        reference_dir=None,no_preview=True))
    validate_masks(output,case['ct']['geometry'])

def reconstruction(case,ct,output,options):
    module=ROOT/'modules/reconstruction';sys.path.insert(0,str(module))
    (module/'outputs/xrt').mkdir(parents=True,exist_ok=True)
    from fpga.mc_host import crop_mask,to_mesh
    from fpga.mc_xrt_backend import XRTAccelerator
    from fpga.smooth_xrt_backend import SmoothSession,smooth
    from airway.mesh_reconstruction import vertex_normals
    from contextlib import nullcontext
    masks=Path(options['mask_dir']);validate_masks(masks,case['ct']['geometry'])
    accelerator=XRTAccelerator(module);layers={};start=time.perf_counter()
    with (SmoothSession(module) if options['surface']=='smooth' else nullcontext()) as session:
        for name in CLASSES:
            image=sitk.ReadImage(str(masks/f'{name}_mask.nii.gz'));array=sitk.GetArrayFromImage(image)
            stride=2 if options['quality']=='preview' and name=='lung' else 1
            begin=time.perf_counter();hardware=None;smoothing=None
            if np.any(array):
                cropped,offset=crop_mask(np.ascontiguousarray(array[::stride,::stride,::stride],dtype=np.uint8))
                words,hardware=accelerator.reconstruct(cropped)
                points,faces=to_mesh(words,np.asarray(image.GetSpacing())*stride,image.GetOrigin(),np.asarray(image.GetDirection()).reshape(3,3),offset)
                if options['surface']=='smooth':
                    limit=min(.10,.10*min(image.GetSpacing())) if name=='airway' else (.35 if name=='lung' else .15)
                    points,smoothing=smooth(points,faces,limit,module,session=session)
            else:
                points=np.empty((0,3),np.float32);faces=np.empty((0,3),np.uint32)
            normals=vertex_normals(points,faces)
            if not np.isfinite(points).all() or not np.isfinite(normals).all():raise ValueError('Nonfinite reconstructed mesh')
            np.savez(output/f'{name}.npz',points=points.astype(np.float32),faces=faces.astype(np.uint32),normals=normals)
            layers[name]=dict(vertices=len(points),triangles=len(faces),stride=stride,seconds=time.perf_counter()-begin,hardware=hardware,smoothing=smoothing)
    write_json(output/'report.json',dict(status='completed',coordinates='LPS',units='mm',backend='pl',surface=options['surface'],smoothing_backend='pl' if options['surface']=='smooth' else None,layers=layers,total_seconds=time.perf_counter()-start,viewer_generated=False))

def navigation(case,ct,output,options):
    module=ROOT/'modules/navigation';sys.path.insert(0,str(module))
    from navigation.pipeline import prepare,choose_target,run_route
    from pl.route_runtime import RouteXRT,RoutePlanner
    masks=Path(options['mask_dir']);validate_masks(masks,case['ct']['geometry'])
    session=RouteXRT()
    try:
        c,_=prepare(masks/'airway_mask.nii.gz',output,backend='pl',session=session)
        target=choose_target(c,lesion_path=masks/'nodule_mask.nii.gz' if options['target_lps'] is None else None,
            lesion_index=options['lesion_index'],target_lps_mm=options['target_lps'])
        planner=RoutePlanner(c,session=session)
        run_route(c,target,output,planner=planner,scope_diameter_mm=options['scope_diameter_mm'],
            safety_margin_mm=options['safety_margin_mm'],sample_mm=options['sample_mm'],smooth=True)
    finally:session.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['segmentation','reconstruction','navigation']);p.add_argument('request',type=Path);args=p.parse_args()
    r=read_json(args.request);case=r['case'];output=Path(r['output']);ct=Path(r['ct'])
    globals()[args.stage](case,ct,output,r['options'])

if __name__=='__main__':main()
