"""Original complete reconstruction with qualified D7 MC and D9 AXIS smoothing."""
from pathlib import Path
import argparse,hashlib,json,sys,time
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'modules/reconstruction')]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ct',type=Path,required=True)
    parser.add_argument('--mask-dir',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--retain-full-banks',action='store_true');args=parser.parse_args()
    args.ct=args.ct.resolve(strict=True);args.mask_dir=args.mask_dir.resolve(strict=True);args.output=args.output.resolve()
    if not all(p.is_relative_to(ROOT) for p in (args.ct,args.mask_dir,args.output)):raise ValueError('Owned medical inputs and outputs required')
    if args.output.exists():raise FileExistsError('Fresh reconstruction output required')
    from modules.reconstruction.smooth_pipeline_r2.axis_tile1024_r1.host_D9_r1.hardware_r1.seal_release import verify
    from modules.reconstruction.axis_mc_8_r2.integration_guard import require_board_grade
    require_board_grade();verify(installed=True)
    import SimpleITK as sitk
    from modules.image_import.partial_r1.contracts import validate_selected_masks
    from modules.reconstruction.axis_mc_8_r2.integrated_pooled_r3.reconstruction import reconstruct
    from modules.reconstruction.streaming_functional_r1.session import Session
    declared,inputs=validate_selected_masks(args.ct,args.mask_dir.parent)
    selected=declared['declared_structures']
    started=time.perf_counter()
    with Session(args.output,retain_full_banks=args.retain_full_banks) as session:
        report=reconstruct(args.mask_dir,args.output,session,selected,inputs)
    context=session.report(args.output/'session.json')
    report.update(available_structures=selected,unavailable_structures=declared['unavailable_structures'],smoothing_kernel='D9_AXIS',smoothing_transport='AXIS512',functional_candidate_only=True,
        original_MC_topology_geometry_checks_normals_and_masks_retained=True,
        session_open_seconds=session.open_seconds,entry_seconds=time.perf_counter()-started,
        partial_switches=context['partial_switches'],xrt_metadata_loads=context['xrt_metadata_loads'],
        PL_context_reused_for_MC_and_smoothing=False,separate_stage_owners_drained_and_closed=True,
        known_D9_PS4_speed_regression_preserved=True,performance_qualification_pending=True,
        retained_full_D9_work_banks=bool(args.retain_full_banks))
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
