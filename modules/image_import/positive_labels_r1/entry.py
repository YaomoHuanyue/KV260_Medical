"""Explicit positive-label import UI action; refuse until complete policy ARM qualification."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
def sha(p):
    with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    if len(sys.argv)<2 or sys.argv[1]!='import-external':raise ValueError('This adapter serves only external image import')
    here=Path(__file__).resolve().parent
    core=json.loads((here/'qualification.json').read_bytes())
    if not core['backend_verified']or not core['actual_Windows_and_ARM']:raise ValueError('Positive-label backend qualification required')
    policy_proof=json.loads((here/'policy_qualification.json').read_bytes())
    if not policy_proof.get('actual_ARM_policy_and_contracts_passed'):raise ValueError('Complete positive-label/probability UI policy is not yet qualified')
    for name,digest in policy_proof['source_SHA256'].items():
        p=(ROOT/name).resolve(strict=True)
        if not p.is_relative_to(ROOT)or sha(p)!=digest:raise ValueError('Changed qualified import source: '+name)
    from modules.image_import.airway_probability_cleanup_r1 import importer as prior
    from modules.image_import.partial_r1 import importer as original
    old=original.read(ROOT/'results/probability_cleanup_20261019_r1/ARM/verified.json')
    assert old['status']=='probability_airway_policy_original_contracts_and_own_CT_exact'
    assert old['own_CT_effective_mask_all_voxels_equal_existing_full_inference_mask']and old['own_CT_original_probability_all_bits_preserved']
    for name,digest in old['source_and_evidence_SHA256'].items():assert original.sha(ROOT/name)==digest,name
    from modules.image_import.positive_labels_r1 import policy
    # Only this fresh short-lived utility process receives the new import function.
    original.import_bundle=policy.import_bundle
    from modules.report_export.backend import main as accepted
    return accepted()
if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps(dict(event='error',text=str(error)),ensure_ascii=False),flush=True);raise SystemExit(1)
