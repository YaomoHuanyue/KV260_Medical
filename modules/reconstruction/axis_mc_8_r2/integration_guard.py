"""Require actual MC8 board/PS4 qualification before full or partial entries."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def require_board_grade():
    path = HERE / 'board_qualification.json'
    proof = json.loads(path.read_text())
    assert proof['actual_board_correctness_passed'] and proof['actual_runtime_DMA_executed']
    assert proof['actual_100MHz_all5_full_PR_passed'] and proof['speed_gate_passed']
    assert proof['scan_loop_II'] == 1 and proof['scan_voxels_per_iteration'] == 8
    assert proof['completed_static_DMA_frames'] == 828 and len(proof['full_own_masks']) == 3
    for name, digest in proof['evidence_SHA256'].items():
        relative = Path(name)
        target = (ROOT / relative).resolve()
        assert not relative.is_absolute() and '..' not in relative.parts and target.is_relative_to(ROOT)
        assert sha(target) == digest, name
    base = json.loads((HERE / 'dfx_r1/release_r1/manifest.json').read_text())
    assert base['partial_SHA256'] == proof['partial_SHA256']
    return proof
