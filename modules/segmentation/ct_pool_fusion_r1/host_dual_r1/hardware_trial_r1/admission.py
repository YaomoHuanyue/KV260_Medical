"""Bind a real physical result to the existing guarded dual-output ARM host.

No flags bypass qualification. Building this record never installs firmware,
opens XRT, takes a PL lock, changes the GUI, or claims board performance.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
CORE = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import project_storage

PROOFS = {
    'RTL': ('results/CT_pool_full199_RTL_20261021_r6/axis_rtl/verified_Windows.json',
        ('all398_full_outputs_padding_status_and_next_marker_independently_exact',
         'real4_global_resets_each_mode_not_live_DFX_abort_qualification',
         'actual_321bit_AXIS_and_all_AXI_channels_random_backpressure_ID_bounds_guards_checked')),
    'SYN': ('results/CT_pool_C5_SYN_20261021_r3/axis_hls/verified_Windows.json',
        ('actual_whole_C5_synthesis_qualified',)),
    'ARM_host': ('modules/segmentation/ct_pool_fusion_r1/host_dual_r1/ARM_native_r1/paired_verified.json',
        ('all_owned_ARM_model_files_collected_and_SHA_verified_then_exact_task_root_removed',)),
    'physical': ('results/CT_pool_C5_ROUTE_20261021_r1/axis_route/verified_Windows.json',
        ('same_frozen_RP', 'routed_100MHz', 'all5_original_static_pr_verify_passed'))}


class PendingQualification(RuntimeError):
    pass


def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def qualification():
    physical_path = ROOT / PROOFS['physical'][0]
    if not physical_path.is_file():
        raise PendingQualification('Actual collected and sealed 100MHz/all5PR/partial proof is not ready')
    dependencies = read(ROOT / 'results/storage_cleanup_20261015/current_dependencies.json')
    bindings = {}

    def retained(p):
        p = p.resolve()
        if not p.is_relative_to(ROOT) or not p.is_file() or p.is_symlink():
            raise RuntimeError('Unsafe or missing qualification dependency: ' + str(p))
        rel = p.relative_to(ROOT).as_posix()
        digest = sha(p)
        if dependencies.get('kv260_system/' + rel) != digest:
            raise PendingQualification('Qualification dependency has not been sealed or changed: ' + rel)
        bindings[rel] = digest
        return digest

    evidence = {}
    values = {}
    for role, (name, fields) in PROOFS.items():
        digest = retained(ROOT / name)
        value = read(ROOT / name)
        if not all(value.get(k) is True for k in fields):
            raise RuntimeError('Incomplete qualification: ' + role)
        evidence[role] = dict(path=name, SHA256=digest)
        values[role] = value
    physical = values['physical']
    if physical.get('schema') != 'kv260.ct_pool.C5.physical.v1':
        raise RuntimeError('Wrong physical core schema')
    if (physical['clock_MHz'] != 100 or physical['WNS_ns'] < 0 or physical['WHS_ns'] < 0
            or not physical['all_owned_bytes_and_closed_logs_collected_exact_root_absent']):
        raise RuntimeError('Actual timing or complete collection gate failed')
    if (values['ARM_host']['result']['numeric_and_lifecycle_checks'] != 311
            or values['ARM_host']['result']['refusals_before_DMA'] != 13
            or values['ARM_host']['result']['actual_HLS_C_convolution_writer_calls'] != 84):
        raise RuntimeError('Original full ARM typed-host scope changed')
    compiled_path = CORE / 'host_dual_r1/ARM_collected_verified.json'
    retained(compiled_path)
    compiled = read(compiled_path)
    library = CORE / 'host_dual_r1/ARM/libct_pool_candidate.so'
    library_sha = retained(library)
    if not compiled['all_own_ARM_compile_outputs_collected'] or compiled['verified']['library_SHA256'] != library_sha:
        raise RuntimeError('Actual ARM XRT library is not the compiled candidate')
    for name, digest in compiled['verified']['source_and_evidence_SHA256'].items():
        if retained(ROOT / name) != digest:
            raise RuntimeError('Compiled ARM source binding changed: ' + name)
    manifest_path = ROOT / 'dfx/medical/release/manifest.json'
    retained(manifest_path)
    manifest = read(manifest_path)
    if manifest['static_routed_sha256'] != physical['frozen_static_DCP_SHA256']:
        raise RuntimeError('Candidate uses a different frozen static shell')
    syn = values['SYN']
    if syn['physical_RP_bits'] != 1830:
        raise RuntimeError('Original RP interface width changed')
    archive = ROOT / 'results/CT_pool_C5_ROUTE_20261021_r1/axis_route/current_candidate.zip'
    if retained(archive) != physical['archive_SHA256']:
        raise RuntimeError('Collected physical archive changed')
    partial = physical['partial_SHA256']
    member = 'b/route/config_ct_pool_r1_pblock_rp_partial.bin'
    if physical['artifact_SHA256']['config_ct_pool_r1_pblock_rp_partial.bin'] != partial:
        raise RuntimeError('Partial is not bound to the routed candidate')
    return dict(schema='kv260.ct_pool.hardware_trial.v1',
        library_SHA256=library_sha, writer_control_address_bits=8, pool_shape_offset=128,
        partial_SHA256=partial, static_SHA256=manifest['bit_bin_sha256'], evidence=evidence,
        qualified_partial_archive=dict(path=archive.relative_to(ROOT).as_posix(), member=member,
            archive_SHA256=physical['archive_SHA256'], partial_SHA256=partial),
        source_and_evidence_SHA256=bindings,
        installed_firmware_and_idle_cooperative_PL_handoff_must_be_checked_before_ct_open=True,
        actual_full139_PL2502_inputs139_logits_and_strongest_PS1_PS4_endpoints_required=True,
        firmware_installed=False, PL_accessed=False, production_promoted=False, whole_goal_completed=False)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=('inspect', 'build'))
    a = p.parse_args()
    if a.action == 'inspect':
        try:
            value = qualification()
        except PendingQualification as error:
            print(json.dumps(dict(ready=False, reason=str(error), record_created=False,
                PL_accessed=False, whole_goal_completed=False)))
            return
        print(json.dumps(dict(ready=True, partial_SHA256=value['partial_SHA256'],
            record_created=False, firmware_installed=False, PL_accessed=False)))
        return
    project_storage.check(85_000_000)
    target = HERE / 'admission.json'
    assert not target.exists()
    value = qualification()
    value.update(UTC=datetime.now(timezone.utc).isoformat(), builder_source_SHA256=sha(Path(__file__)))
    with target.open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2)
    print('PASS sealed actual physical inputs bound to existing ARM host; firmware NOT installed and PL NOT opened')


if __name__ == '__main__':
    main()
