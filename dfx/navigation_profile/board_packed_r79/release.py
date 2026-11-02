"""Seal/publish R7 only from complete actual RTL and routed 100 MHz PR proofs."""
from pathlib import Path
import hashlib,json,re,sys
HERE=Path(__file__).resolve().parent;PROFILE=HERE.parent;ROOT=HERE.parents[2];RELEASE=PROFILE/'release_r7'
sys.path.insert(0,str(PROFILE/'route_r7_r78'))
from verify_inputs import verify,verify_run,BUDGET
SHA=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
READ=lambda p:json.loads(p.read_text(encoding='utf-8'))
def resource_row(text,instance):
    header=None
    for line in text.splitlines():
        fields=[v.strip() for v in line.split('|')[1:-1]]
        if fields and fields[0]=='Instance' and 'Total LUTs' in fields:header=fields
        if header and fields and fields[0]==instance:
            row=dict(zip(header,fields));integer=lambda name:int(row[name].replace(',',''))
            return dict(LUT=integer('Total LUTs'),FF=integer('FFs'),DSP=integer('DSP Blocks'),
                BRAM36=integer('RAMB36'),BRAM18=integer('RAMB18'),URAM=integer('URAM'))
    raise AssertionError('Missing actual routed '+instance)
def reports(timing,drc,pr,util):
    match=re.search(r'WNS\(ns\).*?\n\s*-+.*?\n\s*([-\d.]+)\s+[-\d.]+\s+\d+\s+\d+\s+([-\d.]+)',timing,re.S)
    assert match;wns,whs=map(float,match.groups())
    assert wns>=0 and whs>=0 and 'All user specified timing constraints are met.' in timing
    for clock in ['clk_pl_0','clk_pl_1']:
        assert re.search(r'^'+clock+r'\s+\{0\.000 5\.000\}\s+10\.000\s+100\.000\s*$',timing,re.M),clock
    for check in ['no_clock','unconstrained_internal_endpoints','multiple_clock','loops','latch_loops']:
        assert re.search(r'checking '+check+r' \(0\)',timing),check
    assert not re.search(r'\|\s*(Error|Critical Warning)\s*\|',drc,re.I)
    assert re.search(r'PR_VERIFY: check points .*config_smooth\.dcp and .*config_profile_core_r7\.dcp are compatible',pr)
    assert not re.search(r'(?m)^\s*(?:ERROR|FATAL)\s*[:\[]',pr)
    whole=resource_row(util,'system_top');rp=resource_row(util,'rp')
    used=dict(LUT=rp['LUT'],FF=rp['FF'],DSP=rp['DSP'],BRAM36_equivalent=rp['BRAM36']+.5*rp['BRAM18'],URAM=rp['URAM'])
    assert all(used[k]<=v for k,v in BUDGET.items())
    return dict(clock_MHz=100,WNS_ns=wns,WHS_ns=whs,whole_resources=whole,RP_resources=rp,
        remaining_RP={k:v-used[k] for k,v in BUDGET.items()},timing_constraints_and_DRC_and_full_PR_checked=True)
def host_proofs():
    bindings={}
    for host in ['Windows','ARM']:
        folder=PROFILE/'host_packed_r7'
        for name in ['result_'+host+'.json','runtime_contract_'+host+'.json','build_'+host+'/acceptance.json']:
            path=folder/name;proof=READ(path);verify(proof['source_and_evidence_sha256']);bindings.update(proof['source_and_evidence_sha256']);bindings[path.relative_to(ROOT).as_posix()]=SHA(path)
            if name.startswith('result_'):assert proof['all_16_original_and_capacity_cases_checked'] and proof['rejections_before_all_output_writes']
            elif name.startswith('runtime_'):assert proof['actual_solve_all_cases_exact'] and proof['all_failure_cleanup_cases_passed']
            elif host=='ARM':
                binary=folder/'build_ARM/libprofile_packed_r7.so';assert SHA(binary)==proof['XRT_bridge_sha256'];bindings[binary.relative_to(ROOT).as_posix()]=SHA(binary)
    return bindings
def build_preflight():
    from run_route import preflight
    gate=preflight();out=PROFILE/'route_r7_r78/build';receipt=READ(out/'route_receipt.json')
    assert receipt['status']=='R7_actual_route_100MHz_setup_hold_full_PR_passed_board_tests_pending'
    assert receipt['passed'] and receipt['route_passed'] and receipt['exit_code']==0 and receipt['all_owned_processes_terminal']
    assert receipt['actual_default_memory_API'] and not receipt['resource_failure'] and not receipt['job_memory_limit_rejection_observed']
    assert receipt['source_and_input_sha256']==gate['source_and_input_sha256'];verify(receipt['artifacts_sha256'])
    assert SHA(out/'route.log')==receipt['log_sha256']
    report=reports(*[(out/name).read_text(errors='replace') for name in ['timing_profile_core_r7.rpt','drc_profile_core_r7.rpt','pr_verify_profile_core_r7.log','utilization_profile_core_r7.rpt']])
    host=host_proofs()
    return gate,receipt,report,host
