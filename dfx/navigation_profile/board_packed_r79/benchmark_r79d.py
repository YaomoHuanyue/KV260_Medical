"""Full original CT PS1/PS4/R7 comparison; contract mode is explicitly no XRT."""
from pathlib import Path
import argparse,ctypes as C,json,os,statistics,sys,time
if os.name != "nt":import resource
import numpy as np
import SimpleITK as sitk
from scipy.spatial import cKDTree
from release import HERE,PROFILE,ROOT,RELEASE,SHA,READ,verify,published_preflight,host_proofs
CPU=ROOT/'modules/navigation_comparison'
sys.path.insert(0,str(CPU));sys.path.insert(0,str(PROFILE/'host_packed_r7'));sys.path.insert(0,str(PROFILE/'output_pack_r7'))
from profile_r1 import graph,report
from profile_session_r2 import ProfilePS
from test_profile_r1 import compare_reports
import legacy_profile_r1 as legacy
import runtime as packed_runtime
from protocol import Native,pack_original
from check_full import verify_fixtures
from answer_trace import Trace
PROVIDERS=(1,'PL_sleep20',4,'PL_spin200','PL_spin2000')
PHASES=('BO_capacity_growth','full_input_output_and_guard_setup_sync','partial_load','complete_DFX_switch','hardware',
    'full_readback_and_four_full_guards','mapped_full_validation_and_packed_decode','native_host_total')
def exact(a,b):assert a.shape==b.shape and a.dtype==b.dtype and a.tobytes()==b.tobytes()
def preparation():
    host='Windows' if os.name=='nt' else 'ARM';host_bindings=host_proofs();verify_fixtures()
    for name in ['profile_'+host+'_r1.json','profile_all_nodes_'+host+'_r2.json','profile_session_'+host+'_r2.json']:
        proof=READ(CPU/'results'/name)
        for n,h in proof['source_sha256'].items():assert SHA(CPU/n)==h,n
    original=READ(CPU/'results'/('profile_'+host+'_r1.json'))
    library=CPU/'build'/('profile_ps_r1.dll' if host=='Windows' else 'libprofile_ps_r1.so')
    assert SHA(library)==original['library_sha256']
    full=READ(CPU/'results'/('profile_all_nodes_'+host+'_r2.json'));fixture=CPU/'fixtures'/('own_CT_full_raw_graph_'+host+'_r2.npz')
    assert SHA(fixture)==full['fixture_sha256']
    with np.load(fixture,allow_pickle=False) as f:
        data=graph(f['coordinates_zyx'],f['radii_mm'],int(f['root']),f['spacing_zyx'])
        diameters=f['diameters'].copy();wanted_d=f['expected_distances'].copy();wanted_p=f['expected_parent_ids'].copy()
    source_folder=ROOT/'ui/releases/feature_completion_r4/runs/seed_own_CT/navigation'
    for n,h in original['own_CT']['source_sha256'].items():assert SHA(ROOT/n)==h,n
    sys.path.insert(0,str(ROOT/'modules/navigation'))
    from navigation.pipeline import load_prepared,choose_target
    context=load_prepared(source_folder)
    target=choose_target(context,lesion_path=source_folder.parent/'segmentation/nodule_mask.nii.gz',lesion_index=3)
    assert target.metadata['mask_sha256']==original['own_CT']['target_mask_sha256']
    image=sitk.Image(list(map(int,context.mask.shape[::-1])),sitk.sitkUInt8)
    image.SetSpacing(tuple(context.geometry.spacing_xyz));image.SetDirection(tuple(context.geometry.direction))
    image.SetOrigin(tuple(context.geometry.to_lps(np.asarray(context.offset_zyx).reshape(1,3))[0]))
    tree=cKDTree(target.points_lps_mm)
    paths=[fixture,library,CPU/'profile_session_r2.py',CPU/'profile_r1.py',CPU/'legacy_profile_r1.py',CPU/'test_profile_r1.py',Path(__file__),HERE/'release.py']
    sources={p.relative_to(ROOT).as_posix():SHA(p) for p in paths};sources.update(original['own_CT']['source_sha256']);sources.update(host_bindings)
    sources[Path(packed_runtime.__file__).relative_to(ROOT).as_posix()]=SHA(Path(packed_runtime.__file__))
    return dict(host=host,data=data,diameters=diameters,wanted_d=wanted_d,wanted_p=wanted_p,image=image,tree=tree,
        expected_report=original['own_CT']['profiles'],context=context,fixture_sha256=SHA(fixture),sources=sources)
