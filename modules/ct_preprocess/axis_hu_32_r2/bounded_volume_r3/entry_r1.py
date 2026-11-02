"""Bound memory in the original CT CLI; require complete real-PL evidence, never fall back."""
from pathlib import Path
import ast
import hashlib
import json
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT))


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def verify_qualification():
    # No parent import, output-directory creation or XRT access before all
    # original full-output and memory-sampling gates are actually satisfied.
    inputs=json.loads((HERE/'entry_inputs_r1.json').read_text())
    for name,digest in inputs['source_and_evidence_SHA256'].items():
        p=(ROOT/name).resolve();assert p.is_relative_to(ROOT) and sha(p)==digest,name
    proof=json.loads((ROOT/inputs['actual_full_output_PL_pair']).read_text())
    assert proof['full_own_CT_slices']==139 and proof['total_actual_PL_convolution_calls']==5040
    assert proof['actual_released_HU32_and_C5_kernels_all_outputs_same_input_model_precision_settings_verified']
    assert proof['full139x512x512_int8_logit_threshold_recomputed_against_raw_mask']
    assert proof['logits_metadata_preview_PNG_and_non_timing_audit_fields_exact']
    assert set(proof['sampled_board_memory']['observations'])=={'baseline','candidate'}
    assert all(proof['sampled_board_memory']['observations'][mode]['samples']>0 for mode in ('baseline','candidate'))
    assert proof['exact_current_case_GUI_restore_and_reversible_PC_identity_sync_checked']
    assert not proof.get('missing_system_CMA_sampling_modes')
    return inputs


def main():
    verify_qualification()
    derivation=json.loads((HERE/'entry_derivation_r1.json').read_text())
    path=ROOT/derivation['parent'];assert sha(path)==derivation['parent_SHA256']
    text=path.read_text();node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='main')
    body=ast.get_source_segment(text,node)
    for edit in derivation['literal_edits']:
        assert body.count(edit['before'])==1;body=body.replace(edit['before'],edit['after'])
    assert hashlib.sha256(body.encode()).hexdigest()==derivation['main_body_SHA256']
    from modules.ct_preprocess.axis_hu_32_r2.integrated_r1 import run_segmentation as parent
    namespace=dict(vars(parent))
    exec(compile(body,str(HERE/'entry_r1.py')+':qualified_original_CLI','exec'),namespace)
    return namespace['main']()


if __name__=='__main__':main()
