"""Manually stage/test D7, then restore the exact current HU32 HDMI case."""
from pathlib import Path
import argparse
import fcntl
import gzip
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
MODULE=HERE.parent
ROOT=HERE.parents[3]
OUT=ROOT/'results/MC_AXIS8_FMA2_pooled_board_r3'
sys.path.insert(0,str(ROOT))
from modules.mask_evaluation.ui.actual_pl_r3.check_ARM import review_identity


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def write(path,data):
    with path.open('x') as f:json.dump(data,f,indent=2);f.write('\n')


def unlocked():
    with open('/tmp/kv260-ct-pl.lock','rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(lock,fcntl.LOCK_UN)


def restore(state,before):
    # Use the actual current release's launcher and ownership checks. Older
    # restore helpers hardcode a different backend prepare command.
    from ui.releases.pl_reconstruction_r1.release_runtime import launch
    target=Path(state['actual_selected_result']).resolve()/'pipeline.json'
    assert target.is_relative_to(ROOT/'ui/runs') and not target.is_symlink()
    content=sha(target);stat=target.stat();pipeline=json.loads(target.read_text())
    assert pipeline['status']=='passed' and pipeline['input_sha256']==state['files_sha256']['fixtures/own_ct/CT-chest.nrrd']
    newest=max(p.stat().st_mtime_ns for pattern in ['ui/runs/*/pipeline.json','dfx/medical/results/*/whole_case/pipeline.json']
               for p in ROOT.glob(pattern))
    write(OUT/'selected_case_before_restore.json',dict(path=str(target),SHA256=content,atime_ns=stat.st_atime_ns,mtime_ns=stat.st_mtime_ns))
    try:
        os.utime(target,ns=(stat.st_atime_ns,newest+1000000000))
        current=launch()
        assert current['actual_selected_result']==state['actual_selected_result']
        assert current['actual_selected_scene']==state['actual_selected_scene']
        assert current['boot_id']==state['boot_id'] and current['medical_shell_marker']==state['medical_shell_marker']
        assert current['binary_sha256']==state['binary_sha256'] and current['files_sha256']==state['files_sha256']
    finally:
        assert sha(target)==content
        os.utime(target,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        write(OUT/'selected_case_timestamps_restored.json',dict(contents_and_timestamps_restored=True))
    assert review_identity(current)==[]
    after=(ROOT/'tools/storage_runtime_identity.json').read_bytes()
    mapping_path=ROOT/'tools/storage_protected_paths.json';mapping=json.loads(mapping_path.read_text())
    (OUT/'board_protection_before_restore.json.gz').write_bytes(gzip.compress(mapping_path.read_bytes(),mtime=0))
    for key in ['tools/storage_runtime_identity.json','kv260_system/tools/storage_runtime_identity.json']:
        if key in mapping:
            assert mapping[key]==hashlib.sha256(before).hexdigest();mapping[key]=hashlib.sha256(after).hexdigest()
    temporary=mapping_path.with_name(mapping_path.name+'.MC_FMA2_new');assert not temporary.exists()
    temporary.write_text(json.dumps(mapping,indent=2)+'\n');os.replace(temporary,mapping_path)
    (OUT/'runtime_identity_after.json').write_bytes(after)
    write(OUT/'restored_UI.json',dict(runtime=current,same_case_scene_ELF_and_release=True,
        old_PID=state['UI_PID'],no_auto_start_or_network_change=True))
    return current


def ui_is_live(proc,expected_ticks):
    try:
        fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
    except FileNotFoundError:
        return False
    assert int(fields[19])==expected_ticks,'Do not signal a reused UI PID'
    return fields[0]!='Z'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage-only',action='store_true');args=parser.parse_args()
    assert os.geteuid()==0 and os.uname().machine=='aarch64'
    release=MODULE/'host_pooled_r2/release_r1';manifest=json.loads((release/'manifest.json').read_text())
    assert manifest['full_PR_passed'] and manifest['identity']==0xd7 and manifest['same_context_actual_DMA_still_required']
    for name,digest in manifest['runtime_files_SHA256'].items():assert sha(ROOT/name)==digest,name
    (MODULE/'host_pooled_r2/results').mkdir(exist_ok=True)
    partial=MODULE/'dfx_r1/release_r1/medical_mc_D7_axis8_r2_partial.bin';target=Path('/lib/firmware')/partial.name
    assert sha(partial)==manifest['partial_SHA256'] and shutil.disk_usage(target.parent).free>=64*1024**2
    if target.exists():assert sha(target)==manifest['partial_SHA256'],'Do not replace different installed firmware'
    else:
        temporary=target.with_name(target.name+'.MC_FMA2_new');assert not temporary.exists()
        with partial.open('rb') as source,temporary.open('xb') as destination:
            for block in iter(lambda:source.read(1024**2),b''):destination.write(block)
            destination.flush();os.fsync(destination.fileno())
        assert sha(temporary)==manifest['partial_SHA256'];temporary.chmod(0o644);os.replace(temporary,target)
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='4',PYTHONDONTWRITEBYTECODE='1')
    command=[str(ROOT/'.venv/bin/python'),'-B','-X','utf8',str(HERE/'benchmark_board.py')]
    subprocess.run(command+['--preflight-only'],cwd=ROOT,env=env,check=True)
    if args.stage_only:print('PASS D7 firmware staged, no GUI signal/bit load',flush=True);return
    assert not OUT.exists()
    identity=ROOT/'tools/storage_runtime_identity.json';before=identity.read_bytes();state=json.loads(before)
    assert review_identity(state)==[],'Preserve active render/medical jobs; retry when CT page is idle'
    assert json.loads((ROOT/'ui/active_release.json').read_text())['schema']=='kv260.manual_PL_D7_FMA2_UI.v1'
    proc=Path('/proc')/str(state['UI_PID'])
    scenes=set()
    for fd in (proc/'fd').iterdir():
        try:path=fd.resolve(strict=True)
        except (FileNotFoundError,PermissionError):continue
        if path.name=='ct.f32':scenes.add(str(path.parent/'scene.json'))
    assert scenes=={state['actual_selected_scene']},scenes
    OUT.mkdir();(OUT/'runtime_identity_before.json').write_bytes(before)
    write(OUT/'started.json',dict(PID=os.getpid(),start_ticks=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]),
        UI_PID=state['UI_PID'],release_manifest_SHA256=sha(release/'manifest.json'),partial_SHA256=manifest['partial_SHA256'],
        controller_SHA256=sha(__file__),benchmark_SHA256=sha(HERE/'benchmark_board.py')))
    stopped=False;receipt=None;restored=None
    try:
        review_identity(state);os.kill(state['UI_PID'],signal.SIGTERM)
        deadline=time.monotonic()+90
        while ui_is_live(proc,state['UI_start_ticks']) and time.monotonic()<deadline:time.sleep(.2)
        assert not ui_is_live(proc,state['UI_start_ticks']),'Keep undrained UI, no forced termination'
        stopped=True;unlocked();start=time.perf_counter();argv=command+['--output',str(OUT/'benchmark.json')]
        with (OUT/'benchmark.log').open('xb') as log:
            child=subprocess.Popen(argv,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
            write(OUT/'benchmark_started.json',dict(PID=child.pid,argv=argv,
                start_ticks=int(Path('/proc',str(child.pid),'stat').read_text().rsplit(')',1)[1].split()[19])))
            code=child.wait() # A DMA timeout retains buffers. Never force kill.
        receipt=dict(exit_code=code,elapsed_seconds=time.perf_counter()-start,log_SHA256=sha(OUT/'benchmark.log'))
        write(OUT/'benchmark_receipt.json',receipt)
    except BaseException:
        write(OUT/'failure.json',dict(traceback=traceback.format_exc()));raise
    finally:
        if stopped:
            unlocked();restored=restore(state,before)
    assert receipt and receipt['exit_code']==0 and restored is not None
    proof=json.loads((OUT/'benchmark.json').read_text());assert proof['actual_D7_FMA2_same_context_passed'] and proof['actual_full_and_partial_entries_passed']
    write(OUT/'complete.json',dict(actual_D7_FMA2_combined_board_executed=True,correctness_passed=True,
        speed_gate_passed=False,exact_reviewed_case_restored=True,
        restored_UI_PID=restored['UI_PID'],boot_and_static_unchanged=True,
        no_forced_kill_ZOCL_unload_network_change_or_auto_start=True,
        production_promoted=False,whole_goal_completed=False))
    print('PASS actual D7/FMA2 combined board trial; reviewed HDMI case restored, PID',restored['UI_PID'],flush=True)


if __name__=='__main__':main()
