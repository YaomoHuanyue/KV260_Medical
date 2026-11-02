"""Gate D9 physical work on its own exact native, actual RTL, and synthesis evidence."""
from pathlib import Path
import importlib.util
import json
import sys
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CORE = ROOT / 'modules/reconstruction/smooth_pipeline_r2/axis_tile1024_r1'
sys.path.insert(0, str(HERE))
from check_reports import REFERENCES, require, sha

STATIC_SHA256 = '285f3d4a50af45cbea7f503f1f32789b0d84b55214163750a301267e2e72fcb9'
DCP_SHA256 = '745a365df14b98c252a2107c1b292e10e71e8f54c6f02794ee04e19a5a32fe42'


def checked(path, status, flags, bindings):
    value = json.loads(path.read_text())
    require(value['status'] == status, 'Wrong proof: ' + str(path))
    require(not value.get('production_promoted', False), 'Unexpected candidate promotion')
    for flag in flags:
        require(value.get(flag) is True, 'Unproven gate: ' + flag)
    bindings[path.relative_to(ROOT).as_posix()] = sha(path)
    for key in ('source_and_evidence_SHA256', 'source_and_evidence_sha256', 'source_SHA256', 'source_sha256'):
        for name, expected in value.get(key, {}).items():
            source = (ROOT / name).resolve()
            require(source.is_relative_to(ROOT) and source.is_file() and sha(source) == expected,
                    'Changed/missing physical proof source: ' + name)
            bindings[name] = expected
    return value


