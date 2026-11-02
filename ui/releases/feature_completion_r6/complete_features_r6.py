"""Integrated UI entry point; no runtime imports from prototype candidate folders."""
from pathlib import Path
import argparse,hashlib,os,sys,uuid

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'ui'));sys.path.insert(0,str(ROOT))
import complete_import_r6 as accepted


def main():
    action=sys.argv[1] if len(sys.argv)>1 else None
    if action not in ('dicom-series','import-dicom','export'):
        return accepted.main()
    if hasattr(os,'nice'):os.nice(10)
    os.environ.setdefault('ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS','2')
    p=argparse.ArgumentParser();p.add_argument('action',choices=['dicom-series','import-dicom','export'])
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--series-uid');p.add_argument('--case-root',type=Path,default=ROOT)
    p.add_argument('--result',type=Path);p.add_argument('--destination',type=Path)
    p.add_argument('--minimum-candidate-volume',type=float,default=14.)
    a=p.parse_args()
    if action=='dicom-series':
        from modules.dicom_import.discovery import discover
        accepted.backend.emit('dicom_series',directory=str(a.input.resolve()),
                              series=[r.summary() for r in discover(a.input)])
    elif action=='import-dicom':
        from modules.dicom_import.discovery import discover,select
        from system.contracts import create_case
        series=select(discover(a.input),a.series_uid)
        token=hashlib.sha256((str(a.input.resolve())+'|'+str(a.series_uid)).encode()).hexdigest()[:16]
        folder=create_case(a.case_root,'dicom_'+token+'_'+uuid.uuid4().hex[:6],series.directory,series.series_uid)
        accepted.backend.emit('imported',input=str(folder/'input/ct.nrrd'),
            selection_id=series.selection_id,selected_directory=str(series.directory),
            relative_directory=series.relative_directory,series_uid=series.series_uid,file_count=len(series.files))
    else:
        if a.result is None or a.destination is None:
            raise ValueError('Export requires the completed result and destination')
        from modules.lesion_catalogue.bundle import export_bundle
        import SimpleITK as sitk
        from modules.surface_export.export import sha
        report=export_bundle(a.result,a.destination,sha(a.input),a.minimum_candidate_volume,sitk.ReadImage(str(a.input)))
        accepted.backend.emit('exported',path=str(a.destination.resolve()),files=len(report['files']),
            colored_surface_report=str(a.destination.resolve()/'surfaces/report.json'),
            schema=report['schema'],surface_export_seconds=report['surface_export_seconds'],
            lesion_catalogue_state=report['lesion_catalogue_state'],minimum_candidate_volume_mm3=report['minimum_candidate_volume_mm3'])


if __name__=='__main__':
    try:main()
    except Exception as error:
        accepted.backend.emit('error',text=str(error));sys.exit(1)
