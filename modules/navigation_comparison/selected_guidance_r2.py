"""Guidance for original smoothed paths after verified C4 audit."""
from pathlib import Path
import hashlib,json
from selected_guidance_r1 import attach as checked_mapping
from selected_guidance_rules_r2 import branch_guidance
from protocol import validate_stored_audit

def attach(context,selection,report,route):
    here=Path(__file__).parent
    origin=json.loads((here/'selected_guidance_origin_r2.json').read_text(encoding='utf-8'))
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for name,sha in origin['new_source_sha256'].items():
        if digest(here/name)!=sha:raise ValueError('Selected guidance source changed')
    report,mapped=checked_mapping(context,selection,report,route)
    report['branch_guidance']=branch_guidance(context,mapped)
    report['smoothed_original_branch_matching']='exact raw parent IDs; monotonic lumen-bounded projection'
    report['selected_guidance_source_sha256']=origin['new_source_sha256']
    validate_stored_audit(mapped,report)
    return report,mapped
