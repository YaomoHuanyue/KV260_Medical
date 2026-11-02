"""Add colored surfaces to the accepted masks, STL, route and report bundle."""
from pathlib import Path
import json,sys,uuid
from .export import export_surfaces,sha,ROOT

sys.path.insert(0,str(ROOT/'ui'))
from features.export import export_result

def export_bundle(source,destination,input_sha):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError(destination)
    if source==destination or source in destination.parents or destination in source.parents:
        raise ValueError('Export must be separate from the source result')
    destination.parent.mkdir(parents=True,exist_ok=True)
    staging=destination.parent/(destination.name+'.bundle_pending_'+uuid.uuid4().hex)
    old=export_result(source,staging,input_sha)
    surfaces=export_surfaces(source,staging/'surfaces',input_sha)
    old_report=staging/'report.json';legacy=staging/'legacy_report.json'
    assert old_report.resolve().parent==staging.resolve() and legacy.resolve().parent==staging.resolve()
    old_report.rename(legacy)
    report={**old,'schema':'kv260.export.v3','status':'completed',
        'legacy_report_sha256':sha(legacy),
        'colored_surface_report':'surfaces/report.json',
        'colored_surface_report_sha256':sha(staging/'surfaces/report.json'),
        'surface_export_seconds':surfaces['elapsed_seconds'],
        'source_sha256':{str(Path(__file__).relative_to(ROOT)):sha(Path(__file__)),
                         'ui/features/export.py':sha(ROOT/'ui/features/export.py')},
        'files':{p.relative_to(staging).as_posix():sha(p) for p in staging.rglob('*') if p.is_file()}}
    (staging/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,
        allow_nan=False)+'\n',encoding='utf-8')
    staging.rename(destination)
    return report
