"""Verify R10 source/evidence/defaults and remove exact delivery ZIPs only."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text(encoding='utf-8'))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--platform', choices=['Windows','ARM'], required=True)
    p.add_argument('--cleanup-sha', required=True)
    a = p.parse_args()
    plan = ROOT/'tools/complete_scene_transfer_cleanup_plan_r10.json'
    assert sha(plan) == a.cleanup_sha
    checkpoint = ROOT/'modules/surface_route/work_checkpoint_r10.json'
    c = read(checkpoint)
    assert not c['whole_goal_completed'] and not c['production_promoted']
    for name, expected in {**c['source_sha256'], **c['evidence_sha256']}.items():
        assert sha(ROOT/name) == expected, name
    live = c['current_board_state']
    for name, expected in live['preserved_defaults_sha256'].items():
        assert sha(ROOT/name) == expected, name
    for relative in ['docs/FEATURE_COMPLETION_PROGRESS.json','dfx/smooth_speed/work_checkpoint.json']:
        assert read(ROOT/relative)['current_surface_route_checkpoint'] == 'modules/surface_route/work_checkpoint_r10.json'
    for platform in ['Windows','ARM']:
        proof = read(ROOT/f'modules/surface_route/results/export_kernels_{platform}_r10.json')
        assert len(proof['cases']) == 8 and all(r['every_triangle_normal_attribute_and_route_exact'] for r in proof['cases'])
    if a.platform == 'ARM':
        import fcntl
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == live['boot_id']
        assert Path('/sys/firmware/devicetree/base/fpga-region/firmware-name').read_bytes().rstrip(b'\0').decode() == live['static_firmware']
        assert Path('/run/kv260-dfx-medical-loaded.sha256').read_text().strip() == live['medical_shell_marker_sha256']
        for tag in live['completed_supervisor_tags']:
            started = read(ROOT/f'modules/surface_route/results/{tag}_started.json')
            assert not Path('/proc',str(started['PID'])).exists(), tag
        for process in Path('/proc').iterdir():
            try:
                if not process.name.isdigit():
                    continue
                assert process.joinpath('comm').read_text().strip() != 'medical_ui'
                argv = process.joinpath('cmdline').read_bytes().split(b'\0')
                assert not any(v.endswith(b'/quality_worker_r9.py') for v in argv)
            except FileNotFoundError:
                pass
        with Path('/tmp/kv260-ct-pl.lock').open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(lock, fcntl.LOCK_UN)
    archives = []
    for name, expected in read(plan)['archives_sha256'].items():
        archive = (ROOT/'tools'/name).resolve()
        assert archive.parent == ROOT/'tools' and archive.suffix == '.zip' and sha(archive) == expected
        with zipfile.ZipFile(archive) as z:
            key = 'progress_manifest.json' if 'progress_manifest.json' in z.namelist() else 'upload_manifest.json'
            manifest = json.loads(z.read(key))
            assert set(z.namelist()) == set(manifest)|{key}
            for name, expected in manifest.items():
                rel = PurePosixPath(name)
                assert not rel.is_absolute() and '..' not in rel.parts and ':' not in name
                target = (ROOT/name).resolve()
                assert target.is_relative_to(ROOT)
                wanted = expected['new_sha256'] if isinstance(expected,dict) else expected
                assert sha(target) == wanted and hashlib.sha256(z.read(name)).hexdigest() == wanted, name
        archives.append(archive)
    receipt = ROOT/f'modules/surface_route/results/final_gate_{a.platform}_r10.json'
    assert not receipt.exists()
    for archive in archives:
        archive.unlink()
    receipt.write_text(json.dumps(dict(status='R10_sources_C9_export_proofs_defaults_and_transfer_cleanup_verified',
        platform=a.platform, checkpoint_sha256=sha(checkpoint), finalizer_sha256=sha(Path(__file__)),
        cleanup_plan_sha256=sha(plan), delivery_ZIPs_removed=len(archives),
        ARM_live_state_checked=a.platform == 'ARM', whole_goal_completed=False,
        production_promoted=False), indent=2)+'\n', encoding='utf-8', newline='\n')
    print(a.platform, 'R10 final gate passed and exact delivery ZIPs removed')


if __name__ == '__main__':
    main()
