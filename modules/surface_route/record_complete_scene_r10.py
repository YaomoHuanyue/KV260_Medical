"""Record actual C9 and current-scene export; retain the full original goal."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.surface_route.bundle_r8 import sha, write_json


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    folder = ROOT/'modules/surface_route'
    hardware = read(folder/'results/actual_C9_ARM_r10/acceptance.json')
    gui = read(folder/'results/native_C9_GUI_ARM_r10/acceptance.json')
    export = read(folder/'results/active_export_ARM_r10/acceptance.json')
    export_ui = read(folder/'results/native_export_GUI_ARM_r10/acceptance.json')
    live = read(ROOT/'results/complete_scene_live_r10.json')
    assert hardware['PL_all_frames_faster_than_PS4'] and hardware['full_static_1MiB_echo_and_C6_restore_passed']
    assert gui['status'] == 'actual_HDMI_complete_scene_C9_navigation_passed'
    assert export['status'] == 'ARM_active_export_kernels_and_full_own_CT_bundle_passed'
    assert export_ui['status'] == 'actual_HDMI_active_scene_export_button_passed'
    closure = folder/'native_UI_source_closure_r10.json'
    source_hashes = read(closure)['files_sha256']
    source_files = [*folder.glob('*r10*.py'), closure,
        *ROOT.glob('tools/*scene*trial_r10.py'), ROOT/'tools/active_scene_export_trial_r10.py',
        ROOT/'tools/load_medical_clean_boot_r10.py', ROOT/'tools/finalize_complete_scene_r10.py']
    source_hashes.update({p.relative_to(ROOT).as_posix():sha(p) for p in source_files})
    evidence = [*folder.glob('results/*r10*.json'), *folder.glob('results/*r10*.log'),
        *folder.glob('results/actual_C9_ARM_r10/**/*'),
        *folder.glob('results/native_C9_GUI_ARM_r10/**/*'),
        *folder.glob('results/active_export_ARM_r10/**/*'),
        *folder.glob('results/native_export_GUI_ARM_r10/**/*'),
        ROOT/'results/medical_clean_boot_init_preflight_r10.json',
        ROOT/'results/medical_clean_boot_init_r10.json', ROOT/'results/complete_scene_live_r10.json',
        ROOT/'ui/releases/feature_completion_r6/build_complete_scene_r10/failure.json',
        *ROOT.glob('ui/releases/feature_completion_r6/build_complete_scene_r10b/*'),
        ROOT/'docs/COMPLETE_SCENE_C9_EXPORT_R10.md', folder/'work_checkpoint_r9.json']
    current_export = Path(export_ui['export'])
    if not current_export.is_relative_to(ROOT):
        # Windows stores the same ARM absolute path as provenance, while its
        # delivered payload occupies the matching integration-relative path.
        prefix = '/home/ubuntu/jupyter_notebooks/KV260_System/'
        assert export_ui['export'].startswith(prefix)
        current_export = ROOT/export_ui['export'][len(prefix):]
    evidence += list(current_export.rglob('*'))
    rows = hardware['cases']
    motion = gui['actual_UI_acceptance']['navigation_interaction']
    checkpoint = dict(status='actual_C9_exact_PS4_faster_and_active_scene_full_export_Qt_verified',
        goal_turn_classification='progress', whole_goal_completed=False, production_promoted=False,
        source_sha256=source_hashes,
        evidence_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(evidence)) if p.is_file()},
        current_board_state=live, PL_access_this_milestone=True, new_bitstream_generated=False,
        previous_checkpoint_sha256=sha(folder/'work_checkpoint_r9.json'),
        validation=dict(C9_same_input_frames=len(rows), every_64bit_depth_normal_coverage_outline_word_exact=True,
            PS4_median_API_ms_range=[min(r['PS4_median_full_call_seconds'] for r in rows)*1000,
                                    max(r['PS4_median_full_call_seconds'] for r in rows)*1000],
            PL_median_API_ms_range=[min(r['PL_median_full_call_seconds'] for r in rows)*1000,
                                   max(r['PL_median_full_call_seconds'] for r in rows)*1000],
            speedup_range=[min(r['PL_over_PS4_speedup'] for r in rows), max(r['PL_over_PS4_speedup'] for r in rows)],
            timing_scope=hardware['performance_scope'], GUI_completed_PL_frames=gui['actual_UI_acceptance']['pl_scope_frames'],
            GUI_motion_presented_frames=motion['presented_frames'], GUI_actual_update_fps=motion['actual_update_fps'],
            GUI_motion_gap_p95_ms=motion['gap_p95_ms'], GUI_motion_gap_max_ms=motion['gap_max_ms'],
            Windows_export_cases=8, ARM_export_cases=8, full_own_CT_export=export['full_export'],
            actual_Qt_export_UI=export_ui, user_physical_review=False,
            ordinary_opacity_physical_acceptance='ui/releases/feature_completion_r6/acceptance_physical_fast_opacity_r3.json'),
        computation=dict(PL='existing accepted C1 mesh provenance and actual C9 depth/normal/exit coverage/outline',
            PS='scene contracts, immutable request dispatch, prepared overview attributes, file serialization and report validation',
            GPU='overview drawing and completed C9 image display/shading'),
        known_failure='Initial build/export preflight found a missing bound helper; no PL access. Exact helper installed, original failure retained; R10b compiled and tests passed.',
        next_actions=['Integrate explicit scene/quality selection and generic new-run scene preparation',
            'Recompute instrument profile and Pareto against the active field before enabling their controls',
            'Bind batch/video/recovery dispatch to active scene and complete their physical review',
            'Reduce repeated cold full-asset verification with immutable content binding',
            'Complete original exposure/vignette/outline glow/ray-step heatmap/breathing and remaining performance comparisons'])
    write_json(folder/'work_checkpoint_r10.json', checkpoint)
    changes = {}
    for relative in ['docs/FEATURE_COMPLETION_PROGRESS.json','dfx/smooth_speed/work_checkpoint.json']:
        path = ROOT/relative
        before = sha(path)
        value = read(path)
        value['previous_goal_turn_result'] = value.get('current_goal_turn_result')
        value['current_goal_turn_result'] = dict(classification='progress', checkpoint='modules/surface_route/work_checkpoint_r10.json',
            status=checkpoint['status'], whole_goal_completed=False, production_promoted=False)
        value['current_surface_route_checkpoint'] = 'modules/surface_route/work_checkpoint_r10.json'
        if relative.startswith('docs/'):
            value['current_board_UI_state'] = live
        else:
            value['status'] = 'active_original_feature_completion_C9_and_active_export_R10_verified'
            value['last_current_board_state_receipt'] = 'results/complete_scene_live_r10.json'
            value['current_board_boot_id'] = live['boot_id']
            value['latest_original_surface_UI_promoted'] = False
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')
        changes[relative] = dict(previous_sha256=before, new_sha256=sha(path))
    write_json(folder/'results/complete_scene_progress_plan_r10.json', dict(files=changes))
    print(checkpoint['status'])


if __name__ == '__main__':
    main()
