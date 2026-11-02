"""Q15 candidate entry with the original stage transaction and worker lifecycle."""
from pathlib import Path
from types import SimpleNamespace
import argparse,ast,hashlib,inspect,json,os,sys,time

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'modules/segmentation'),str(ROOT/'dfx/medical')]
from modules.segmentation.reader_burst.admission import load,need


def configured(certificate):
    from modules.segmentation.axis_tensor_reader_r3.streaming_r1 import entry as stage,functional
    from modules.segmentation.reader_burst.worker import run_worker
    source=inspect.getsource(stage.run)
    before="qualified_inputs_SHA256=sha(HERE/'stage_inputs.json')"
    after='qualified_inputs_SHA256=_reader_certificate_SHA256'
    need(source.count(before)==1,'Original stage audit boundary changed')
    selected=source.replace(before,after)
    need(selected.replace(after,before)==source,'Stage audit derivation is not reversible');ast.parse(selected)
    qualified=SimpleNamespace(configure_imports=functional.configure_imports,
        verify=certificate.verify_original,run_worker=run_worker)
    def qualification():
        certificate.check_unchanged()
        return certificate.stage_inputs(),certificate.stage_record(),qualified
    namespace=dict(vars(stage),verify_qualification=qualification,_reader_certificate_SHA256=certificate.digest)
    exec(compile(selected,str(Path(__file__))+':original_stage_with_runtime_certificate','exec'),namespace)
    derivation=dict(parent_stage_function_SHA256=hashlib.sha256(source.encode()).hexdigest(),
        selected_stage_function_SHA256=hashlib.sha256(selected.encode()).hexdigest(),
        literal_edit=[before,after],reverse_exact=True,original_transaction_and_tracker_body_preserved=True)
    return stage,namespace['run'],derivation


def require_arm():
    need(sys.platform=='linux'and os.uname().machine=='aarch64'and os.geteuid()==0,'Actual ARM/root stage required')


def save(path,value):
    path=Path(path);tmp=path.with_name(path.name+'.reader.new')
    need(not tmp.exists(),'Previous candidate metadata write is unfinished')
    with tmp.open('x',encoding='utf-8')as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
    tmp.replace(path)


def run(args):
    require_arm()
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    certificate=load(args.admission,args.admission_sha256)
    stage,original_run,derivation=configured(certificate)
    need(not(stage.HERE/'pending_transaction.json').exists(),'Use explicit same-candidate recover before starting a new stage')
    need(1<=args.repeats<=5,'Repeats outside1..5')
    from modules.segmentation.reader_burst.native import bind_reader
    started=time.perf_counter()
    with bind_reader(certificate):original_run(args)
    certificate.require_pair(False)
    need(not(stage.HERE/'pending_transaction.json').exists(),'Firmware transaction remains pending')
    post_seconds=certificate.verify_all()
    report=json.loads((args.output/'report.json').read_text())
    report['reader_burst_runtime']=dict(certificate_SHA256=certificate.digest,
        source_verification_bytes=certificate.verified_bytes,initial_verification_seconds=certificate.load_seconds,
        postflight_source_hash_seconds=post_seconds,entry_seconds=time.perf_counter()-started,
        compiler_archives_replayed_at_runtime=False,postflight_passed=True,
        transaction_derivation=derivation,production_promoted=False)
    save(args.output/'report.json',report)
    save(args.output/'reader_runtime.json',report['reader_burst_runtime'])
    return report


def recover(args):
    require_arm();certificate=load(args.admission,args.admission_sha256)
    stage,_,_=configured(certificate)
    tx=stage.transaction(certificate.stage_inputs(),certificate.stage_record())
    with stage.job_lock():
        with stage.idle_pl():
            pending=tx.ledger.exists()
            if pending:result=tx.restore(abandoned=True)
            else:
                tx.validate_assets(original_only=True);result=None
            certificate.require_pair(False);certificate.verify_all()
    return dict(pending_found=pending,restored=result,no_pending_transaction=not tx.ledger.exists(),
        original_pair_verified=True,PL_loaded=False,XRT_opened=False,
        scope='Same-candidate file transaction recovery; no device or in-flight DMA reset')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',nargs='?',default='run',choices=('run','recover','verify'))
    p.add_argument('--admission',type=Path,required=True);p.add_argument('--admission-sha256',required=True)
    p.add_argument('--input',type=Path);p.add_argument('--output',type=Path);p.add_argument('--repeats',type=int,default=1)
    p.add_argument('--job-lock-fd',type=int);p.add_argument('--reference-dir',type=Path);p.add_argument('--preview',action='store_true')
    args=p.parse_args()
    if args.action=='verify':
        require_arm();c=load(args.admission,args.admission_sha256)
        result=dict(runtime_verified=True,certificate_SHA256=c.digest,PL_accessed=False)
    elif args.action=='recover':result=recover(args)
    else:
        need(args.input is not None and args.output is not None,'Input and fresh output required')
        result=run(args)
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
