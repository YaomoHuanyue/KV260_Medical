"""Copy the selected native recovery review into a standalone current export."""
from pathlib import Path
import copy,json,shutil
from modules.airway_detail.active_scene_r20 import validate_review
from modules.surface_route.bundle_r8 import write_json
from modules.surface_route.verification_session_r15 import sha

def append_export(scene,payload):
    binding=scene.get('distal_recovery_binding')
    if binding is None:return None
    report=validate_review(scene,binding);payload=Path(payload)
    source=Path(binding['report']).parent;exported={}
    # These exact optional files were just created by the inherited exporter
    # in a private, unpublished staging directory. Replace its old review.
    for name in ['airway_detail_report.json',*['airway_detail_'+n for n in report['files']]]:
        p=payload/name
        if p.exists():assert p.is_file() and p.parent==payload;p.unlink()
    for name,h in report['files'].items():
        target=payload/('airway_detail_'+name);shutil.copyfile(source/name,target)
        assert sha(target)==h;exported[target.name]=h
    copied=copy.deepcopy(report);copied.update(files=exported,source_report_sha256=binding['report_sha256'])
    write_json(payload/'airway_detail_report.json',copied)
    scope=dict(schema='kv260.export.active_recovery_review.v1',target_index=binding['target_index'],
        report='airway_detail_report.json',report_sha256=sha(payload/'airway_detail_report.json'),
        scope=binding['scope'],model_navigation_replaced=False,display_at_generation=binding['display_at_generation'],
        exported_display={k:scene['complete_surface'][k] for k in ('revision','route_id','scalar_sha256')})
    write_json(payload/'active_recovery_binding.json',scope);return scope
