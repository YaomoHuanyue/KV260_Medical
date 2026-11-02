"""Audit the complete-scene milestone; do not claim the whole goal complete."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from modules.surface_route.bundle_r8 import sha, write_json


def main():
    p = argparse.ArgumentParser(); p.add_argument('--label', choices=['Windows', 'ARM'], required=True)
    a = p.parse_args(); checkpoint_path = ROOT/'modules/surface_route/work_checkpoint_r8.json'
    c = json.loads(checkpoint_path.read_text())
    assert not c['whole_goal_completed'] and not c['production_promoted'] and not c['PL_access_this_milestone']
    for name, wanted in {**c['source_sha256'], **c['evidence_sha256']}.items():
        assert sha(ROOT/name) == wanted, name
    for platform in ['Windows', 'ARM']:
        proof = json.loads((ROOT/f'modules/surface_route/results/bundle_dispatch_tests_{platform}_r8.json').read_text())
        assert proof['count'] == 19 and all(x['passed'] for x in proof['cases'])
        portable = json.loads((ROOT/f'modules/surface_route/results/portable_reader_tests_{platform}_r8b.json').read_text())
        assert len(portable['cases']) == 4 and all(x['passed'] for x in portable['cases'])
        folder = ROOT/f'modules/surface_route/results/complete_bundles_{platform}_r8'
        data = json.loads((folder/'acceptance.json').read_text()); assert len(data['cases']) == 8
        for row in data['cases']:
            scene = folder/row['label']; meta = json.loads((scene/'scene.json').read_text())
            assert meta['revision'] == row['revision']
            for name, wanted in meta['identity']['files_sha256'].items():
                path = (scene/name).resolve(); assert path.parent == scene.resolve() and sha(path) == wanted
    cross = json.loads((ROOT/'modules/surface_route/results/complete_bundles_cross_platform_r8b.json').read_text())
    assert len(cross['cases']) == 8 and all(x['scene_packets_scalar_targets_normals_byte_exact'] for x in cross['cases'])
    reference_root = ROOT/'modules/surface_route/results/reference_frames_ARM_r8'
    reference = json.loads((reference_root/'acceptance.json').read_text())
    assert len(reference['cases']) == 8 and not reference['PL_access']
    for row in reference['cases']:
        assert row['every_depth_normal_target_outline_word_exact_PS1_PS4'] and row['max_steps'] == 1023
        for name, wanted in row['files_sha256'].items():
            assert sha(reference_root/row['label']/name) == wanted
        assert sha(reference_root/row['label']/'reference.u64') == row['pixels_sha256']
    progress = json.loads((ROOT/'docs/FEATURE_COMPLETION_PROGRESS.json').read_text())
    smooth = json.loads((ROOT/'dfx/smooth_speed/work_checkpoint.json').read_text())
    assert progress['current_surface_route_checkpoint'] == smooth['current_surface_route_checkpoint'] == 'modules/surface_route/work_checkpoint_r8.json'
    assert progress['status'] == 'active_not_all_features_completed'
    live = c['current_board_state']
    descriptor = json.loads((ROOT/'ui/active_release.json').read_text())
    assert sha(ROOT/'ui/active_release.json') == live['default_descriptor_sha256']
    assert sha(ROOT/'ui/run.sh') == live['manual_entry_sha256']
    assert sha(ROOT/descriptor['binary']) == live['UI_binary_sha256']
    assert sha(ROOT/descriptor['composite_binary']) == live['composite_worker_sha256']
    plan_path = ROOT/'tools/complete_surface_transfer_cleanup_plan_r8.json'
    plan = json.loads(plan_path.read_text())
    assert all(not (ROOT/n).exists() for n in plan['archives_sha256'])
    cleanup = json.loads((ROOT/f'results/complete_surface_transfer_cleanup_{a.label}_r8.json').read_text())
    assert cleanup['plan_sha256'] == sha(plan_path) and all(x['removed'] for x in cleanup['files'])
    runtime = dict(checked_here=False)
    if sys.platform == 'linux':
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == live['boot_id']
        jobs = []
        for proc in Path('/proc').iterdir():
            if not proc.name.isdecimal(): continue
            try: argv = (proc/'cmdline').read_bytes().split(b'\0')[:-1]
            except (OSError, PermissionError): continue
            if argv and argv[0].endswith(b'/medical_ui'): jobs.append(int(proc.name))
        assert jobs == [] and live['PID'] is None
        for receipt in ['complete_bundle_ARM_r8_started.json', 'reference_frames_ARM_r8b_started.json']:
            pid = json.loads((ROOT/'modules/surface_route/results'/receipt).read_text())['pid']
            assert not (Path('/proc')/str(pid)).exists()
        runtime = dict(checked_here=True, boot_id=live['boot_id'], default_UI_PID=None,
                       no_remaining_bundle_or_reference_job=True)
    write_json(ROOT/f'results/complete_scenes_final_gate_{a.label}_r8.json', dict(
        status='complete_scene_milestone_sources_full_payloads_references_progress_and_cleanup_passed',
        checkpoint_sha256=sha(checkpoint_path), runtime=runtime, whole_goal_completed=False,
        PL_access=False, UI_promoted=False))
    print('Complete-scene milestone gate passed', a.label)


if __name__ == '__main__': main()
