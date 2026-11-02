"""Owned functional full-system trial; reuse qualified PL, restore exact firmware.

This is an explicitly slower candidate, not a replacement for the formal UI.
The normal PL and task mutexes remain authoritative; no owner is stopped.
"""
from pathlib import Path
from datetime import datetime,timezone
import fcntl,gc,hashlib,json,os,re,shutil,subprocess,sys,threading,time,traceback
ROOT=Path(__file__).resolve().parents[3]


def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,v):
    with Path(p).open('x',encoding='utf-8') as f:json.dump(v,f,indent=2,allow_nan=False)
def identity(expected):
    p=Path('/proc',str(expected['PID']));fields=(p/'stat').read_text().rsplit(')',1)[1].split()
    value=dict(PID=int(p.name),ticks=int(fields[19]),boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        ELF=sha(p/'exe'),identity_SHA256=sha(ROOT/'tools/storage_runtime_identity.json'))
    assert value==expected,('Formal UI identity changed',value)
    return value
def pl_lock():
    f=Path('/tmp/kv260-ct-pl.lock').open('rb')
    try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BaseException:f.close();raise
    return f
def replace(source,target,expected,tag):
    target=Path(target);assert target.is_file() and not target.is_symlink() and sha(target)==expected
    temporary=target.with_name(target.name+'.owned_streaming_'+tag)
    assert not temporary.exists();st=target.stat()
    with Path(source).open('rb') as src,temporary.open('xb') as dst:
        shutil.copyfileobj(src,dst,1048576);dst.flush();os.fsync(dst.fileno())
    os.chmod(temporary,st.st_mode&0o7777);os.chown(temporary,st.st_uid,st.st_gid)
    assert sha(temporary)==sha(source);os.replace(temporary,target)


