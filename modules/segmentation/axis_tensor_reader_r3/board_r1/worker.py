"""Owned full139 trial with durable firmware restoration and cooperative locks."""
from contextlib import contextmanager
from pathlib import Path
import fcntl,hashlib,json,os,pwd,shutil,subprocess,sys,time,traceback
HERE=Path(__file__).resolve().parent
WORK=Path(sys.argv[1]).resolve()
PLAN=json.loads((WORK/'plan.json').read_text())
ROOT=Path(PLAN['root']);sys.path.insert(0,str(ROOT))
from system.partial_transaction_r1 import Transaction

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def save(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,indent=2)

def identity():
    e=PLAN['formal'];p=Path('/proc',str(e['PID']))
    a=dict(PID=e['PID'],ticks=int((p/'stat').read_text().rsplit(')',1)[1].split()[19]),
        boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),ELF=sha(p/'exe'),
        identity_SHA256=sha(ROOT/'tools/storage_runtime_identity.json'))
    assert a==e,('Formal UI changed',a)
    return a

@contextmanager
def idle():
    with open('/tmp/kv260-ct-pl.lock','rb') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);yield

def check_inputs():
    for n,h in PLAN['inputs'].items():
        p=(ROOT/n).resolve();assert p.is_relative_to(ROOT) and not p.is_symlink() and sha(p)==h,n
    assert Path('/run/kv260-dfx-medical-loaded.sha256').read_text().strip()==PLAN['static_SHA256']
    assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='operating'
    identity()

def child(argv,name):
    with (WORK/(name+'.log')).open('xb') as log:
        p=subprocess.Popen(argv,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',
                ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS='1',CT_PL_WAIT_MODE='adaptive',CT_PL_CLEAN_BO='1'))
        ticks=int(Path('/proc',str(p.pid),'stat').read_text().rsplit(')',1)[1].split()[19])
        save(WORK/(name+'_process.json'),dict(PID=p.pid,start_ticks=ticks,argv=argv))
        # Never terminate a possible DMA owner because an observer times out.
        rc=p.wait()
    save(WORK/(name+'_exit.json'),dict(exit_code=rc,child_terminal=True))
    assert rc==0,(name,rc)
    return p.pid

def lifecycle(name):
    code="""from pathlib import Path
import os,sys
root=Path(ROOT_VALUE);os.environ['OPENBLAS_NUM_THREADS']='1'
sys.path[:0]=[str(root/'dfx/edt_volume')]
from volume_runtime import VolumeSession
with VolumeSession(experimental=False) as s:s.return_to_scope()
""".replace('ROOT_VALUE',repr(str(ROOT)))
    return child([str(ROOT/'.venv/bin/python'),'-B','-c',code],name)

def copy_known(src,dst,expected):
    assert dst.is_file() and not dst.is_symlink() and sha(dst)==expected
    temp=dst.with_name(dst.name+'.owned_tensor_R3_'+WORK.name.rsplit('_',1)[-1]);assert not temp.exists()
    st=dst.stat()
    with src.open('rb') as a,temp.open('xb') as b:shutil.copyfileobj(a,b,1048576);b.flush();os.fsync(b.fileno())
    os.chmod(temp,st.st_mode&0o7777);os.chown(temp,st.st_uid,st.st_gid)
    assert sha(temp)==sha(src) and sha(dst)==expected
    os.replace(temp,dst)

