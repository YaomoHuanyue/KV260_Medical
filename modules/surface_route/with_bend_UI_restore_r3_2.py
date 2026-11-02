# Derived from the sealed R2 lifecycle for nonzero bend query inputs; see bend_C4_derivation_r3.json.
"""Drain the exact verified R17 UI, compare accepted C4, restore accepted C6."""
from pathlib import Path
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
SHA=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
BOOT='e95c2c0b-2c3b-41cf-8127-c4ff6550935c'
UI_SHA='1e58f3b6e77147ee8048f6952c5c477c4f03922c8dfb80402435838977983ff6'
DESCRIPTOR_SHA='7bc2f8e3edf017449dd737728e9f8ff099dd6a46c2c0c03f1b0b4ac0920ebe06'
ENTRY_SHA='d30ecad6ab8db031c77e562429da3485994c2e2edfa502130f8196e420952532'
WORKER_SHA='1b5a2149a624d53c740f972575800eed18934dd096ec1e5f311f81aea9a41b83'


def ui_binding():
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT
    assert SHA(ROOT/'ui/active_release.json')==DESCRIPTOR_SHA
    assert SHA(ROOT/'ui/run.sh')==ENTRY_SHA
    assert SHA(ROOT/'dfx/composite/medical/exact_speed_r26/worker')==WORKER_SHA
    spec=importlib.util.spec_from_file_location('verified_R17',ROOT/'ui/production_r1/verify_release_r17_r2.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    release=module.verify('ui/active_release.json')
    assert SHA(ROOT/release['binary'])==UI_SHA
    argv=[release['binary'].encode(),b'--root',str(ROOT).encode()]
    matches=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:found=(proc/'cmdline').read_bytes().split(b'\0')[:-1]
        except (FileNotFoundError,ProcessLookupError):continue
        if found==argv:
            assert SHA(proc/'exe')==UI_SHA
            matches.append(int(proc.name))
    assert len(matches)==1,'Expected exactly one verified R17 UI'
    return argv,matches[0]


def main():
    assert sys.platform=='linux' and os.geteuid()==0
    parser=argparse.ArgumentParser();parser.add_argument('--check-only',action='store_true');args=parser.parse_args()
    os.chdir(ROOT)
    result=HERE/'results/C4_bend_board_r3';restore=HERE/'results/UI_restored_after_bend_C4_r3.json'
    assert not result.exists() and not restore.exists()
    review=HERE/'results/bend_own_CT_ARM_r3_2'
    record=json.loads((review/'acceptance.json').read_text())
    assert record['platform']=='linux' and record['status']=='own_CT_Q5_Q6_nonzero_bend_original_prefix_policy_fresh_wall_curve_camera_passed'
    test=json.loads((HERE/'results/bend_numeric_policy_ARM_r3.json').read_text())
    assert test['status']=='new_surface_native_bend_numeric_and_original_prefix_policy_tests_passed'
    for source in (record['source_sha256'],test['source_sha256']):
        for n,d in source.items():assert SHA(ROOT/n)==d
    for case in record['cases']:
        assert SHA(review/case['arrays_file'])==case['arrays_sha256']
        for n,d in case['source_binding_sha256'].items():assert SHA(ROOT/n)==d
    sys.path.insert(0,str(ROOT/'dfx/route_audit_speed'))
    from audit_runtime import verify
    verify()  # No XRT session or signal in this preflight.
    reference=json.loads((ROOT/'dfx/route_audit/docs/arm_cpu_baseline.json').read_text())
    assert SHA(ROOT/reference['reference_library_archive'])==reference['reference_library_sha256']
    argv,pid=ui_binding()
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:stat=(proc/'stat').read_text()
        except (FileNotFoundError,ProcessLookupError):continue
        parent=int(stat[stat.rfind(')')+2:].split()[1])
        assert parent!=pid,'A GUI job is active; preserve it and defer independent PL trial'
    if args.check_only:
        print('R17, C4 firmware, own-mesh bindings and ARM geometry tests passed; no signal/PL access',flush=True)
        return
    started=HERE/'results/C4_bend_trial_started_r3.json';assert not started.exists()
    started.write_text(json.dumps(dict(status='source_bound_nonzero_bend_C4_comparison_starting',
        UI_PID=pid,boot_id=BOOT,descriptor_sha256=DESCRIPTOR_SHA,manual_entry_sha256=ENTRY_SHA,
        UI_binary_sha256=UI_SHA,wrapper_sha256=SHA(Path(__file__)),
        comparison_source_sha256=SHA(HERE/'compare_bend_board_r3.py'),
        review_sha256=SHA(review/'acceptance.json')),indent=2)+'\n')
    stopped=False;code=None;error=None
    try:
        assert ui_binding()==(argv,pid)
        os.kill(pid,signal.SIGTERM)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            try:current=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')[:-1]
            except (FileNotFoundError,ProcessLookupError):current=[]
            if current!=argv:stopped=True;break
            time.sleep(.1)
        assert stopped,'UI did not drain; no PL session started'
        with open('/tmp/kv260-ct-pl.lock','rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(lock,fcntl.LOCK_UN)
        code=subprocess.run([sys.executable,str(HERE/'compare_bend_board_r3.py'),
            '--review',str(review),'--output',str(result)],cwd=ROOT).returncode
    finally:
        if stopped:
            try:
                sys.path.insert(0,str(ROOT/'dfx/edt_volume'))
                from volume_runtime import VolumeSession
                with VolumeSession(experimental=False) as session:session.return_to_scope()
                with open('/tmp/kv260-ct-pl.lock','rb') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(lock,fcntl.LOCK_UN)
                assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT
                assert SHA(ROOT/'ui/active_release.json')==DESCRIPTOR_SHA and SHA(ROOT/'ui/run.sh')==ENTRY_SHA
                log=HERE/'results/UI_restored_after_bend_C4_r3.log';assert not log.exists()
                with log.open('xb') as out:
                    ui=subprocess.Popen(['bash','ui/run.sh'],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL,start_new_session=True)
                time.sleep(4);assert ui.poll() is None
                _,restored=ui_binding();assert restored==ui.pid
                receipt=dict(status='verified_R17_and_C6_restored_after_nonzero_bend_C4_comparison',
                    PID=restored,previous_UI_PID=pid,boot_id=BOOT,trial_exit_code=code,
                    UI_binary_sha256=UI_SHA,default_descriptor_sha256=DESCRIPTOR_SHA,
                    manual_entry_sha256=ENTRY_SHA,composite_worker_sha256=WORKER_SHA,
                    accepted_volume_lifecycle_and_C6_restore_passed=True,PL_lock_free_before_UI_launch=True,
                    static_shell_reloaded=False,ZOCL_unloaded=False,forced_kill_or_reset=False,
                    source_sha256={n:SHA(HERE/n) for n in ('with_bend_UI_restore_r3_2.py','compare_bend_board_r3.py')})
                restore.write_text(json.dumps(receipt,indent=2)+'\n')
                print(receipt['status'],restored,flush=True)
            except BaseException as exc:
                error=exc
                failure=HERE/'results/UI_restore_failure_bend_C4_r3.json';assert not failure.exists()
                failure.write_text(json.dumps(dict(status='restoration_requires_inspection_no_forced_recovery',
                    error=repr(exc),trial_exit_code=code),indent=2)+'\n')
    if error is not None:raise error
    assert code==0,'Comparison failed; accepted UI restored and failure retained'


if __name__=='__main__':main()
