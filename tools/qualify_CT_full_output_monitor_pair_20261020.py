"""Pair corrected PC/ARM observer fixtures and real full-output data; bind a candidate CLI only."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PAIR=ROOT/'modules/segmentation/full_outputs_PL_pair_monitor_r2'
EVIDENCE=ROOT/'results/CT_full_outputs_PL_pair_monitor_20261020_r2'
CORE=ROOT/'modules/ct_preprocess/axis_hu_32_r2/bounded_volume_r3'
UI=ROOT/'ui/releases/ct_bounded_outputs_r1'


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def read(p):return json.loads(p.read_text())


def main():
    target=CORE/'entry_inputs_r1.json';result=EVIDENCE/'paired_monitor_and_entry_qualified_r1.json'
    assert not target.exists() and not result.exists()
    proof=read(EVIDENCE/'verified_PC.json')
    for n,h in proof['source_and_evidence_SHA256'].items():assert sha(ROOT/n)==h,n
    assert proof['full_own_CT_slices']==139 and proof['total_actual_PL_convolution_calls']==5040
    assert set(proof['sampled_board_memory']['observations'])=={'baseline','candidate'}
    assert all(v['samples']>100 for v in proof['sampled_board_memory']['observations'].values())
    with zipfile.ZipFile(EVIDENCE/'current_candidate.zip') as z:
        aliases=json.loads(z.read('collection/canonical_aliases.json'))['logical_aliases']
        def data(n):
            if n in aliases:n=aliases[n]['member']
            return json.loads(z.read(n))
        windows=read(PAIR/'monitor_fixture_verified.json');arm=data('monitor_fixture_verified.json')
        assert windows==arm and len(arm['cases'])==7 and arm['original_baseline_disappearance_bug_reproduced']
        assert windows['source_SHA256']==sha(PAIR/'test_monitor.py')
        new_manifest=data('collection/original_outputs_manifest.json')
        request=data('request.json');reports={mode:data(mode+'/report.json') for mode in ('baseline','candidate')}
    old=ROOT/'results/CT_full_outputs_PL_pair_20261020_r1'
    with zipfile.ZipFile(old/'current_candidate.zip') as z:
        old_manifest=json.loads(z.read('collection/original_outputs_manifest.json'))
        old_request=json.loads(z.read('request.json'))
    assert request['input']==old_request['input'] and request['model_source_SHA256']==old_request['model_source_SHA256']
    assert request['shared_files_SHA256']==old_request['shared_files_SHA256']
    exact=[]
    for mode in ('baseline','candidate'):
        for n in ('lung_mask.nii.gz','airway_mask.nii.gz','nodule_mask.nii.gz','airway_mask_network.nii.gz',
                  'airway_mask_detail.nii.gz','airway_logits.npy','airway_logits.json','ct_overlay.png'):
            key=mode+'/'+n;assert new_manifest[key]==old_manifest[key];exact.append(key)
    a,b=reports['baseline'],reports['candidate']
    worker_delta=b['worker_total_seconds']-a['worker_total_seconds']
    logit_delta=b['worker_stages']['airway_logits_save_seconds']-a['worker_stages']['airway_logits_save_seconds']
    timing=dict(worker_seconds={m:r['worker_total_seconds'] for m,r in reports.items()},
        logits_finish_seconds={m:r['worker_stages']['airway_logits_save_seconds'] for m,r in reports.items()},
        worker_difference_seconds=worker_delta,logit_finish_difference_seconds=logit_delta,
        finish_phase_accounts_for_fraction_of_observed_difference=logit_delta/worker_delta,
        measured_phase_contains_original_memmap_flush_rename_and_file_SHA_not_PL_MAC=True,
        disk_device_root_cause_or_statistical_speedup_not_claimed=True)
    paths=[Path(__file__),CORE/'entry_r1.py',CORE/'entry_derivation_r1.json',CORE/'runtime.py',
        ROOT/'modules/ct_preprocess/axis_hu_32_r2/bounded_volume_r2/runtime.py',
        EVIDENCE/'verified_PC.json',EVIDENCE/'current_candidate.zip',PAIR/'source_derivation.json',PAIR/'monitor_fixture_verified.json']
    paths.extend(UI/n for n in ('backend.py','dispatch.py','main.cpp','derivation.json'))
    for folder in ('ARM_evidence_r3','ARM_int32_evidence_r1'):
        p=CORE/folder/'verified_PC_ARM.json';v=read(p)
        assert v['all16_case_flags_retention_and_output_checks_paired'] and v['all_source_SHA256_exactly_paired_PC_ARM']
        paths.append(p)
    for n,h in request['shared_files_SHA256'].items():assert sha(ROOT/n)==h;paths.append(ROOT/n)
    inputs=dict(status='complete_real139slice_outputs_and_both_memory_samples_qualified_candidate_CLI_not_formal_UI',
        actual_full_output_PL_pair=(EVIDENCE/'verified_PC.json').relative_to(ROOT).as_posix(),
        source_and_evidence_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in paths},
        same_original_PL_HU32_C5_math_model_outputs_and_original_CLI_defaults=True,
        actual_UI_full_pipeline_gate_and_formal_release_still_required=True,production_promoted=False,whole_goal_completed=False)
    target.write_text(json.dumps(inputs,indent=2)+'\n')
    result.write_text(json.dumps(dict(status='PC_ARM_all7_observer_controls_paired_and_actual_complete_full_output_PL_pair_strictly_qualified_candidate_CLI_only',
        original_failed_monitor_and_incomplete_initial_PC_path_fixture_preserved=True,
        current_PC_ARM_monitor_source_and_cases_and_results_equal=True,all7_lifecycle_controls=arm['cases'],
        previous_and_current_runs_same_full_data_payload_SHA256=exact,process_peak_RSS_bytes=proof['process_peak_RSS_bytes'],
        measured_timing_scope=timing,entry_inputs=target.relative_to(ROOT).as_posix(),entry_inputs_SHA256=sha(target),
        original_all_139_slices_all_outputs_and_full_strict_gate_not_relaxed=True,
        actual_UI_compile_full_pipeline_and_formal_release_not_done=True,PL_accessed=False,production_promoted=False,whole_goal_completed=False),indent=2)+'\n')
    print('PASS corrected PC/ARM7 fixtures; original full real-PL gate qualified; all data matches previous pair; slower measured file finish retained; candidate CLI only')


if __name__=='__main__':main()
