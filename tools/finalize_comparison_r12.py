"""Verify complete comparison evidence and remove only exact transport archives."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--platform',choices=['Windows','ARM'],required=True)
    ap.add_argument('--plan-sha256',required=True);a=ap.parse_args()
    plan=ROOT/'tools/comparison_cleanup_plan_r12.json';assert sha(plan)==a.plan_sha256
    path=ROOT/'modules/surface_route/work_checkpoint_r12.json';c=read(path)
    assert not c['whole_goal_completed'] and not c['production_promoted']
    for name,digest in {**c['source_sha256'],**c['evidence_sha256']}.items():assert sha(ROOT/name)==digest,name
    for name,digest in c['current_board_state']['preserved_defaults_sha256'].items():assert sha(ROOT/name)==digest,name
    for name in ('docs/FEATURE_COMPLETION_PROGRESS.json','dfx/smooth_speed/work_checkpoint.json'):
        assert read(ROOT/name)['current_surface_route_checkpoint']==path.relative_to(ROOT).as_posix()
    if a.platform=='ARM':
        import fcntl
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==c['current_board_state']['boot_id']
        assert Path('/sys/firmware/devicetree/base/fpga-region/firmware-name').read_bytes().rstrip(b'\0')==b'dfx_medical.bin'
        for revision in (11,12):
            s=read(ROOT/f'modules/surface_route/results/comparison_trial_ARM_r{revision}_started.json')
            assert not Path('/proc',str(s['PID'])).exists()
        with Path('/tmp/kv260-ct-pl.lock').open('rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    archives=[]
    for name,digest in read(plan)['archives_sha256'].items():
        archive=(ROOT/'tools'/name).resolve()
        assert archive.parent==ROOT/'tools' and archive.suffix=='.zip' and sha(archive)==digest
        with zipfile.ZipFile(archive) as z:
            key='progress_manifest.json' if 'progress_manifest.json' in z.namelist() else 'upload_manifest.json'
            manifest=json.loads(z.read(key));assert set(z.namelist())==set(manifest)|{key}
            for name,expected in manifest.items():
                rel=PurePosixPath(name);assert not rel.is_absolute() and '..' not in rel.parts and ':' not in name
                target=(ROOT/name).resolve();assert target.is_relative_to(ROOT)
                digest=expected['new_sha256'] if isinstance(expected,dict) else expected
                assert sha(target)==digest and hashlib.sha256(z.read(name)).hexdigest()==digest,name
        archives.append(archive)
    receipt=ROOT/f'modules/surface_route/results/final_gate_{a.platform}_r12.json';assert not receipt.exists()
    for path in archives:path.unlink()
    receipt.write_text(json.dumps(dict(status='comparison_sources_full_PS_PL_evidence_defaults_and_transport_cleanup_verified',
        platform=a.platform,checkpoint_sha256=sha(ROOT/'modules/surface_route/work_checkpoint_r12.json'),
        finalizer_sha256=sha(Path(__file__)),plan_sha256=sha(plan),transport_archives_removed=len(archives),
        production_promoted=False,whole_goal_completed=False),indent=2)+'\n',encoding='utf-8',newline='\n')
    print(a.platform,'comparison final gate passed',flush=True)


if __name__=='__main__':main()
