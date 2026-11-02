"""Independently read routed100MHz/all5PR and full collection before board admission."""
from pathlib import Path
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import sys
import preflight
import collect
from check_reports import ARTIFACTS, PARTIALS, REPORTS, MARKER, REFERENCES, physical_reports, check_pr

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parents[2]
OUT = collect.OUT


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    sys.path.insert(0, str(ROOT / 'tools'))
    import project_storage
    project_storage.check(1_000_000)
    target = OUT / 'verified_Windows.json'
    assert not target.exists() and not (OUT / 'verified_failure_Windows.json').exists()
    current = preflight.admit()
    collect.configure()
    receipt = json.loads((OUT / 'stream_collection_verified.json').read_text())
    cleanup = json.loads((OUT / 'cleanup_verified_stream.json').read_text())
    assert cleanup['owned_root_confirmed_absent'] and cleanup['all_owned_member_bytes_and_closed_logs_stream_SHA_verified_locally']
    archive = OUT / 'current_candidate.zip'
    original, terminal = collect.helper.verify(archive, receipt)
    spec = importlib.util.spec_from_file_location('independent_C5_route_archive_view', preflight.CODEC)
    codec = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(codec)
    with ExitStack() as stack:
        view = codec.View(stack, archive)
        assert terminal['all_owned_compiler_processes_terminal']
        if not terminal['tool_gates_passed']:
            failure = dict(status='actual_C5_route_failed_all_gates_preserved_owned_bytes_collected',
                terminal=terminal, task_log=view.read('task.log').decode(errors='replace'),
                archive_SHA256=sha(archive), all_owned_bytes_and_closed_logs_collected_exact_root_absent=True,
                PL_accessed=False, production_promoted=False, whole_goal_completed=False)
            if collect.PREFIX + 'failure.json' in original:
                failure['primary_failure'] = json.loads(view.read(collect.PREFIX + 'failure.json'))
            with (OUT / 'verified_failure_Windows.json').open('x', encoding='utf-8') as stream:
                json.dump(failure, stream, indent=2)
            print('PRESERVED actual C5 physical failure; original clocks and PR gates unchanged', flush=True)
            return
        accepted = json.loads(view.read(collect.PREFIX + 'complete.json'))
        assert accepted['actual_same_version_100MHz_route_and_all5_fullPR_passed']
        assert accepted['all_five_firmware_artifacts_generated_and_hashed']
        assert accepted['full986_RTL_all8_resets_original_full139_typed_model_gates_preserved']
        assert current['candidate_DCP_SHA256'] == accepted['candidate_DCP_SHA256']
        assert current['frozen_static_DCP_SHA256'] == accepted['frozen_static_DCP_SHA256']
        result = physical_reports(*(view.read(collect.BUILD + name).decode(errors='replace') for name in REPORTS[:3]))
        for key, value in result.items():
            assert value == accepted[key], key
        result['five_reference_full_PR'] = [check_pr(view.read(collect.BUILD + 'pr_verify_ct_tensor_r3_' + ref + '.log').decode(errors='replace'), ref)
                                            for ref in REFERENCES]
        assert result['five_reference_full_PR'] == accepted['five_reference_full_PR']
        assert receipt['all_original_members_stream_SHA_verified_locally']
        artifacts = {}
        for name in ARTIFACTS + REPORTS + (MARKER,):
            expected = accepted['artifact_SHA256'][name]
            assert original[collect.BUILD + name] == expected
            # Collector has consumed every full artifact byte. Re-read retained
            # partial firmware/reports; do not regenerate full artifacts locally.
            if name not in ARTIFACTS[:3]:
                with view.stream(collect.BUILD + name) as stream:
                    assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected
            artifacts[name] = expected
        for name, expected in accepted['source_and_evidence_SHA256'].items():
            with view.stream('workspace/' + name) as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected, name
            assert sha(ROOT / name) == expected, name
        for name, expected in accepted['physical_input_SHA256'].items():
            with view.stream(name) as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected, name
        runtime = json.loads(view.read(collect.PREFIX + 'route_receipt.json'))
        assert runtime['exit_code'] == 0 and runtime['all_owned_processes_terminal']
        assert runtime['configured_limit_verified'] and runtime['actual_default_memory_API']
        assert runtime['job_memory_limit_bytes'] == 28 * 1024**3
        assert not runtime['resource_failure'] and not runtime['elapsed_time_abort']
    result.update(schema='kv260.ct_pool.C5.physical.v1', same_frozen_RP=True,
        routed_100MHz=True, all5_original_static_pr_verify_passed=True,
        status='independent_actual_C5_100MHz_setup_hold_DRC_all5PR_and_partial_firmware_verified_not_board',
        candidate_DCP_SHA256=current['candidate_DCP_SHA256'], frozen_static_DCP_SHA256=current['frozen_static_DCP_SHA256'],
        artifact_SHA256=artifacts, partial_SHA256=artifacts[PARTIALS[-1]],
        actual_route_seconds=runtime['elapsed_s'], actual_route_peak_job_bytes=runtime['reported_peak_job_bytes'],
        archive_SHA256=sha(archive), all_owned_bytes_and_closed_logs_collected_exact_root_absent=True,
        full986_RTL_all8_resets_full139_model_and_ARM_host_prerequisites_preserved=True,
        actual_ARM_XRT_DMA_board_full139_strongest_PS1_PS4_and_integration_still_required=True,
        source_and_evidence_SHA256={path.relative_to(ROOT).as_posix(): sha(path) for path in
            (Path(__file__), HERE / 'check_reports.py', HERE / 'preflight.py',
             OUT / 'stream_collection_verified.json', OUT / 'cleanup_verified_stream.json',
             ROOT / 'results/CT_pool_full493_RTL_20261021_r7/axis_rtl/verified_Windows.json')},
        PL_accessed=False, production_promoted=False, whole_goal_completed=False)
    with target.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print('PASS actual C5 routed100MHz/setup/hold/all5PR and partial bytes; board and speed gates remain', flush=True)


if __name__ == '__main__':
    main()
