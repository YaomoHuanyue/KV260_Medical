"""Independently check collected actual HLS RTL, all40 cases and18,351,000 words."""
from pathlib import Path
from contextlib import ExitStack
import hashlib,io,json,sys,zipfile
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[4]
OUT=ROOT/'results/smooth_FMA3_flow40_RTL_20261019_r14/axis_rtl'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
class View:
    def __init__(self,stack,path):
        self.stack=stack;self.z=stack.enter_context(zipfile.ZipFile(path));self.cache={}
        self.names=json.loads(self.z.read('outputs_manifest.json'))
        self.original=json.loads(self.z.read('collection/original_outputs_manifest.json'))
        self.aliases=json.loads(self.z.read('collection/canonical_aliases.json'))['logical_aliases']
    def stream(self,name):
        if name in self.names:return self.z.open(name)
        a=self.aliases[name];assert self.original[name]==a['SHA256']
        if a['kind']=='retained_member':return self.z.open(a['member'])
        if a['kind']=='canonical_file':
            p=(ROOT/a['path']).resolve();assert p.is_relative_to(ROOT) and p.is_file() and sha(p)==a['SHA256'];return p.open('rb')
        assert a['kind']=='canonical_archive'
        if a['archive'] not in self.cache:
            p=(ROOT/a['archive']).resolve();assert p.is_relative_to(ROOT) and p.is_file() and sha(p)==a['archive_SHA256']
            self.cache[a['archive']]=self.stack.enter_context(zipfile.ZipFile(p))
        return self.cache[a['archive']].open(a['member'])
    def read(self,name):
        with self.stream(name) as f:raw=f.read()
        assert hashlib.sha256(raw).hexdigest()==self.original.get(name,self.names.get(name)),name
        return raw
def main():
    proof=OUT/'verified_Windows.json';assert not proof.exists()
    receipt=json.loads((OUT/'stream_collection_verified.json').read_text());cleanup=json.loads((OUT/'cleanup_verified_stream.json').read_text())
    assert cleanup['owned_root_confirmed_absent'] and cleanup['all_owned_member_bytes_and_closed_logs_stream_SHA_verified_locally']
    archive=OUT/'current_candidate.zip';assert sha(archive)==receipt['compact_archive_SHA256']
    with ExitStack() as stack:
        view=View(stack,archive);prefix='workspace/rtl_flow/'
        complete=json.loads(view.read(prefix+'complete.json'))
        for key in ['all40_complementary_cases_passed','all18351000_full_bank_words_exact',
            'all5_work_banks_16_reports_unused_tails_preserved','independent_original_C_gold',
            'actual4_AXI_ID_bounds_hold_checks','actual512_AXIS_header_payload_sideband_backpressure_checks',
            'reset_input_partial_stall_and_output_stall_recovered','original14_numeric_gate_not_replaced','actual_HLS_RTL_unchanged']:
            assert complete[key],key
        for name,h in complete['source_and_evidence_SHA256'].items():
            assert view.original['workspace/'+name]==h
            with view.stream('workspace/'+name) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==h,name
            local=ROOT/name
            if local.exists():assert local.is_file() and sha(local)==h,'Changed physical source cannot fall back: '+name
        fixture=HERE/'fixtures.zip';meta=json.loads((HERE/'fixtures_verified.json').read_text())
        assert sha(fixture)==meta['archive_SHA256']
        z=stack.enter_context(zipfile.ZipFile(fixture));manifest=json.loads(z.read('outputs_manifest.json'))
        cases=json.loads(z.read('cases.json'));assert len(cases['cases'])==40
        reference=(ROOT/cases['reference_path']).resolve()
        assert reference.is_relative_to(ROOT) and sha(reference)==cases['reference_SHA256']
        log=view.read(prefix+'simulate.log').decode(errors='replace')
        assert log.count('FLOW_COMPLETED case=')==40 and 'PASS all40_complementary_full_core_fault_reset_recovery_cases' in log
        assert 'FLOW_RESET_AT_input_STALL beats=' in log and 'FLOW_RESET_AT_output_STALL' in log
        assert not any(t in log for t in ['ERROR:','Fatal:','Critical WARNING'])
        for name in ['compile_receipt.json','simulate_receipt.json']:
            r=json.loads(view.read(prefix+name));assert r['exit_code']==0 and r['all_owned_processes_terminal'] and r['configured_limit_verified']
            assert not r['resource_failure'] and not r['elapsed_time_abort']
        tb=view.read(prefix+'faults/tb.sv').decode()
        assert tb.count('Truncated ')==16 and 'cycles>15000000' in tb and tb.count('FLOW_COMPLETED case=')==40
        assert 'axis_payload_hold hold_input_r' in tb and 'axis_payload_hold hold_output_r' in tb
        rows=[];total=0
        for bank in ['meta','coords']:
            width,count,_=cases['banks'][bank]
            member=prefix+'faults/rtl.mesh_smooth.autotvout_'+bank+'.dat';h=hashlib.sha256()
            with view.stream(member) as source:
                def line():
                    raw=source.readline();assert raw;h.update(raw);return raw.strip()
                assert line()==b'[[[runtime]]]'
                for index,case in enumerate(cases['cases']):
                    assert line()==f'[[transaction]] {index}'.encode()
                    name='gold/'+case['name']+'/'+bank+'.bin';gold=z.read(name);assert hashlib.sha256(gold).hexdigest()==manifest[name]
                    assert len(gold)==width*count
                    for word in range(count):
                        actual=int(line(),16);expected=int.from_bytes(gold[word*width:(word+1)*width],'little')
                        assert actual==expected,(bank,case['name'],word,actual,expected)
                    assert line()==b'[[/transaction]]';total+=count
                assert line()==b'[[[/runtime]]]' and not source.read().strip()
            assert h.hexdigest()==view.original[member]
            rows.append(dict(bank=bank,all40_full_banks_exact=True,words=40*count,capture_SHA256=h.hexdigest()))
        assert total==18351000
    result=dict(status='independent_PC_all40_actual_FMA3_R14_malformed_reset_recovery_full_RTL_verified',
        all18351000_full_bank_words_independently_exact=True,all5_banks16_reports_unused_tails_exact=True,
        real4_AXI_full_ID_bounds_hold_checks_and512_AXIS_errors_backpressure_checked=True,
        input_partial_stall_and_output_stall_global_reset_recovery_checked=True,
        global_reset_not_equivalent_to_unsafe_live_DFX_abort=True,
        original_full14_gate_and_HLS_dependency_checker_and_ARM_route_PR_board_PS4_still_required=True,
        frozen_original_C_reference_SHA256=cases['reference_SHA256'],banks=rows,
        archive_SHA256=sha(archive),all_owned_bytes_collected_and_exact_server_root_absent=True,
        source_and_evidence_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),HERE/'fixtures.zip',HERE/'fixtures_verified.json',OUT/'stream_collection_verified.json',OUT/'cleanup_verified_stream.json']},
        PL_accessed=False,production_promoted=False,whole_goal_completed=False)
    proof.write_text(json.dumps(result,indent=2)+'\n');print('PASS independent40 actual D8 RTL18351000 exact words; ARM/PR/board and full14 gates remain',flush=True)
if __name__=='__main__':main()
