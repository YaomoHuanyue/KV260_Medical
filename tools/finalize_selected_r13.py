"""Recheck R13 closed evidence/defaults and remove exact transport archives only."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,sys,zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--platform',choices=['Windows','ARM'],required=True)
    ap.add_argument('--plan-sha256',required=True);a=ap.parse_args()
    plan=ROOT/'tools/selected_cleanup_plan_r13.json';assert sha(plan)==a.plan_sha256
    checkpoint=ROOT/'modules/surface_route/work_checkpoint_r13.json';c=read(checkpoint)
    assert not c['whole_goal_completed'] and not c['production_promoted']
    assert not c['selected_backend_scope']['native_UI_comparison_and_selected_path_controls_integrated']
    for name,h in {**c['source_sha256'],**c['evidence_sha256']}.items():assert sha(ROOT/name)==h,name
    for name,h in c['current_board_state']['preserved_defaults_sha256'].items():assert sha(ROOT/name)==h,name
    for name in ('docs/FEATURE_COMPLETION_PROGRESS.json','dfx/smooth_speed/work_checkpoint.json'):
        assert read(ROOT/name)['current_surface_route_checkpoint']==checkpoint.relative_to(ROOT).as_posix()
    if a.platform=='ARM':
        import fcntl
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==c['current_board_state']['boot_id']
        assert Path('/sys/firmware/devicetree/base/fpga-region/firmware-name').read_bytes().rstrip(b'\0')==b'dfx_medical.bin'
        s=read(ROOT/'modules/surface_route/results/selected_trial_ARM_r13_started.json')
        assert not Path('/proc',str(s['PID'])).exists()
        with Path('/tmp/kv260-ct-pl.lock').open('rb') as lock:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    archives=[]
    for name,h in read(plan)['archives_sha256'].items():
        p=(ROOT/'tools'/name).resolve();assert p.parent==ROOT/'tools' and p.suffix=='.zip' and sha(p)==h
        with zipfile.ZipFile(p) as z:
            key='progress_manifest.json' if 'progress_manifest.json' in z.namelist() else 'upload_manifest.json'
            manifest=json.loads(z.read(key));assert set(z.namelist())==set(manifest)|{key}
            for name,value in manifest.items():
                rel=PurePosixPath(name);assert not rel.is_absolute() and '..' not in rel.parts and ':' not in name
                dest=(ROOT/name).resolve();assert dest.is_relative_to(ROOT)
                expected=value['new_sha256'] if isinstance(value,dict) else value
                assert sha(dest)==expected and hashlib.sha256(z.read(name)).hexdigest()==expected,name
        archives.append(p)
    output=ROOT/f'modules/surface_route/results/final_gate_{a.platform}_r13.json';assert not output.exists()
    for p in archives:p.unlink()
    output.write_text(json.dumps(dict(status='selected_backend_sources_PS_PL_evidence_defaults_and_cleanup_verified',
        platform=a.platform,checkpoint_sha256=sha(checkpoint),plan_sha256=sha(plan),finalizer_sha256=sha(Path(__file__)),
        transport_archives_removed=len(archives),native_UI_selected_controls_pending=True,
        production_promoted=False,whole_goal_completed=False),indent=2)+'\n',encoding='utf-8')
    print(a.platform,'R13 final gate passed',flush=True)


if __name__=='__main__':main()
