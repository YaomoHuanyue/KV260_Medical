"""Verify accepted route adapters separately from the frozen native UI proof."""
from pathlib import Path
import hashlib,json
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def historical_source(root,name,digest):
 root=Path(root);p=root/name
 if p.exists() and sha(p)==digest:return p
 assert name in ('ui/features/analysis.py','ui/features/navigation_task.py')
 p=root/'ui/archive/20261004_route_metrics_r2'/name
 assert p.exists() and sha(p)==digest,name
 return p
def verify(root):
 root=Path(root).resolve();path=root/'ui/build/route_metrics_release_r1.json'
 if not path.exists():return None
 r=json.loads(path.read_text());assert r['status']=='accepted_after_candidate_and_canonical_complete_native_PL_audit_trials'
 archive=(root/r['rollback']).resolve();assert archive.is_relative_to(root/'ui/archive')
 assert sha(archive/'inventory.json')==r['rollback_inventory_sha256']
 for name,digest in json.loads((archive/'inventory.json').read_text())['inventory'].items():assert sha(archive/name)==digest,name
 for name,digest in r['source_sha256'].items():assert sha(root/name)==digest,name
 assert sha(root/'ui/build/medical_ui')==r['UI_binary_sha256']
 for name,digest in r['receipts_sha256'].items():assert sha(root/name)==digest,name
 candidate=json.loads((root/'ui/candidates/route_metrics_r2/docs/native_acceptance_r2.json').read_text())
 for name,digest in candidate['source_sha256'].items():assert sha(historical_source(root,name,digest))==digest,name
 for name,digest in candidate['evidence_sha256'].items():assert sha(root/name)==digest,name
 acceptance=json.loads((root/'ui/docs/route_canonical_r1/acceptance.json').read_text())
 assert acceptance['protocol3_PS_recalculation_forbidden_and_passed'] and acceptance['original_precision_and_route_camera_preserved']
 for collection in ('source_sha256','evidence_sha256'):
  for name,digest in acceptance[collection].items():assert sha(root/name)==digest,name
 trial=json.loads((root/'ui/docs/route_canonical_r1/trial.json').read_text())
 assert trial['trial_terminal'] and trial['trial_passed'] and trial['trial_exit_code']==0 and not trial['rollback_performed']
 assert trial['script_sha256']==sha(root/'tools/run_route_metrics_canonical_trial_r1.sh')
 assert trial['restored_UI_binary_sha256']==r['UI_binary_sha256']
 board=json.loads((root/'dfx/route_audit_speed/docs/board_acceptance_r14.json').read_text())
 assert board['PL_audit_is_faster_than_optimized_PS']
 for name,digest in board['evidence_sha256'].items():assert sha(root/'dfx/route_audit_speed'/name)==digest,name
 for name,digest in board['source_sha256'].items():assert sha(root/name)==digest,name
 return r
