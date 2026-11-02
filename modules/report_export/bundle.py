"""Extend the accepted colored bundle with complete bound analysis reports."""
from pathlib import Path
import json,uuid
from modules.lesion_catalogue.bundle import export_bundle as previous_export
from .reports import validate,write_reports,sha


def export_bundle(source,destination,input_sha,minimum_volume_mm3=14.,expected_geometry=None):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError(destination)
    if source==destination or source in destination.parents or destination in source.parents:
        raise ValueError('Export must be separate from its source result')
    snapshot=validate(source,input_sha)
    staging=destination.parent/(destination.name+'.reports_pending_'+uuid.uuid4().hex)
    previous=previous_export(source,staging,input_sha,minimum_volume_mm3,expected_geometry)
    complete=write_reports(snapshot,staging/'reports')
    (staging/'report.json').rename(staging/'catalogue_bundle_report.json')
    report=dict(previous,schema='kv260.export.v5',complete_reports='reports/index.json',
        complete_reports_sha256=sha(staging/'reports/index.json'),
        complete_report_seconds=complete['elapsed_seconds'],
        catalogue_bundle_report_sha256=sha(staging/'catalogue_bundle_report.json'),
        source_sha256={**previous['source_sha256'],Path(__file__).relative_to(Path(__file__).resolve().parents[2]).as_posix():sha(Path(__file__))},
        files={p.relative_to(staging).as_posix():sha(p) for p in staging.rglob('*') if p.is_file()})
    (staging/'report.json').write_text(json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf-8')
    staging.rename(destination)
    return report
