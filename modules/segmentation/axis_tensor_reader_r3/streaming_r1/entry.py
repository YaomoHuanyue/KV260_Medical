"""General D6/C5-pool stage, with the complete qualified worker and durable restore."""
from contextlib import contextmanager
from pathlib import Path
import argparse,csv,fcntl,gc,hashlib,json,os,re,shutil,sys,time,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT))


def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def read(p):return json.loads(Path(p).read_text())


def save(p,value):
    with Path(p).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,allow_nan=False)


@contextmanager
def job_lock(inherited=None):
    path=ROOT/'ui/runs/.runner.lock'
    if inherited is None:
        with path.open('rb') as f:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);yield f.fileno()
    else:
        st=os.fstat(inherited);expected=path.stat()
        if (st.st_dev,st.st_ino)!=(expected.st_dev,expected.st_ino):raise ValueError('Inherited job lock is not the global medical task lock')
        fcntl.flock(inherited,fcntl.LOCK_EX|fcntl.LOCK_NB)
        # It is the parent's open-file description. Never unlock it here.
        yield inherited


@contextmanager
def idle_pl():
    with Path('/tmp/kv260-ct-pl.lock').open('rb') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);yield


def verify_qualification():
    path=HERE/'stage_inputs.json'
    if not path.is_file():raise RuntimeError('The integrated stage admission is not installed')
    inputs=read(path)
    protected=read(ROOT/'results/storage_cleanup_20261015/current_dependencies.json')
    if protected.get('kv260_system/'+path.relative_to(ROOT).as_posix())!=sha(path):raise RuntimeError('Unsealed stage admission')
    if inputs.get('schema')!='kv260.streaming.R3_reader.general_stage.v1':raise ValueError('Wrong general-stage admission')
    for n,h in inputs['source_SHA256'].items():
        p=(ROOT/n).resolve()
        if not p.is_relative_to(ROOT) or not p.is_file() or sha(p)!=h:raise ValueError('Changed general-stage source: '+n)
    roles=inputs['proofs']
    if set(roles)!={'actual_full139_system','actual_partial7_system','file_transaction_windows','file_transaction_ARM'}:
        raise ValueError('Complete actual system and recovery qualification required')
    proofs={}
    for role,row in roles.items():
        p=(ROOT/row['path']).resolve()
        if not p.is_relative_to(ROOT) or not p.is_file() or sha(p)!=row['SHA256']:raise ValueError('Changed stage proof: '+role)
        proofs[role]=read(p)
    full=proofs['actual_full139_system'];partial=proofs['actual_partial7_system'];files=proofs['file_transaction_windows'];arm_files=proofs['file_transaction_ARM']
    if not (full['all139_original_CT_and_five_full_masks_logits_three_meshes_and_four_navigation_arrays_exact'] and
        full['actual_same_process_three_C5_sessions_with_unique_logs_and_fixed_name_preserved'] and
        partial['actual7_partial_cases14_reconstruction_processes_independently_verified'] and
        files['actual_process_exit_between_two_file_swaps_and_recovery_passed'] and
        arm_files['actual_process_exit_between_two_file_swaps_and_recovery_passed'] and
        len(files['cases'])==len(arm_files['cases'])==9 and arm_files['host']=='linux'):
        raise RuntimeError('Actual complete functional qualification missing')
    from modules.segmentation.axis_tensor_reader_r3.streaming_r1 import functional as qualified
    # The immutable template is itself pinned above. Its formal firmware
    # targets can still contain a dead owner's candidate, so defer their
    # full original-state check until after durable file recovery.
    record=read(ROOT/inputs['qualified_template'])
    if sha(ROOT/inputs['original_asset'])!=record['old_partial_SHA256']:raise ValueError('Original recovery asset changed')
    return inputs,record,qualified


def transaction(inputs,record):
    from system.partial_transaction_r1 import Transaction
    return Transaction(HERE/'pending_transaction.json',
        [ROOT/'dfx/medical/release/medical_ct_partial.bin',Path('/lib/firmware/medical_ct_partial.bin')],
        ROOT/inputs['original_asset'],ROOT/record['pool_partial'],record['old_partial_SHA256'],record['new_partial_SHA256'])


def recover_pending():
    inputs,record,qualified=verify_qualification();tx=transaction(inputs,record)
    if tx.ledger.exists():
        with job_lock():
            with idle_pl():tx.restore(abandoned=True)
    assert qualified.verify(ROOT/inputs['qualified_template'])==record
    return inputs,record,qualified


