"""One report-export action; all other accepted UI actions delegate unchanged."""
from pathlib import Path
import argparse,os,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ui/releases/feature_completion_r6'));sys.path.insert(0,str(ROOT))
import backend_selected_r1 as accepted
import backend_core_r6 as backend


def main():
    if len(sys.argv)<2 or sys.argv[1]!='export':return accepted.main()
    p=argparse.ArgumentParser();p.add_argument('action');p.add_argument('--input',type=Path,required=True)
    p.add_argument('--result',type=Path,required=True);p.add_argument('--destination',type=Path,required=True)
    p.add_argument('--minimum-candidate-volume',type=float,default=14.)
    a=p.parse_args();os.environ.setdefault('ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS','2')
    if hasattr(os,'nice'):os.nice(10)
    from modules.image_import.partial_r1.contracts import validate_source
    if validate_source(a.input,a.result) is None:
        import complete_import_r6
        complete_import_r6.validate_external_source(a.input,a.result)
    import SimpleITK as sitk
    from modules.report_export.bundle import export_bundle
    from modules.report_export.reports import sha
    report=export_bundle(a.result,a.destination,sha(a.input),a.minimum_candidate_volume,sitk.ReadImage(str(a.input)))
    backend.emit('exported',path=str(a.destination.resolve()),files=len(report['files']),schema=report['schema'],
        colored_surface_report=str(a.destination.resolve()/'surfaces/report.json'),
        surface_export_seconds=report['surface_export_seconds'],
        lesion_catalogue_state=report['lesion_catalogue_state'],minimum_candidate_volume_mm3=report['minimum_candidate_volume_mm3'],
        complete_reports=report['complete_reports'],complete_report_seconds=report['complete_report_seconds'])
if __name__=='__main__':
    try:main()
    except Exception as e:backend.emit('error',text=str(e));sys.exit(1)
