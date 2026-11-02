"""Final current-surface evidence check and exact transport archive cleanup."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--platform',choices=['Windows','ARM'],required=True);ap.add_argument('--plan-sha256',required=True);a=ap.parse_args()
    plan=ROOT/'tools/active_surface_cleanup_plan_r14d.json';assert sha(plan)==a.plan_sha256
    checkpoint=ROOT/'modules/surface_route/work_checkpoint_r14d.json';c=read(checkpoint)
    assert not c['whole_goal_completed'] and not c['production_promoted'] and c['native_UI_scope']['current_surface_selected_path_integrated']
    for n,h in {**c['source_sha256'],**c['evidence_sha256'],**c['current_board_state']['preserved_defaults_sha256']}.items():assert sha(ROOT/n)==h,n
    for n in ('docs/FEATURE_COMPLETION_PROGRESS.json','dfx/smooth_speed/work_checkpoint.json'):assert read(ROOT/n)['current_surface_route_checkpoint']==checkpoint.relative_to(ROOT).as_posix()
    if a.platform=='ARM':
        import fcntl
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==c['current_board_state']['boot_id']
        assert Path('/run/kv260-dfx-medical-loaded.sha256').read_text().strip()==c['current_board_state']['medical_shell_marker_sha256']
        s=read(ROOT/'modules/surface_route/results/active_surface_trial_ARM_r14d_started.json');assert not Path('/proc',str(s['PID'])).exists()
        with Path('/tmp/kv260-ct-pl.lock').open('rb') as lock:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    archives=[]
    for n,h in read(plan)['archives_sha256'].items():
        p=(ROOT/'tools'/n).resolve();assert p.parent==ROOT/'tools' and p.suffix=='.zip' and sha(p)==h
        with zipfile.ZipFile(p) as z:
            key='progress_manifest.json' if 'progress_manifest.json' in z.namelist() else 'upload_manifest.json'
            manifest=json.loads(z.read(key));assert set(z.namelist())==set(manifest)|{key}
            for name,value in manifest.items():
                rel=PurePosixPath(name);assert not rel.is_absolute() and '..' not in rel.parts and ':' not in name
                dest=(ROOT/name).resolve();assert dest.is_relative_to(ROOT)
                expected=value['new_sha256'] if isinstance(value,dict) else value
                assert sha(dest)==expected and hashlib.sha256(z.read(name)).hexdigest()==expected,name
        archives.append(p)
    output=ROOT/f'modules/surface_route/results/final_gate_{a.platform}_r14d.json';assert not output.exists()
    for p in archives:p.unlink()
    output.write_text(json.dumps(dict(status='active_surface_UI_sources_actual_C9_evidence_defaults_and_cleanup_verified',platform=a.platform,
        checkpoint_sha256=sha(checkpoint),plan_sha256=sha(plan),finalizer_sha256=sha(Path(__file__)),transport_archives_removed=len(archives),
        physical_review_pending=True,production_promoted=False,whole_goal_completed=False),indent=2)+'\n',encoding='utf-8')
    print(a.platform,'R14d final gate passed',flush=True)


if __name__=='__main__':main()