def build():
    assert not RELEASE.exists(),'Keep an existing release intact'
    gate,receipt,report,host=build_preflight()
    source=PROFILE/'route_r7_r78/build/config_profile_core_r7_pblock_rp_partial.bin';assert source.is_file() and source.stat().st_size>0
    RELEASE.mkdir()
    def copy(path,target):
        target=RELEASE/target;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as f:f.write(path.read_bytes())
        assert SHA(target)==SHA(path)
    copy(source,Path('medical_navigation_profile_r7_partial.bin'))
    full=PROFILE/'rtl_r74/full'
    for label,folder in [('ordinary','p75o'),('random','p75r')]:
        for stage in ['elaborate','simulate','postcheck']:
            for suffix in ['.log','_receipt.json']:copy(full/(label+'_'+stage+suffix),Path('RTL/receipts')/(label+'_'+stage+suffix))
        copy(full/(label+'_full_output.json'),Path('RTL/receipts')/(label+'_full_output.json'))
        for directory in ['cdatafile','rtldatafile']:
            for path in (PROFILE/folder/'sim/tv'/directory).glob('*.dat'):copy(path,Path('RTL')/label/'sim/tv'/directory/path.name)
    out=PROFILE/'route_r7_r78/build'
    for name in ['route_receipt.json','route_metrics_r7.json','timing_profile_core_r7.rpt','drc_profile_core_r7.rpt',
        'pr_verify_profile_core_r7.log','utilization_profile_core_r7.rpt','route.log']:
        copy(out/name,Path('route_reports')/name)
    offline=dict(status='complete_actual_R7_16_ordinary_16_random_RTL_RM_100MHz_full_PR_locally_verified',
        full_local_source_closure_verified=gate,actual_route_receipt=receipt,route_reports=report,
        source_closure_rechecked_at_sealing=True,actual_board_speed_verified=False,production_promoted=False)
    with (RELEASE/'offline_verification.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(offline,f,indent=2);f.write('\n')
    bindings=dict(host)
    for path in RELEASE.rglob('*'):
        if path.is_file():bindings[path.relative_to(ROOT).as_posix()]=SHA(path)
    for path in HERE.glob('*.py'):bindings[path.relative_to(ROOT).as_posix()]=SHA(path)
    for path in [PROFILE/'route_r7_r78/verify_inputs.py',PROFILE/'rtl_r74/check_full.py',PROFILE/'rtl_r74/completion_r74.py']:
        bindings[path.relative_to(ROOT).as_posix()]=SHA(path)
    manifest=dict(schema='kv260.navigation_profile.dfx.packed.v1',identity=0xcf,output_capacity_words=2178,maximum_results=8705,
        result_magic='5052515545525932',offline_verified=True,full_16_ordinary_RTL_passed=True,full_16_random_RTL_passed=True,
        actual_RM_synthesized=True,route_PR_100MHz_passed=True,source_and_evidence_sha256=bindings,
        partial_bin_sha256=SHA(RELEASE/'medical_navigation_profile_r7_partial.bin'),static_base_manifest_sha256=SHA(ROOT/'dfx/medical/release/manifest.json'),
        actual_board_speed_verified=False,production_promoted=False)
    with (RELEASE/'manifest.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(manifest,f,indent=2);f.write('\n')
    print(offline['status'])
def metadata(manifest):
    assert manifest['schema']=='kv260.navigation_profile.dfx.packed.v1' and manifest['identity']==0xcf
    assert manifest['output_capacity_words']==2178 and manifest['maximum_results']==8705 and manifest['result_magic']=='5052515545525932'
    assert all(manifest[k] is True for k in ['offline_verified','full_16_ordinary_RTL_passed','full_16_random_RTL_passed','actual_RM_synthesized','route_PR_100MHz_passed'])
def published_preflight():
    manifest=READ(RELEASE/'manifest.json');metadata(manifest);verify(manifest['source_and_evidence_sha256'])
    assert SHA(ROOT/'dfx/medical/release/manifest.json')==manifest['static_base_manifest_sha256']
    assert SHA(RELEASE/'medical_navigation_profile_r7_partial.bin')==manifest['partial_bin_sha256']
    offline=READ(RELEASE/'offline_verification.json')
    assert offline['status']=='complete_actual_R7_16_ordinary_16_random_RTL_RM_100MHz_full_PR_locally_verified' and offline['source_closure_rechecked_at_sealing']
    out=RELEASE/'route_reports'
    actual_reports=reports(*[(out/name).read_text(errors='replace') for name in ['timing_profile_core_r7.rpt','drc_profile_core_r7.rpt','pr_verify_profile_core_r7.log','utilization_profile_core_r7.rpt']])
    assert actual_reports==offline['route_reports'];host_proofs()
    runs={label:verify_run(label,RELEASE/'RTL'/label/'sim',RELEASE/'RTL/receipts',full_source=False) for label in ['ordinary','random']}
    return dict(manifest_sha256=SHA(RELEASE/'manifest.json'),partial_sha256=manifest['partial_bin_sha256'],route_reports=actual_reports,actual_complete_original_RTL=runs,PL_accessed=False)
if __name__=='__main__':build()