def inspect():
    bindings = {}
    spec = importlib.util.spec_from_file_location('D9_exact_native_qualification', CORE / 'qualification.py')
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    bindings.update(native.bindings())
    checked(CORE / 'typed_Csim_r1/verified_Windows.json',
        'full_AXIS_smoothing_actual_vendor_Csim_original144_CT18_exact',
        ('actual_vendor_ap_uint_burst_maxi_ap_axiu_and_hls_stream_enabled',
         'candidate_SMOOTH_NATIVE_not_defined', 'original_all5_banks_16_reports_guards_and_FMA_oracle_preserved',
         'graph_service_REQUEST_FINAL_sequence_address_totals_and_bounded_queue_checked'), bindings)
    csim = checked(CORE / 'results/official_Csim_verified_Windows.json',
        'tile1024_official_Csim_original7_full_banks_and_AXIS_protocol_independently_verified',
        ('full7_original_numeric_fixtures_passed', 'all5_banks16_reports_tails_and_frozen_oracle_retained',
         'REQUEST_FINAL_sequence_address_and_all_declared_beats_checked',
         'all_owned_member_bytes_stream_verified_and_exact_root_absent'), bindings)
    csim_archive = ROOT / 'results/smooth_AXIS_tile1024_official_Csim_r1/axis_csim/current_candidate.zip'
    require(sha(csim_archive) == csim['archive_SHA256'], 'Official Csim archive changed')
    bindings[csim_archive.relative_to(ROOT).as_posix()] = sha(csim_archive)
    arm = checked(CORE / 'arm_native_r1/PC_verified.json',
        'D9_actual_ARM_native144_CT18_and_PC_pair_verified_no_PL_access',
        ('original144_complete_bank_cases_exact', 'original_CT18_full5_banks16_reports_guards_exact',
         'Windows_ARM_same_original_case_results_paired', 'actual_AArch64_ELF_verified'), bindings)
    require(not arm['actual_D9_PL_accessed'], 'ARM CPU verification is not a board PL trial')
    require(sha(CORE / 'arm_native_r1/inputs.json') == arm['source_plan_SHA256'], 'ARM input plan changed')
    for name, expected in arm['files_SHA256'].items():
        path = CORE / 'arm_native_r1' / name
        require(sha(path) == expected, 'ARM native evidence changed: ' + name)
        bindings[path.relative_to(ROOT).as_posix()] = expected
    area = checked(CORE / 'dfx_candidate_r2/verified_area_Windows.json',
        'actual_D9_tile1024_full_DFX_RM_synthesis_area_and_exact_boundary_verified_not_routed',
        ('area_in_budget', 'original218_HLS_RTL_Tcl_and_all_official_IP_bytes_preserved',
         'lossless_logical_member_dedup_verified', 'all_owned_bytes_verified_and_exact_source_task_root_absent'), bindings)
    require(area['identity'] == 217 and area['ABI'] == 12 and area['actual_external_frozen_pins'] == 67
            and area['actual_control_fields'] == 17 and area['actual_algorithm_AXIS_bits'] == 512, 'Wrong D9 boundary')
    require(area['DCP_SHA256'] == DCP_SHA256, 'Wrong D9 synthesized checkpoint')
    archive = ROOT / area['source_archive']
    require(sha(archive) == area['source_archive_SHA256'], 'Synthesized candidate archive changed')
    with zipfile.ZipFile(archive) as source:
        manifest = json.loads(source.read('outputs_manifest.json'))
        require(manifest[area['DCP_member']] == DCP_SHA256, 'Wrong retained synthesized DCP')
        with source.open(area['DCP_member']) as stream:
            import hashlib
            require(hashlib.file_digest(stream, 'sha256').hexdigest() == DCP_SHA256, 'DCP byte mismatch')
    bindings[archive.relative_to(ROOT).as_posix()] = area['source_archive_SHA256']
    pending = []
    gates = [
        ('results/smooth_AXIS_D9_monitored_full_RTL_r2/axis_rtl',
         'independent_PC_actual_original14_D9_official_monitored_RTL6422850_words_and_both_C_posts_verified',
         ('all_original14_cases_and6422850_full_words_exact', 'all5_work_banks16_reports_and_full_unused_tails_preserved',
          'actual4_AXI_full_ID_bounds_hold_and_real512_AXIS_backpressure_tails_drain_passed',
          'independent_original_C_post_both_modes_passed', 'fresh_official4_dependency_deadlock_and_dataflow_monitored_full14_passed',
          'all_owned_bytes_collected_and_exact_server_root_absent'), 'fresh_official_monitored_original14_RTL_not_yet_independently_verified'),
        ('results/smooth_AXIS_D9_flow_RTL_r1/axis_rtl',
         'independent_PC_all40_actual_D9_malformed_reset_recovery_full_RTL_verified',
         ('all18351000_full_bank_words_independently_exact', 'all5_banks16_reports_unused_tails_exact',
          'real4_AXI_full_ID_bounds_hold_checks_and512_AXIS_errors_backpressure_checked',
          'input_partial_stall_and_output_stall_global_reset_recovery_checked',
          'global_reset_not_equivalent_to_unsafe_live_DFX_abort', 'all_owned_bytes_collected_and_exact_server_root_absent'),
         'original40_fault_reset_RTL_not_yet_independently_verified')]
    for folder, status, flags, message in gates:
        directory = ROOT / folder
        proof = directory / 'verified_Windows.json'
        if not proof.exists():
            pending.append(message)
            continue
        value = checked(proof, status, flags, bindings)
        retained = directory / 'current_candidate.zip'
        require(sha(retained) == value['archive_SHA256'], 'Actual RTL archive changed')
        bindings[retained.relative_to(ROOT).as_posix()] = value['archive_SHA256']
    static = ROOT / 'dfx/medical/build/static_routed.dcp'
    require(sha(static) == STATIC_SHA256, 'Frozen static design changed')
    for path in [static] + [ROOT / ('dfx/medical/build/config_' + name + '.dcp') for name in REFERENCES]:
        bindings[path.relative_to(ROOT).as_posix()] = sha(path)
    derivation = json.loads((HERE / 'derivation.json').read_text())
    require(sha(HERE / 'derive_sources.py') == derivation['source_SHA256'], 'Deriver changed')
    for row in derivation['records']:
        parent, target = ROOT / row['parent'], ROOT / row['candidate']
        require(sha(parent) == row['parent_SHA256'] and sha(target) == row['candidate_SHA256'], 'Recipe source changed')
        text = target.read_text()
        for edit in reversed(row['literal_edits']):
            require(text.count(edit['after']) == edit['count'], 'Changed derivation count')
            text = text.replace(edit['after'], edit['before'])
        require(text == parent.read_text(), 'Original test/physical gate changed')
        bindings[row['parent']] = row['parent_SHA256']
        bindings[row['candidate']] = row['candidate_SHA256']
    for path in (Path(__file__), HERE / 'derivation.json', HERE / 'derive_sources.py',
                 ROOT / 'tools/canonical_alias_promotion_r1.py'):
        bindings[path.relative_to(ROOT).as_posix()] = sha(path)
    return dict(status='D9_offline_physical_admission_ready' if not pending else 'D9_offline_physical_admission_waiting_for_actual_RTL',
        offline_route_admitted=not pending, pending_before_start=pending,
        candidate_DCP_SHA256=DCP_SHA256, candidate_DCP_member=area['DCP_member'],
        frozen_static_SHA256=STATIC_SHA256, actual_synthesized_RP=area['actual_complete_RM_resources'],
        five_full_PR_reference_configs=list(REFERENCES), original_clock_MHz=100,
        ARM_native_XRT_board_PS4_and_release_gates_preserved=True, preboarding_physical_candidate_only=True,
        source_and_evidence_SHA256=bindings, PL_accessed=False, production_promoted=False, whole_goal_completed=False)


def admit():
    result = inspect()
    require(result['offline_route_admitted'], '; '.join(result['pending_before_start']))
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--require-ready', action='store_true')
    args = parser.parse_args()
    result = inspect()
    print(json.dumps(dict(status=result['status'], admitted=result['offline_route_admitted'],
                          pending=result['pending_before_start']), indent=2))
    if args.require_ready and not result['offline_route_admitted']:
        sys.exit(2)
