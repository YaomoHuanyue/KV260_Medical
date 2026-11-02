"""Seal complete original-surface evidence; observe current boot without PL access."""
from pathlib import Path
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SHA = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
READ = lambda p: json.loads(Path(p).read_text())


def main():
    assert sys.platform == 'linux'
    output = HERE/'work_checkpoint_r7.json'
    live_path = ROOT/'results/original_surfaces_live_r7.json'
    assert not output.exists() and not live_path.exists()
    cross_path = HERE/'results/original_surface_cross_platform_r7b.json'
    cross = READ(cross_path)
    assert cross['source_sha256'] == SHA(HERE/'compare_original_surfaces_r7b.py')
    assert len(cross['cases']) == 12
    assert cross['mesh_indexing']['all_four_scalar_mesh_points_and_indices_byte_exact']
    evidence = {}
    folders = {
        'mesh_Windows': HERE/'results/original_mesh_indexing_Windows_r7',
        'mesh_ARM': HERE/'results/original_mesh_indexing_ARM_r7',
        'route_Windows': HERE/'results/original_surface_replan_Windows_r7',
        'route_ARM': HERE/'results/original_surface_replan_ARM_r7b',
    }
    for kind, folder in folders.items():
        proof = READ(folder/'acceptance.json')
        for name, digest in {**proof['source_sha256'], **proof['input_sha256']}.items():
            assert SHA(ROOT/name) == digest, name
        if kind.startswith('mesh'):
            assert proof['all_four_passed'] and len(proof['cases']) == 4
            for c in proof['cases']:
                assert c['retained_ordered_triangles_byte_exact'] and c['original_scalar_unchanged']
                for name, digest in c['files_sha256'].items():
                    assert SHA(folder/c['name']/name) == digest, name
        else:
            assert len(proof['cases']) == 12
            for c in proof['cases']:
                assert c['status'] == 'geometry_filtered_replan_camera_and_scalar_guidance_passed'
                if c['point_count'] > 1:
                    assert c['available_events'] == c['guidance_events'] == 3
                else:
                    assert c['guidance_events'] == 0
                for name, digest in c['files_sha256'].items():
                    assert SHA(folder/name) == digest, name
        for p in folder.rglob('*'):
            if p.is_file():
                evidence[p.relative_to(ROOT).as_posix()] = SHA(p)
    for platform in ('Windows', 'ARM'):
        p = HERE/f'results/original_mesh_indexing_unit_{platform}_r7.json'
        unit = READ(p)
        assert len(unit['tests']) == 6
        for name, digest in unit['source_sha256'].items():
            assert SHA(ROOT/name) == digest, name
        evidence[p.relative_to(ROOT).as_posix()] = SHA(p)
    original = READ(HERE/'results/original_surface_mesh_ARM_r6/acceptance.json')
    assert len(original['cases']) == 4
    for c in original['cases']:
        assert c['PL_topology_repeats_byte_exact']
        assert c['far_negative_saturation_preserves_all_crossing_edges']
    for rel in (
        'modules/surface_route/results/original_surface_mesh_ARM_r6/acceptance.json',
        'modules/surface_route/results/original_mesh_diagnosis_r6.json',
        'modules/surface_route/results/original_surface_cross_platform_r6.json',
        'modules/surface_route/results/original_surface_cross_platform_r7b.json',
        'modules/surface_route/results/state_after_board_original_surface_mesh_r6b.json',
        'modules/surface_route/results/original_surface_replan_ARM_r7_interrupted.json',
        'modules/surface_route/results/original_surface_replan_ARM_r7b_started.json',
        'modules/surface_route/results/original_surface_replan_ARM_r7b.log',
        'ui/releases/feature_completion_r6/acceptance_physical_fast_opacity_r3.json',
    ):
        evidence[rel] = SHA(ROOT/rel)
    for platform in ('Windows', 'ARM'):
        key = 'mesh_'+platform
        assert cross['mesh_indexing']['evidence_sha256'][platform] == SHA(folders[key]/'acceptance.json')
        assert cross['evidence_sha256'][platform] == SHA(folders['route_'+platform]/'acceptance.json')
    sys.path.insert(0, str(ROOT/'ui/production_r1'))
    from verify_release_r17_r2 import verify
    release = verify('ui/active_release.json')
    expected = [release['binary'].encode(), b'--root', str(ROOT).encode()]
    running = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            argv = (proc/'cmdline').read_bytes().split(b'\0')[:-1]
        except (FileNotFoundError, ProcessLookupError):
            continue
        if argv == expected:
            assert SHA(proc/'exe') == SHA(ROOT/release['binary'])
            running.append(int(proc.name))
    assert len(running) <= 1
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    restore = READ(HERE/'results/state_after_board_original_surface_mesh_r6b.json')
    live = dict(status='current_boot_and_default_UI_files_observed_without_PL_access',
        boot_id=boot, PID=running[0] if running else None,
        tested_formal_default_UI_running=bool(running),
        UI_binary_sha256=SHA(ROOT/release['binary']), default_descriptor_sha256=SHA(ROOT/'ui/active_release.json'),
        manual_entry_sha256=SHA(ROOT/'ui/run.sh'), manual_only=True,
        previous_restoration_boot_id=restore['boot_id'], previous_restored_PID=restore['PID'],
        previous_restoration_is_historical=boot != restore['boot_id'],
        PL_access=False, static_shell_reloaded=False, ZOCL_unloaded=False)
    sources = [
        'modules/surface_quality/scalar_mesh_r7.py', 'modules/surface_quality/scalar_mesh_indexing_r7.py',
        'modules/surface_quality/scalar_mesh_derivation_r7.json', 'modules/surface_quality/test_scalar_mesh_indexing_r7.py',
        'modules/surface_route/original_mesh_indexing_trial_r7.py', 'modules/surface_route/original_surface_replan_r7.py',
        'modules/surface_route/original_surface_replan_derivation_r7.json',
        'modules/surface_route/compare_original_surfaces_r7b.py',
        'modules/surface_route/original_surfaces_comparison_derivation_r7b.json',
        'modules/surface_route/README_ORIGINAL_SURFACES_r7.md', 'modules/surface_route/record_original_surfaces_r7.py',
    ]
    result = dict(status='four_original_surfaces_exact_PL_geometry_indexing_and_twelve_Windows_ARM_routes_guidance_passed',
        goal_turn_classification='progress', whole_goal_completed=False,
        source_sha256={n:SHA(ROOT/n) for n in sources}, evidence_sha256=evidence, current_board_state=live,
        PL_topology=dict(actual_C1_cases=4, repeats_each_case=2,
            proof='modules/surface_route/results/original_surface_mesh_ARM_r6/acceptance.json',
            source_boot_id=restore['boot_id'], warm_core_seconds=[c['MC_trials'][1]['compute_seconds'] for c in original['cases']],
            warm_full_host_seconds=[c['MC_trials'][1]['host_seconds'] for c in original['cases']],
            new_PS_PL_speed_claim=False, new_bitstream=False, resources_changed=False),
        original_scalar_and_retained_ordered_triangles_unchanged=True,
        full_vertex_link_and_unchanged_mesh_region_checks_passed=True,
        PS='shared scalar edge interpolation, index-only fan/link handling and one-time sparse route/camera/guidance preparation',
        PL='retained actual C1 topology; existing C9 renderer awaits complete new-surface UI and frame comparison',
        remaining=['Complete same-scalar mesh/route/camera/guidance UI bundle',
            'Actual new-route C9/strongest PS frame comparison and native UI/physical review',
            'Original remaining visual/export features and full-API profile/smoothing acceleration',
            'Reduce one-time original-field and mesh-validation preparation overhead'],
        production_promoted=False, PS_Marching_Cubes_used=False, clinical_safety_certified=False)
    assert boot == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
    live_path.write_text(json.dumps(live, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(result['status'], 'current_UI_PID', live['PID'], flush=True)


if __name__ == '__main__':
    main()
