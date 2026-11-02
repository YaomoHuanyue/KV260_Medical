"""Manual complete exact-offset field producer with explicit PS/PL backends."""
from dataclasses import replace
from pathlib import Path
import argparse,json,sys,time
import SimpleITK as sitk
from .case_io import load_case,save_field
from .field import Quality
from .fast_field_local import build_local


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--ct',type=Path,required=True)
    parser.add_argument('--segmentation',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source',choices=['accepted_binary','network_probability'],default='accepted_binary')
    parser.add_argument('--quality',choices=['high','ultra'],default='high')
    parser.add_argument('--backend',choices=['PS','PL'],default='PS')
    args=parser.parse_args()
    sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(4)
    args.ct=args.ct.resolve();args.segmentation=args.segmentation.resolve();args.output=args.output.resolve()
    if args.output.exists():raise ValueError('Require a new field output directory')
    image,identity=load_case(args.ct,args.segmentation,args.source)
    quality=Quality() if args.quality=='high' else replace(Quality(),
        surface_smoothing_sigma_mm=.5,surface_smoothing_strength=.72,
        axial_smoothing_sigma_mm=1,quantization_mm=1/64)
    root=Path(__file__).resolve().parents[2]
    begin=time.perf_counter();session=None;distance=None
    # The accepted same-input measurements select ITK for binary and the
    # stronger four-core Q20 ROI implementation for probability preparation.
    if args.backend=='PS' and args.source=='network_probability':
        sys.path.insert(0,str(root/'dfx/edt_cache'))
        from ps_runtime import PSReference
        reference=PSReference()
        def distance(mask,spacing):
            values,seconds=reference.distance(mask,spacing,4)
            return values,dict(backend='PS_Q20_4_thread',total_seconds=seconds)
    elif args.backend=='PL':
        sys.path.insert(0,str(root/'dfx/edt_volume'))
        from volume_runtime import VolumeSession
        session=VolumeSession(experimental=False);session.__enter__()
        def distance(mask,spacing):
            values,_,stats=session.distance(mask,spacing)
            return values,stats
    try:
        field=build_local(image,quality,distance)
        field.report['requested_backend']=args.backend
        field.report['producer_wall_before_save_seconds']=time.perf_counter()-begin
        field.report['producer_wall_scope']='includes backend initialization and field computation; excludes input read, output compression and UI'
        report=save_field(args.output,field,identity)
    finally:
        if session is not None:
            try:session.return_to_scope()
            finally:session.close()
    print(json.dumps(report,indent=2,allow_nan=False))


if __name__=='__main__':main()
