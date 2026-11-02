"""Re-read complete original-gold RTL and actual RM evidence before R7 routing."""
from pathlib import Path
import hashlib,json,re,sys
HERE=Path(__file__).resolve().parent;PROFILE=HERE.parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(PROFILE/'rtl_r74'))
from check_full import actual,generated
from completion_r74 import check_log
SHA=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
READ=lambda p:json.loads(p.read_text(encoding='utf-8'))
RM=PROFILE/'rm_r7_r76c';FULL=PROFILE/'rtl_r74/full'
BUDGET=dict(LUT=88320,FF=176640,DSP=960,BRAM36_equivalent=132,URAM=64)
def verify(mapping):
    for name,wanted in mapping.items():
        p=(ROOT/name).resolve();assert p.is_relative_to(ROOT) and SHA(p)==wanted,name
def success(receipt,log):
    assert receipt['passed'] and receipt['exit_code']==0 and receipt['all_owned_processes_terminal']
    assert receipt['actual_default_memory_API'] and not receipt['resource_failure'] and not receipt['job_memory_limit_rejection_observed']
    assert receipt['log_sha256']==SHA(log)
def resources(text):
    header=None
    for line in text.splitlines():
        fields=[p.strip() for p in line.split('|')[1:-1]]
        if fields and fields[0]=='Instance' and 'Total LUTs' in fields:header=fields
        if header and fields and fields[0]=='rm_medical':
            row=dict(zip(header,fields));integer=lambda n:int(row[n].replace(',',''))
            return dict(LUT=integer('Total LUTs'),FF=integer('FFs'),DSP=integer('DSP Blocks'),
                BRAM36=integer('RAMB36'),BRAM18=integer('RAMB18'),URAM=integer('URAM'))
    raise AssertionError('No actual synthesized rm_medical row')
def wrapper(text):
    ports=[tuple(p) for p in READ(ROOT/'dfx/medical/build/rp_ports.json')]
    declared=re.findall(r'\b(input|output)\s+wire\s*(\[[^\]]+\])?\s*(\w+)',text.split(');',1)[0])
    assert declared==ports,'Frozen RP ports changed'
    assert text.count('route_pad #(.WORDS(2178)) padding(')==1
    assert text.count("assign identity=8'hcf;")==1
    for direction,width,name in ports:
        if direction=='output' and name.startswith('memory_'):assert f'assign {name}=0;' in text,name
    return dict(frozen_ports=len(ports),output_capacity_words=2178,identity_hex='cf',unused_memory_outputs_zero=True)
def verify_rm(directory=RM,full_source=True):
    directory=Path(directory);out=directory/'build'
    receipt=READ(out/'synthesis_receipt.json');success(receipt,out/'synthesis.log')
    assert receipt['actual_RM_synthesized'] and not receipt['route_passed'] and not receipt['PL_accessed']
    if full_source:verify(receipt['source_and_input_sha256'])
    origin=READ(out/'rm_core_build_origin_r7.json')
    assert origin['identity_hex']=='cf' and origin['output_padded_capacity_words']==2178
    verify(origin['frozen_boundary_sha256'])
    if full_source:verify(origin['source_and_input_sha256']);verify(origin['actual_IP_inventory_sha256'])
    proof=READ(out/'rm_core_resource_r7.json')
    for name,wanted in proof['artifact_sha256'].items():assert SHA(directory/name)==wanted,name
    counts=resources((out/'rm_core_synth_util_r7.rpt').read_text())
    assert counts==proof['resources'] and proof['budget']==BUDGET and not proof['excess']
    used=dict(LUT=counts['LUT'],FF=counts['FF'],DSP=counts['DSP'],BRAM36_equivalent=counts['BRAM36']+.5*counts['BRAM18'],URAM=counts['URAM'])
    assert all(used[k]<=v for k,v in BUDGET.items())
    assert proof['remaining']=={k:v-used[k] for k,v in BUDGET.items()}
    log=(out/'synthesis.log').read_text(errors='replace')
    assert 'PROFILE_CORE_R7_RM_RESOURCE_GATE_PASSED' in log and 'INFO: [Common 17-206] Exiting Vivado' in log
    assert not re.search(r'(?m)^\s*(?:ERROR|FATAL)\s*[:\[]',log)
    ports=wrapper((out/'rm_medical_core_r7.v').read_text())
    return dict(actual_RM_synthesis_passed=True,resources=counts,remaining=proof['remaining'],boundary=ports,
        complete_local_source_closure_rechecked=full_source,elapsed_s=receipt['elapsed_s'],peak_job_bytes=receipt['reported_peak_job_bytes'])
def verify_run(label,sim=None,receipts=FULL,full_source=True):
    assert label in ['ordinary','random'];sim=Path(sim) if sim else PROFILE/('p75o' if label=='ordinary' else 'p75r')/'sim'
    receipts=Path(receipts);binding=generated(sim);fields=actual(sim)
    for stage in ['elaborate','simulate','postcheck']:
        r=READ(receipts/(label+'_'+stage+'_receipt.json'));success(r,receipts/(label+'_'+stage+'.log'))
        if full_source:verify(r['source_and_input_sha256'])
    log=(receipts/(label+'_simulate.log')).read_text(errors='replace');completion=check_log(log)
    matches=re.findall(r'NAV_PACKED_OBSERVER cycles=(\d+) input_words=(\d+) output_words=(\d+) input_backpressure_cycles=(\d+) input_source_gap_cycles=(\d+) output_backpressure_cycles=(\d+) violations=(\d+)',log)
    assert len(matches)==1;values=list(map(int,matches[0]))
    assert values[1]==binding['input_words'] and values[2]==binding['output_words'] and values[6]==0
    if label=='random':assert min(values[3:6])>0
    post=(receipts/(label+'_postcheck.log')).read_text()
    assert [int(x) for x in re.findall(r'PACKED_FULL_PASS case=(\d+) ',post)]==list(range(16))
    assert 'ALL 14 ORIGINAL PLUS 2 MAXIMUM RESULT CASES PACKED LOSSLESSLY' in post
    prior=READ(receipts/(label+'_full_output.json'));assert prior['fields']==fields and prior['completion']==completion
    for name,wanted in prior['files'].items():assert SHA(sim/'tv/rtldatafile'/Path(name).name)==wanted,name
    return dict(total_cases=16,original_cases=14,maximum_8705_results_checked=True,all_six_actual_fields_exact=fields,
        all_original_inputs_and_control_counts_rechecked=True,completion=completion,original_C_postcheck_passed=True,
        complete_local_source_closure_rechecked=full_source,observer=dict(zip(['cycles','input_words','output_words','input_backpressure_cycles','input_source_gap_cycles','output_backpressure_cycles','violations'],values)))
def complete_job(job):
    assert job['status']=='all_16_ordinary_16_actual_random_R7_RTL_and_postchecks_passed'
    assert job['stage']=='complete' and job['original_cases']==14 and job['total_cases']==16
    assert all(job[k] is True for k in ['ordinary_passed','random_passed','full_RTL_passed'])
    assert not job['PL_accessed']