def run():
    assert WORK.parent==ROOT/'results' and WORK.name.startswith('owned_tensor_R3_board_r1_')
    start=time.monotonic();failed=None;restored=False;full=None;global_before={};new_logs={}
    tx=Transaction(WORK/'pending_firmware.json',
        [ROOT/'dfx/medical/release/medical_ct_partial.bin',Path('/lib/firmware/medical_ct_partial.bin')],
        ROOT/PLAN['original_asset'],ROOT/PLAN['candidate'],PLAN['old_partial_SHA256'],PLAN['new_partial_SHA256'])
    with (ROOT/'ui/runs/.runner.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        check_inputs()
        with idle():
            assert not tx.ledger.exists();tx.validate_assets()
            for p in tx.targets:assert sha(p)==PLAN['old_partial_SHA256']
        assert int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024>=1536*1024**2
        backup=WORK/'backups';backup.mkdir()
        for p in (ROOT/'dfx').glob('*/results/*.csv'):
            n=p.relative_to(ROOT).as_posix();global_before[n]=sha(p)
        save(WORK/'global_logs_before.json',global_before)
        maps=ROOT/'results/storage_cleanup_20261015/current_dependencies.json'
        old_map_sha=sha(maps);shutil.copyfile(maps,backup/'current_dependencies.json')
        before=json.loads(maps.read_text());after=dict(before)
        for n,h in PLAN['inputs'].items():
            k='kv260_system/'+n
            assert after.get(k) in (None,h),('Different existing dependency',n)
            after[k]=h
        added=WORK/'trial_dependencies.json';save(added,after)
        map_changed=False;known_c8=[]
        try:
            copy_known(added,maps,old_map_sha);map_changed=True
            known_c8.append(lifecycle('prepare_return_scope'))
            with idle():
                check_inputs();tx.begin()
            save(WORK/'temporary_install.json',dict(old_SHA256=tx.old_sha,new_SHA256=tx.new_sha,
                exact_candidate_both_files=True,formal=identity(),static_reloaded=False))
            argv=[str(ROOT/'.venv/bin/python'),'-B',str(HERE/'run_full139.py'),
                '--admission',str(HERE.parent/'host_r1/admission.json'),'--library',str(ROOT/PLAN['library']),
                '--output',str(WORK/'full139')]
            pid=child(argv,'full139')
            full=json.loads((WORK/'full139/verified.json').read_text())
            assert full['all139_completed'] and full['actual_PL_convolution_calls']==2502 and full['actual_PL_pool_calls']==417 and full['actual_PL_reader_transform_calls']==834
            assert full['all2502_input_SHA256_and139_full_float32_logit_SHA256_exact']
        except BaseException:
            failed=traceback.format_exc();save(WORK/'failure.json',dict(traceback=failed,whole_goal_completed=False))
        finally:
            try:
                with idle():recovery=tx.restore()
                known_c8.append(lifecycle('restore_return_scope'))
                # Only collect/delete new logs with a proven owned child PID.
                pids=[json.loads(p.read_text())['PID'] for p in WORK.glob('*_process.json')]
                logdir=WORK/'owned_logs';logdir.mkdir()
                for p in (ROOT/'dfx').glob('*/results/*.csv'):
                    n=p.relative_to(ROOT).as_posix();h=sha(p)
                    if n in global_before:
                        assert h==global_before[n],('Existing log changed; preserve it',n)
                        continue
                    own=any(p.name==f'switches_{pid}.csv' or p.name.endswith(f'_{pid}.csv') for pid in pids)
                    if not own:continue
                    dest=logdir/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
                    assert sha(dest)==h and sha(p)==h;p.unlink();new_logs[n]=h
                for n,h in global_before.items():assert sha(ROOT/n)==h,n
                if map_changed:copy_known(backup/'current_dependencies.json',maps,sha(added))
                assert sha(maps)==old_map_sha
                with idle():
                    assert not tx.ledger.exists()
                    for p in tx.targets:assert sha(p)==tx.old_sha
                check_inputs();restored=True
                save(WORK/'restored.json',dict(original_firmware_pair_and_dependency_map_exact=True,
                    original_global_logs_unchanged=True,only_proven_owned_new_logs_collected=new_logs,
                    firmware_transaction=recovery,formal=identity(),accepted_C8_return_to_C6=True,
                    no_driver_unload_static_reload_reset_or_forced_PL_release=True))
            except BaseException:
                save(WORK/'restoration_failure.json',dict(traceback=traceback.format_exc(),whole_goal_completed=False))
    save(WORK/'terminal.json',dict(passed=failed is None and restored and full is not None,
        full139_actual_passed=full is not None,originals_restored=restored,elapsed_seconds=time.monotonic()-start,
        production_promoted=False,new_R3_reader_in_this_bit=True,whole_goal_completed=False))

if __name__=='__main__':
    try:run()
    finally:
        u=pwd.getpwnam('ubuntu')
        for p in WORK.rglob('*'):os.chown(p,u.pw_uid,u.pw_gid)