def run(args,record,worker):
    work=args.output.parent
    assert work.resolve()==work and work.parent==ROOT/'results' and not work.is_symlink()
    assert re.fullmatch('owned_streaming_functional_r1_[0-9a-f]{32}',work.name)
    assert args.output==work/'segmentation' and not (work/'terminal.json').exists()
    assert read(work/'plan.json')==record and sha(Path(__file__))==record['coordinator']['SHA256']
    before=identity(record['formal_UI'])
    sys.path.insert(0,str(ROOT))
    from modules.ct_preprocess.axis_hu_32_r2.bounded_volume_r3.entry_r1 import verify_qualification
    verify_qualification()
    from modules.ct_preprocess.axis_hu_32_r2.bounded_volume_r3.runtime import prepare_ct
    partials=[ROOT/'dfx/medical/release/medical_ct_partial.bin',Path('/lib/firmware/medical_ct_partial.bin')]
    candidate=ROOT/record['pool_partial'];old,new=record['old_partial_SHA256'],record['new_partial_SHA256']
    assert sha(candidate)==new and all(sha(p)==old for p in partials)
    assert Path('/run/kv260-dfx-medical-loaded.sha256').read_text().strip()==record['static_SHA256']
    assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='operating'
    mem=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
    assert mem>=2*1024**3 and os.statvfs(work).f_bavail*os.statvfs(work).f_frsize>=1500_000_000
    samples=[];stages=[];children=[];stop=threading.Event();errors=[]
    def monitor():
        while not stop.is_set():
            try:
                memory={a[0].rstrip(':'):int(a[1])*1024 for a in (line.split() for line in Path('/proc/meminfo').read_text().splitlines()) if len(a)>2 and a[2]=='kB'}
                samples.append(dict(monotonic=time.monotonic(),MemAvailable=memory['MemAvailable'],CmaFree=memory.get('CmaFree')))
            except Exception as e:errors.append(repr(e))
            stop.wait(.5)
    def command(argv,label):
        identity(before);started=time.perf_counter()
        with (work/(label+'.log')).open('xb') as log:
            child=subprocess.Popen(argv,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='2',ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS='2'))
            ticks=int(Path('/proc',str(child.pid),'stat').read_text().rsplit(')',1)[1].split()[19])
            row=dict(PID=child.pid,start_ticks=ticks,argv=argv,label=label);children.append(row)
            save(work/(label+'_process.json'),row)
            rc=child.wait() # Never time out or kill a possibly active DMA owner.
        save(work/(label+'_exit.json'),dict(exit_code=rc,wall_seconds=time.perf_counter()-started))
        assert rc==0,(label,rc)
        return time.perf_counter()-started
    installed=[];failure=None;restored=False;fixed=ROOT/'dfx/medical/results/switches_extended.csv'
    original_csv=None;known_trial_csv=None;external=[];all_csv_before={}
    with (ROOT/'ui/runs/.runner.lock').open('rb') as formal_job:
        fcntl.flock(formal_job,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pl_lock():pass
        for pattern in ('dfx/*/results/switch*.csv','modules/ct_preprocess/axis_hu_32_r2/host_r1/results/switch*.csv','modules/reconstruction/axis_mc_8_r2/host_pooled_r2/results/switch*.csv'):
            for p in ROOT.glob(pattern):all_csv_before[p.relative_to(ROOT).as_posix()]=sha(p)
        backup=work/'original_ct_partial.bin';shutil.copyfile(partials[0],backup);assert sha(backup)==old
        if fixed.exists():
            original_csv=sha(fixed);shutil.copyfile(fixed,work/'original_fixed_C5_log.csv')
        save(work/'global_CSV_before.json',all_csv_before)
        sampler=threading.Thread(target=monitor,daemon=True);sampler.start()
        try:
            args.output.mkdir();args.model_dir=ROOT/'modules/segmentation/outputs/ct_accuracy_v2/pl_model'
            args.scheduler='fused';args.slice_workers=2;args.save_airway_logits=True;args.no_preview=True;args.reference_dir=None;args.repeats=1
            os.environ.setdefault('CT_PL_WAIT_MODE','adaptive');os.environ.setdefault('CT_PL_CLEAN_BO','1')
            started=time.perf_counter();prepared=prepare_ct(args)
            # D6 is drained and closed; only the next qualified C5 partial changes.
            with pl_lock():
                for i,p in enumerate(partials):replace(candidate,p,old,'install'+str(i));installed.append(i)
            os.chdir(ROOT/'dfx/medical')
            try:
                report=worker(args,prepared,record)
                assert report['all_three_original_pools_on_PL'] and report['pl_pool_calls']==420 and report['pl_conv_calls']==2520
                assert report['PL_HU_preprocessing']['no_PS_quantization_or_fallback']
                assert report['airway_logits']['sha256']==record['expected_logits_SHA256']
                assert report['repeat_raw_mask_sha256']==record['expected_raw_masks']
            finally:
                gc.collect()
                with pl_lock():
                    for i in installed:replace(backup,partials[i],new,'restore'+str(i))
                installed.clear()
                if fixed.exists():
                    known_trial_csv=sha(fixed);shutil.copyfile(fixed,work/'actual_C5_switches.csv')
            stages.append(dict(stage='segmentation',wall_seconds=time.perf_counter()-started,real_PL_conv_calls=2520,real_PL_pool_calls=420))
            recon=ROOT/'modules/reconstruction/axis_mc_8_r2/integrated_pooled_r3/run_reconstruction.py'
            elapsed=command([sys.executable,'-B',str(recon),'--ct',str(args.input),'--mask-dir',str(args.output),'--output',str(work/'reconstruction')],'reconstruction')
            mesh=read(work/'reconstruction/report.json');assert mesh['mesh_sha256']==record['expected_mesh_SHA256']
            assert mesh['mc_kernel']=='AXIS_D7' and mesh['smoothing_kernel']=='FMA2'
            stages.append(dict(stage='reconstruction',wall_seconds=elapsed))
            nav=ROOT/'ui/releases/feature_completion_r6/navigation_task_r6.py'
            elapsed=command([sys.executable,'-B',str(nav),'--airway',str(args.output/'airway_mask.nii.gz'),'--lesion',str(args.output/'nodule_mask.nii.gz'),
                '--lesion-index','0','--scope-diameter-mm','1.0','--safety-margin-mm','0.2','--minimum-bend-radius-mm','0.0','--output',str(work/'navigation')],'navigation')
            for name,digest in record['expected_navigation_NPZ_SHA256'].items():assert sha(work/'navigation'/name)==digest,name
            stages.append(dict(stage='navigation',wall_seconds=elapsed))
            lifecycle="from pathlib import Path;import sys;sys.path.insert(0,"+repr(str(ROOT/'dfx/edt_volume'))+");from volume_runtime import VolumeSession\nwith VolumeSession(experimental=False) as session:session.return_to_scope()"
            command([sys.executable,'-B','-c',lifecycle],'return_scope')
        except BaseException:
            failure=traceback.format_exc();save(work/'failure.json',dict(traceback=failure,completed_stages=stages,whole_goal_completed=False))
        finally:
            # Persist diagnostics even when a later guard rejects the whole trial.
            stop.set();sampler.join();save(work/'memory_samples.json',dict(samples=samples,monitor_errors=errors))
            save(work/'observed_processes.json',children)
            try:
                with pl_lock():
                    for i in installed:replace(backup,partials[i],new,'final_restore'+str(i))
                installed.clear()
                if known_trial_csv is not None and original_csv is not None:
                    assert sha(fixed)==known_trial_csv
                    replace(work/'original_fixed_C5_log.csv',fixed,known_trial_csv,'log_restore')
                owners={os.getpid()}|{r['PID'] for r in children}
                for pattern in ('dfx/*/results/switch*.csv','modules/ct_preprocess/axis_hu_32_r2/host_r1/results/switch*.csv','modules/reconstruction/axis_mc_8_r2/host_pooled_r2/results/switch*.csv'):
                    for p in ROOT.glob(pattern):
                        name=p.relative_to(ROOT).as_posix()
                        if name in all_csv_before:continue
                        match=re.search(r'_(\d+)\.csv$',p.name)
                        if not match or int(match[1]) not in owners:continue
                        dest=work/'external_csv'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
                        external.append(dict(path=name,SHA256=sha(p),bytes=p.stat().st_size,PID=int(match[1])))
                save(work/'external_owned_outputs.json',external)
                assert all(sha(ROOT/n)==h for n,h in all_csv_before.items()),'Existing global logs changed'
                assert all(sha(p)==old for p in partials)
                assert identity(before)==before and not errors
                save(work/'restored.json',dict(original_partials_and_fixed_CSV_bytes_exact=True,formal_UI_identity_unchanged=before,
                    no_reset_driver_unload_static_reload_or_forced_PL_release=True))
                restored=True
            except BaseException:save(work/'restoration_failure.json',dict(traceback=traceback.format_exc(),whole_goal_completed=False))
    if failure is None and restored and len(stages)==3:
        save(work/'complete.json',dict(UTC=datetime.now(timezone.utc).isoformat(),functional_candidate_only=True,
            actual_D6_HU32_C5_18conv_threePLpools_D7_MC_FMA2_C8_R14_full_system_passed=True,
            actual_original139_CT_masks_logits_meshes_routes_and_cameras_exact=True,stages=stages,
            all_operators_on_PL=False,known_network_speed_regression_retained=True,performance_qualification_pending=True,
            memory_samples=len(samples),minimum_MemAvailable_bytes=min(r['MemAvailable'] for r in samples),
            minimum_CmaFree_bytes=min(r['CmaFree'] for r in samples if r['CmaFree'] is not None),
            formal_UI_not_replaced=True,whole_goal_completed=False))
    save(work/'terminal.json',dict(complete=(work/'complete.json').exists(),failure=failure is not None,
        original_files_restored=restored,all_direct_children_terminal=True,ended_ns=time.time_ns()))
    if failure or not restored:raise RuntimeError('Functional candidate failed; owned diagnostics preserved')
