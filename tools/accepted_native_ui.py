"""Read the current accepted UI without rewriting historical release proofs."""
from pathlib import Path
import hashlib
import json

sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()


def accepted(root):
    root=Path(root).resolve()
    base_path=root/'ui/build/composite_modes_release.json'
    base=json.loads(base_path.read_text(encoding='utf-8'))
    path=root/'ui/build/linked_overview_release_r1.json'
    if not path.exists():
        for name,digest in base['source_sha256'].items():assert sha(root/name)==digest,name
        assert sha(root/'ui/build/medical_ui')==base['binary_sha256']
        return base
    current=json.loads(path.read_text(encoding='utf-8'))
    assert current['status']=='promoted_after_actual_HDMI_linked_camera_validation'
    assert current['base_release_sha256']==sha(base_path)
    archive=(root/current['rollback']).resolve();assert archive.is_relative_to(root/'ui/archive')
    assert sha(archive/'inventory.json')==current['rollback_inventory_sha256']
    for name,digest in json.loads((archive/'inventory.json').read_text(encoding='utf-8'))['inventory'].items():assert sha(archive/name)==digest,name
    assert sha(archive/'ui/build/medical_ui')==base['binary_sha256']
    for name,digest in base['source_sha256'].items():assert sha(archive/name)==digest,name
    for name,digest in current['source_sha256'].items():assert sha(root/name)==digest,name
    assert sha(root/'ui/build/medical_ui')==current['binary_sha256']
    receipt_path=root/current['acceptance'];assert sha(receipt_path)==current['acceptance_sha256']
    receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
    assert receipt['status'].startswith('passed_actual_HDMI_presented_PL_camera_')
    assert receipt['candidate_binary_sha256']==current['binary_sha256']
    for name,digest in receipt['evidence_sha256'].items():assert sha(root/name)==digest,name
    for name,digest in receipt['source_sha256'].items():assert sha(root/name)==digest,name
    for name,digest in current['PL_release_sha256'].items():assert sha(root/name)==digest,name
    return current


def historical_source(root,name,digest):
    """Resolve only the explicitly preserved old UI source after this fix."""
    root=Path(root);p=root/name
    if p.exists() and sha(p)==digest:return p
    current=accepted(root)
    p=root/current['rollback']/name
    assert name.startswith('ui/src/') and p.is_file() and sha(p)==digest,name
    return p