class BoardSession(packed_runtime.Session):
    def raw(self,data,operation):
        assert self.handle;data=np.ascontiguousarray(data,np.uint64);assert data.ndim==2 and data.shape[1]==8
        target=np.empty((2178,8),np.uint64);status=C.c_uint32();phases=(C.c_double*10)()
        call=self.library.profile_transfer_raw_r7;call.argtypes=[C.c_void_p]*3+[C.c_uint]*2+[C.c_void_p]*2;call.restype=C.c_int
        self.restored=False
        code=call(self.handle,data.ctypes.data,target.ctypes.data,len(data),operation,C.byref(status),phases)
        if code:raise RuntimeError(self.library.profile_error_r7().decode())
        return target,status.value
class ContractSession:
    """Actual native core and C consumer; never represents hardware timing."""
    def __init__(self):
        self.model=Native();self.calls=[];self.restored=True;self.wait_policy=0
        host='Windows' if os.name=='nt' else 'ARM';folder=PROFILE/'host_packed_r7'/('build_'+host)
        proof=READ(folder/'acceptance.json');binary=folder/('consume.dll' if host=='Windows' else 'libconsume.so')
        assert SHA(binary)==proof['consumer_sha256']
        self.consume=C.CDLL(str(binary)).profile_consume_packed_r7
        self.consume.argtypes=[C.c_void_p,C.c_uint32]+[C.c_uint]*3+[C.c_uint64]+[C.c_void_p]*3;self.consume.restype=C.c_int
    def __enter__(self):return self
    def __exit__(self,*exception):self.restore()
    def policy(self,index):assert index in [0,1,2];self.wait_policy=index
    def raw(self,data,operation):
        answer,status=self.model.run(data,operation,output_count=1 if not operation else 2178)
        full=np.zeros((2178,8),np.uint64);full[:len(answer)]=answer;return full,status
    def compact(self,data,operation,n,queries,token):
        full,status=self.raw(data,operation);ack=np.empty((1,8),np.uint64)
        d=np.empty((queries,n),np.float64) if operation else None;p=np.empty((queries,n),np.int32) if operation else None
        code=self.consume(full.ctypes.data,status,operation,n,queries,token,ack.ctypes.data,d.ctypes.data if d is not None else None,p.ctypes.data if p is not None else None)
        if code:raise RuntimeError('Native software-contract consumer refusal, no XRT')
        self.calls.append(dict(operation=operation,input_words=len(data),output_capacity_words=2178,status=status,
            phases_seconds={name:0. for name in PHASES},all_four_full_4096_byte_DMA_guards_checked=False,
            native_kernel_guards_checked=True,full_output_capacity_checked=2178 if operation else 1,
            Python_full_output_copy_bytes=0,measured_backend='native_kernel_and_real_consumer_no_XRT',PL_accessed=False))
        return ack,d,p
    def solve(self,*args,**kwargs):return packed_runtime.Session.solve(self,*args,**kwargs)
    def restore(self):self.restored=True