def run(args):
    inputs,record,qualified=verify_qualification();qualified.configure_imports()
    tx=transaction(inputs,record)
    args.input=args.input.resolve(strict=True);args.output=args.output.resolve()
    if args.reference_dir:args.reference_dir=args.reference_dir.resolve(strict=True)
    if args.repeats<1:raise ValueError('Positive repeats required')
    if not args.output.is_relative_to(ROOT) or args.output.exists() or not args.output.parent.is_dir():
        raise ValueError('Fresh output inside this project with an existing parent required')
    args.model_dir=ROOT/'modules/segmentation/outputs/ct_accuracy_v2/pl_model'
    args.scheduler='fused';args.slice_workers=2;args.save_airway_logits=True;args.no_preview=not args.preview
    os.environ.setdefault('CT_PL_WAIT_MODE','adaptive');os.environ.setdefault('CT_PL_CLEAN_BO','1')
    with job_lock(args.job_lock_fd):
        with idle_pl():recovery=tx.restore(abandoned=True)
        assert qualified.verify(ROOT/inputs['qualified_template'])==record
        args.output.mkdir();audit=args.output/'dfx_audit';audit.mkdir()
        save(audit/'admission.json',dict(qualified_inputs_SHA256=sha(HERE/'stage_inputs.json'),
            actual_input_SHA256=sha(args.input),recovered_previous_transaction=recovery,
            functional_candidate_only=True,performance_qualification_pending=True,all_operators_on_PL=False,
            qualification_only_probe_sessions_used=False))
        patterns=('dfx/medical/results/switches_extended_*.csv','modules/ct_preprocess/axis_hu_32_r2/host_r1/results/switch*.csv')
        previous={p.relative_to(ROOT).as_posix():sha(p) for pattern in patterns for p in ROOT.glob(pattern)}
        original_cwd=Path.cwd();failure=None;prepared=None;instances=[];report=None
        from modules.segmentation.axis_tensor_reader_r3.host_r1 import backend as pool_module
        base=pool_module.ReaderXRT
        class TrackedPool(base):
            def __init__(self,*a,**kw):
                instances.append(self);super().__init__(*a,**kw)
        pool_module.ReaderXRT=TrackedPool
        started=time.perf_counter()
        try:
            from modules.ct_preprocess.axis_hu_32_r2.bounded_volume_r3.runtime import prepare_ct
            prepared=prepare_ct(args)
            with idle_pl():save(audit/'transaction.json',tx.begin())
            os.chdir(ROOT/'dfx/medical')
            report=qualified.run_worker(args,prepared,record)
        except BaseException as error:
            failure=traceback.format_exc()
            # The original worker closes normal inference in its own finally.
            # Clear exception frames before GC so NumPy BO leases can drain too.
            error.__traceback__=None;error.__context__=None;error.__cause__=None
        finally:
            pool_module.ReaderXRT=base
            for instance in instances:
                if getattr(instance,'handle',None):base.close(instance)
            instances.clear();prepared=None;gc.collect();os.chdir(original_cwd)
            try:
                with idle_pl():restored=tx.restore()
                save(audit/'restored.json',restored)
            except BaseException:
                save(audit/'restoration_failure.json',dict(traceback=traceback.format_exc(),pending_ledger=str(tx.ledger)))
                if failure is None:failure='Qualified firmware restore failed; pending transaction retained'
            try:
                if any(sha(ROOT/n)!=h for n,h in previous.items()):raise RuntimeError('An existing DFX log changed')
                owned=[]
                for pattern in patterns:
                    for p in ROOT.glob(pattern):
                        n=p.relative_to(ROOT).as_posix()
                        if n in previous or not re.search('_'+str(os.getpid())+r'\.csv$',n):continue
                        h=sha(p);target=audit/p.name;shutil.copyfile(p,target)
                        if sha(target)!=h:raise RuntimeError('Stage DFX log copy changed')
                        rows=list(csv.DictReader(target.open()))
                        owned.append(dict(original_path=n,file=target.name,SHA256=h,records=rows))
                if failure is None:
                    if len(owned)!=2 or sorted(r['records'][0]['rm'] for r in owned)!=['ct','hu'] or any(len(r['records'])!=1 for r in owned):
                        raise RuntimeError('One actual D6 and one actual C5 session required')
                save(audit/'switches.json',dict(actual_logs=owned,unique_C5_session=True,no_fixed_log_overwrite=True))
                for row in owned:
                    p=ROOT/row['original_path']
                    if sha(p)!=row['SHA256']:raise RuntimeError('Owned log changed after close')
                    p.unlink()  # Only this closed native session's log, retained above.
            except BaseException:
                save(audit/'log_collection_failure.json',dict(traceback=traceback.format_exc()))
                if failure is None:failure='Closed stage DFX log retention failed'
        if failure is not None:
            save(audit/'failure.json',dict(traceback=failure,whole_goal_completed=False))
            (args.output/'status.json').write_text(json.dumps(dict(status='failed',error=failure,pid=os.getpid())))
            raise RuntimeError(failure)
        report.update(general_streaming_stage=True,dfx_audit_directory='dfx_audit',
            stage_wall_seconds=time.perf_counter()-started,qualified_original_firmware_restored=True,
            actual_C5_sessions=1,qualification_only_probe_sessions_used=False)
        (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(dict(status='completed',general_streaming_stage=True,PL_conv_calls=report['pl_conv_calls'],
            PL_pool_calls=report['pl_pool_calls'],original_firmware_restored=True)),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--repeats',type=int,default=1);p.add_argument('--reference-dir',type=Path);p.add_argument('--preview',action='store_true')
    p.add_argument('--job-lock-fd',type=int);run(p.parse_args())


if __name__=='__main__':main()
