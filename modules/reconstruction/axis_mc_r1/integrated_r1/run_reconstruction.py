"""Actual D7 AXIS MC and FMA2 smoothing, through one owned DFX context."""
from pathlib import Path
import argparse,json,sys,time
SYSTEM=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(SYSTEM))
from modules.reconstruction.axis_mc_r1.host_integrated_r2.runtime import Session
from modules.reconstruction.axis_mc_r1.integrated_r1.reconstruction import reconstruct


def main():
    p=argparse.ArgumentParser();p.add_argument('--ct',type=Path,required=True)
    p.add_argument('--mask-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.ct=a.ct.resolve(strict=True);a.mask_dir=a.mask_dir.resolve(strict=True);a.output=a.output.resolve()
    if not a.ct.is_relative_to(SYSTEM) or not a.mask_dir.is_relative_to(SYSTEM) or not a.output.is_relative_to(SYSTEM):
        raise ValueError('Owned medical inputs/output required')
    if a.output.exists():raise FileExistsError('Choose a new reconstruction directory')
    started=time.perf_counter()
    import SimpleITK as sitk
    from system.contracts import validate_masks,geometry
    inputs=validate_masks(a.mask_dir,geometry(sitk.ReadImage(str(a.ct))))
    selected=['lung','airway','nodule']
    with Session() as s:
        report=reconstruct(a.mask_dir,a.output,s,selected,inputs)
        context=s.report(a.output/'session.json')
        report.update(session_open_seconds=s.open_seconds,entry_seconds=time.perf_counter()-started,
            partial_switches=context['partial_switches'],xrt_metadata_loads=context['xrt_metadata_loads'],
            PL_context_reused_for_MC_and_smoothing=True)
    report['entry_seconds']=time.perf_counter()-started
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