def fixture_checks(session,trace):
    cases=[tuple(map(int,s.split())) for s in (PROFILE/'rtl_r74/fixtures/cases.txt').read_text().splitlines()]
    raw_records=[];compact_records=[]
    for policy in range(3):
        session.policy(policy)
        for index,(operation,ni,no,capacity) in enumerate(cases):
            incoming=np.fromfile(PROFILE/'rtl_r74/fixtures'/(str(index).zfill(2)+'.input.bin'),'<u8').reshape(-1,8)
            legacy_gold=np.fromfile(PROFILE/'rtl_r74/fixtures'/(str(index).zfill(2)+'.expected.bin'),'<u8').reshape(-1,8)
            wanted=pack_original(legacy_gold,operation);actual,status=session.raw(incoming,operation)
            assert actual.shape==(2178,8);exact(actual[:len(wanted)],wanted);assert np.all(actual[len(wanted):]==0) and status==int(wanted[0,0])
            saved=trace.raw(policy,index,actual)
            raw_records.append(dict(wait_policy=policy,case=index,original_words=no,packed_valid_words=len(wanted),raw_output=saved,actual_control_status=status,
                full_2178_output_and_zero_padding_checked=True,exact_original_FP64_parent_and_metadata=True,exact_invalid_core_status=True))
        for index,(operation,ni,no,capacity) in enumerate(cases):
            incoming=np.fromfile(PROFILE/'rtl_r74/fixtures'/(str(index).zfill(2)+'.input.bin'),'<u8').reshape(-1,8)
            legacy_gold=np.fromfile(PROFILE/'rtl_r74/fixtures'/(str(index).zfill(2)+'.expected.bin'),'<u8').reshape(-1,8)
            wanted=pack_original(legacy_gold,operation);status=int(wanted[0,0])
            n,q,token=map(int,wanted[0,[1,2,4]]) if operation and not status else (0,0,int(incoming[0,4]) if not operation else 0)
            if operation and status:n,q=1,1
            rejected=False
            try:ack,d,p=session.compact(incoming,operation,n,q,token)
            except RuntimeError:rejected=True
            assert rejected==bool(status),(policy,index)
            if not rejected:
                exact(ack,wanted[:1])
                if operation:
                    exact(d.view(np.uint64).ravel(),legacy_gold[1:1+n*q,0].copy())
                    exact(p.view(np.uint32).ravel(),legacy_gold[1:1+n*q,1].astype(np.uint32))
            compact_records.append(dict(wait_policy=policy,case=index,expected_status=status,expected_rejection=rejected,
                all_original_cost_bits_and_parent_ids_checked=True,maximum_8705_case_retained=index==15))
    assert len(raw_records)==48 and len(compact_records)==48
    return raw_records,compact_records
