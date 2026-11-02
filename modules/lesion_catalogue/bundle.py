"""Extend the complete colored-surface bundle with an explicit size catalogue."""
from pathlib import Path
import json
import uuid
from modules.surface_export.bundle import export_bundle as export_surfaces
from .export import export_catalogue,sha,ROOT


def export_bundle(source,destination,input_sha,minimum_volume_mm3=14.0,expected_geometry=None):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError(destination)
    if source==destination or source in destination.parents or destination in source.parents:
        raise ValueError('Export must be separate from source')
    # Validate the setting even when the nodule structure was not provided.
    import math
    if not math.isfinite(float(minimum_volume_mm3)) or minimum_volume_mm3<0:
        raise ValueError('Minimum volume must be finite and nonnegative')
    staging=destination.parent/(destination.name+'.catalogue_pending_'+uuid.uuid4().hex)
    previous=export_surfaces(source,staging,input_sha)
    mask=source/'segmentation/nodule_mask.nii.gz'
    if mask.is_file():
        catalogue=export_catalogue(mask,staging/'lesions',minimum_volume_mm3,expected_geometry)
        state=catalogue['state']
    else:
        state='nodule_not_provided'
    (staging/'report.json').rename(staging/'surface_bundle_report.json')
    result={**previous,'schema':'kv260.export.v4','status':'completed',
        'lesion_catalogue_state':state,'minimum_candidate_volume_mm3':float(minimum_volume_mm3),
        'surface_bundle_report_sha256':sha(staging/'surface_bundle_report.json'),
        'candidate_catalogue_report':'lesions/catalogue_report.json' if mask.is_file() else None,
        'source_sha256':{**previous['source_sha256'],Path(__file__).relative_to(ROOT).as_posix():sha(Path(__file__))},
        'files':{p.relative_to(staging).as_posix():sha(p) for p in staging.rglob('*') if p.is_file()}}
    (staging/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    staging.rename(destination)
    return result
