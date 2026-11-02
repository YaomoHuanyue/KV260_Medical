"""Exercise the real candidate CLI without replacing or stopping the formal GUI."""
from pathlib import Path
import csv,fcntl,gzip,hashlib,json,os,re,subprocess,sys,threading,time,traceback
ROOT=Path(__file__).resolve().parents[3]


def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def read(p):return json.loads(Path(p).read_text())


def save(p,v):
    with Path(p).open('x',encoding='utf-8') as f:json.dump(v,f,indent=2,allow_nan=False)


def birth(pid):return int(Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19])


def main():
    work=Path(sys.argv[1]).resolve(strict=True)
    assert work.parent==ROOT/'results' and re.fullmatch('owned_streaming_backend_r1_[0-9a-f]{32}',work.name)
    plan=read(work/'plan.json');assert sha(Path(__file__))==plan['trial_SHA256']
    sys.path.insert(0,str(ROOT))
    from ui.releases.streaming_functional_r1.backend import snapshot_logs
    from modules.segmentation.axis_tensor_reader_r3.streaming_r1.entry import recover_pending
    inputs,reference,_=recover_pending()
    for n,h in plan['source_SHA256'].items():assert sha(ROOT/n)==h,n
    def identity():
        e=plan['formal_UI'];p=Path('/proc',str(e['PID']))
        fields=(p/'stat').read_text().rsplit(')',1)[1].split()
        value=dict(PID=e['PID'],ticks=int(fields[19]),boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            ELF=sha(p/'exe'),identity_SHA256=sha(ROOT/'tools/storage_runtime_identity.json'))
        assert fields[0]!='Z' and value==e
        return value
    def idle():
        for n in (ROOT/'ui/runs/.runner.lock',Path('/tmp/kv260-ct-pl.lock')):
            with n.open('rb') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    identity();idle()
    assert os.statvfs(work).f_bavail*os.statvfs(work).f_frsize>=1_500_000_000
    assert int(next(v.split()[1] for v in Path('/proc/meminfo').read_text().splitlines() if v.startswith('MemAvailable:')))*1024>=2*1024**3
    save(work/'started.json',dict(PID=os.getpid(),start_ticks=birth(os.getpid())))
    before=snapshot_logs();save(work/'global_CSV_before.json',before)
    samples=[];errors=[];stop=threading.Event();cases=[];owned_results=[];children=[];failure=None
    def monitor():
        while not stop.is_set():
            try:
                values={v[0].rstrip(':'):int(v[1])*1024 for v in (n.split() for n in Path('/proc/meminfo').read_text().splitlines()) if len(v)>2 and v[2]=='kB'}
                samples.append(dict(monotonic=time.monotonic(),MemAvailable=values['MemAvailable'],CmaFree=values.get('CmaFree')))
            except Exception as e:errors.append(repr(e))
            stop.wait(.5)
    sampler=threading.Thread(target=monitor,daemon=True);sampler.start()
    ct=ROOT/'fixtures/own_ct/CT-chest.nrrd'
    backend=ROOT/'ui/releases/streaming_reader_r1/backend.py'
    def command(label,arguments,expected_rc=0):
        identity();idle();start=time.perf_counter()
        argv=[sys.executable,'-B',str(backend),*arguments]
        with (work/(label+'.log')).open('xb') as log:
            child=subprocess.Popen(argv,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='2',ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS='2'))
            process=dict(PID=child.pid,start_ticks=birth(child.pid),argv=argv,label=label);children.append(process)
            save(work/(label+'_process.json'),process)
            rc=child.wait()  # Never terminate an owner which may still have DMA in flight.
        events=[]
        for line in (work/(label+'.log')).read_text(errors='replace').splitlines():
            try:item=json.loads(line)
            except json.JSONDecodeError:continue
            if isinstance(item,dict) and 'event' in item:events.append(item)
        outputs=[Path(e['output']) for e in events if e['event']=='started']
        for out in outputs:
            assert out.parent==ROOT/'ui/releases/streaming_reader_r1/runs' and out not in owned_results
            owned_results.append(out)
        save(work/'observed_processes.json.new',children);os.replace(work/'observed_processes.json.new',work/'observed_processes.json')
        save(work/'owned_results.json.new',[str(p) for p in owned_results]);os.replace(work/'owned_results.json.new',work/'owned_results.json')
        row=dict(label=label,exit_code=rc,expected_exit_code=expected_rc,seconds=time.perf_counter()-start,events=events,outputs=[str(p) for p in outputs])
        save(work/(label+'_exit.json'),row)
        assert rc==expected_rc,(label,rc)
        identity();idle();assert snapshot_logs()==before,'Existing or unretained global DFX CSV changed'
        assert not (ROOT/'modules/segmentation/axis_tensor_reader_r3/streaming_r1/pending_transaction.json').exists()
        assert sha(ROOT/'dfx/medical/release/medical_ct_partial.bin')==sha(Path('/lib/firmware/medical_ct_partial.bin'))==reference['old_partial_SHA256']
        cases.append(row)
        return outputs,events
    try:
        # These invoke the same CLI as the native UI, rather than mocked dispatch.
        out,events=command('missing_CT',['run','--input',str(work/'absent.nrrd')],1)
        assert not out and any(e['event']=='error' for e in events)
        out,events=command('missing_source',['run','--input',str(ct),'--mode','reconstruction'],1)
        assert not out and any(e['event']=='error' for e in events)
        cancel=work/'cancel_requested';cancel.write_text('cancel before the first stage\n')
        out,events=command('cancel_before_start',['run','--input',str(ct),'--stop-file',str(cancel)])
        assert len(out)==1
        stopped=read(out[0]/'pipeline.json');assert stopped['status']=='stopped' and not stopped['stages']
        assert not list(out[0].glob('*_process.json'))
        out,events=command('full139',['run','--input',str(ct)])
        assert len(out)==1;full=out[0];pipeline=read(full/'pipeline.json')
        assert pipeline['status']=='passed' and [r['stage'] for r in pipeline['stages']]==['segmentation','reconstruction','navigation']
        seg=read(full/'segmentation/report.json');mesh=read(full/'reconstruction/report.json')
        assert seg['actual_C5_sessions']==1 and not seg['qualification_only_probe_sessions_used']
        assert seg['pl_conv_calls']==2520 and seg['pl_pool_calls']==420 and seg['pl_reader_calls']==840 and seg['no_PS_pool_fallback']
        assert seg['repeat_raw_mask_sha256']==reference['expected_raw_masks']
        assert sha(full/'segmentation/airway_logits.npy')==reference['expected_logits_SHA256']
        assert mesh['mc_kernel']=='AXIS_D7' and mesh['smoothing_kernel']=='D9_AXIS'
        assert mesh['mesh_sha256']==reference['expected_mesh_SHA256']
        for name,h in reference['expected_mesh_SHA256'].items():assert sha(full/'reconstruction'/(name+'.npz'))==h
        for name,h in reference['expected_navigation_NPZ_SHA256'].items():assert sha(full/'navigation'/name)==h
        switches=read(full/'segmentation/dfx_audit/switches.json')
        assert len(switches['actual_logs'])==2 and sorted(v['records'][0]['rm'] for v in switches['actual_logs'])==['ct','hu']
        save(work/'full139_checked.json',dict(result=str(full),actual_single_C5_session=True,full_logits_masks_meshes_navigation_reference_exact=True,
            segmentation=seg,pipeline=pipeline,normal_path_without_qualification_probes=True,actual_R3_reader_840_calls_including_warmup=True))
        from modules.image_import.airway_probability_cleanup_r1.importer import import_bundle
        fixture=ROOT/'results/manual_acceptance_20261017/external_fixture/inputs/airway_probability_only.json'
        bundle=work/'partial_import';imported=import_bundle(ct,fixture,bundle)
        assert imported['declared_structures']==['airway']
        out,events=command('partial_probability',['run','--input',str(ct),'--mode','reconstruction','--result',str(bundle)])
        assert len(out)==1;partial=out[0];p=read(partial/'pipeline.json');r=read(partial/'reconstruction/report.json')
        assert p['status']=='passed' and p['available_structures']==['airway'] and p['unavailable_structures']==['lung','nodule']
        assert r['smoothing_kernel']=='D9_AXIS' and r['available_structures']==['airway']
        assert not (partial/'reconstruction/lung.npz').exists() and not (partial/'reconstruction/nodule.npz').exists()
        for n,h in imported['files'].items():assert sha(partial/n)==h,n
        save(work/'partial_probability_checked.json',dict(result=str(partial),all_imported_mask_and_probability_file_bytes_preserved=True,
            only_declared_airway_reconstructed_on_PL=True,report=r))
    except BaseException:
        failure=traceback.format_exc();save(work/'failure.json',dict(traceback=failure,completed_cases=[r['label'] for r in cases]))
    finally:
        stop.set();sampler.join();save(work/'memory_samples.json',dict(samples=samples,errors=errors))
        restored=False
        try:
            identity();idle();assert snapshot_logs()==before
            assert not (ROOT/'modules/segmentation/axis_tensor_reader_r3/streaming_r1/pending_transaction.json').exists()
            assert sha(ROOT/'dfx/medical/release/medical_ct_partial.bin')==sha(Path('/lib/firmware/medical_ct_partial.bin'))==reference['old_partial_SHA256']
            restored=True
        except BaseException:save(work/'restoration_failure.json',dict(traceback=traceback.format_exc()))
        save(work/'terminal.json',dict(complete=failure is None and restored and len(cases)==5,entry_child_terminal=True,failure=failure,
            cases=cases,formal_UI=identity(),original_firmware_and_global_CSV_exact=restored,production_promoted=False,whole_goal_completed=False))
    if failure:raise RuntimeError(failure)


if __name__=='__main__':main()