def execute(prepared,session,contract):
    data=prepared['data'];diameters=prepared['diameters'];ed=prepared['wanted_d'];ep=prepared['wanted_p'];cpu=ProfilePS()
    def check(d,p,computed):exact(d,ed);exact(p,ep);compare_reports(computed,prepared['expected_report'])
    samples=[];trace=Trace(prepared['host'],contract)
    with session:
        raw,compact=fixture_checks(session,trace)
        for warm in range(2):
            for policy in range(3):session.policy(policy);d,p=session.solve(data,diameters,.2,2.);exact(d,ed);exact(p,ep)
            for threads in [1,4]:_,d,p=cpu.solve(data,diameters,.2,2.,threads=threads);exact(d,ed);exact(p,ep)
        for repeat in range(10):
            shift=repeat%5;order=PROVIDERS[shift:]+PROVIDERS[:shift];ps={};pl={};ps_compute={};pl_compute={};calls={};answers={}
            for provider in order:
                start=time.perf_counter()
                if isinstance(provider,int):
                    values,d,p=cpu.solve(data,diameters,.2,2.,threads=provider);ps_compute[str(provider)]=time.perf_counter()-start
                    computed=report(data,prepared['image'],prepared['tree'],values,d,p);ps[str(provider)]=time.perf_counter()-start
                else:
                    policy=provider.removeprefix('PL_');session.policy({'sleep20':0,'spin200':1,'spin2000':2}[policy])
                    begin=len(session.calls);d,p=session.solve(data,diameters,.2,2.);pl_compute[policy]=time.perf_counter()-start
                    computed=report(data,prepared['image'],prepared['tree'],diameters,d,p);pl[policy]=time.perf_counter()-start;calls[policy]=session.calls[begin:]
                    assert len(calls[policy])==2 and [c['operation'] for c in calls[policy]]==[0,1]
                check(d,p,computed)
                answers[str(provider)]=trace.answers(repeat,provider,d,p)
            samples.append(dict(repeat=repeat,execution_order=order,PS_full_profile_API_seconds=ps,PL_full_profile_API_seconds=pl,
                PS_distances_and_parents_API_seconds=ps_compute,PL_distances_and_parents_API_seconds=pl_compute,PL_calls=calls,
                all_4315_original_FP64_bits_and_parents_exact=True,all_original_report_fields_passed=True,software_contract_only=contract,answer_trace=answers))
            print('Complete original CT comparison round',repeat,'contract_only',contract,flush=True)
        context=prepared['context'];skeleton=np.zeros(context.mask.shape,bool);skeleton[tuple(data.coordinates_zyx.T)]=True
        start=time.perf_counter();original_report=legacy.reachability_profile(skeleton,tuple(data.coordinates_zyx[data.root]),data.spacing_zyx,
            context.distance_mm,prepared['image'],prepared['tree'],diameters,.2);original_seconds=time.perf_counter()-start
        compare_reports(original_report,prepared['expected_report']);session.restore()
    for provider in PROVIDERS:assert all(sum(s['execution_order'][position]==provider for s in samples)==2 for position in range(5))
    ps={t:statistics.median(s['PS_full_profile_API_seconds'][t] for s in samples) for t in ['1','4']}
    pl={policy:statistics.median(s['PL_full_profile_API_seconds'][policy] for s in samples) for policy in ['sleep20','spin200','spin2000']}
    best=min(pl,key=pl.get);strongest=min(ps.values());result=dict(
        status='native_core_real_consumer_PS1_PS4_complete_benchmark_contract_passed_no_XRT' if contract else 'actual_R7_full_original_CT_PS1_PS4_three_policy_comparison',
        host=prepared['host'],software_contract_only=contract,PL_accessed=not contract,production_promoted=False,whole_goal_completed=False,
        performance_gate_passed=not contract and pl[best]<=strongest,PS4_PL_speedup_established=not contract and pl[best]<=ps['4'],
        strongest_PS_full_API_seconds=None if contract else strongest,best_PL_policy=None if contract else best,
        PL_full_API_speedup_over_strongest_PS=None if contract else strongest/pl[best],
        own_CT_nodes=len(data.coordinates_zyx),undirected_raw_edges=len(data.neighbors)//2,
        all_4315_original_FP64_costs_and_parents_exact=True,all_original_report_fields_checked=True,
        raw_fixtures=raw,compact_fixtures=compact,samples=samples,complete_output_words_per_call=2178,
        four_full_DMA_guards_checked_in_hardware=not contract,original_Python_profile_seconds=original_seconds,
        fixture_sha256=prepared['fixture_sha256'],source_and_evidence_sha256=prepared['sources'],
        timing_scope='Each full API freshly prepares and uploads the complete original graph, calculates all queries, checks all results and four DMA guards, and formats the same report. Common file IO and shared geometric preparation excluded equally. Two warmups, ten balanced rotating rounds, no cached graph transfer or answers. Host wait is not isolated PL cycles.')
    result['source_and_evidence_sha256'].update(trace.bindings)
    result['source_and_evidence_sha256'][(HERE/'answer_trace.py').relative_to(ROOT).as_posix()]=SHA(HERE/'answer_trace.py')
    result['complete_actual_raw_and_provider_answer_files']=len(trace.bindings)
    if contract:result['native_contract_provider_medians_only']=dict(PS=ps,native_kernel_consumer=pl)
    else:result.update(median_PS_full_API_seconds=ps,median_PL_full_API_seconds=pl,peak_process_RSS_MiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        release_manifest_sha256=SHA(RELEASE/'manifest.json'),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    return result
def main():
    p=argparse.ArgumentParser();p.add_argument('--preflight-only',action='store_true');p.add_argument('--software-contract-only',action='store_true');args=p.parse_args()
    if not args.software_contract_only:published_preflight();packed_runtime.verify_release()
    prepared=preparation()
    if args.preflight_only:print('Original complete CT/PS/native host and release preflight passed; no XRT open or PL access');return
    out=HERE/('benchmark_contract_r79d_'+prepared['host']+'.json') if args.software_contract_only else HERE/'board/own_CT_benchmark_r79d.json'
    assert not out.exists()
    if not args.software_contract_only:assert sys.platform=='linux' and os.geteuid()==0
    result=execute(prepared,ContractSession() if args.software_contract_only else BoardSession(),args.software_contract_only)
    verify(prepared['sources'])
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf-8',newline='\n') as f:json.dump(result,f,indent=2);f.write('\n')
    print(result['status'],flush=True)
if __name__=='__main__':main()
