"""Independently reopen actual logs/RTL, enumerate every full frame and reset."""
from pathlib import Path
from contextlib import ExitStack
from datetime import datetime,timezone
import hashlib,json,re,sys
import project_storage
ROOT=project_storage.SYSTEM;sys.path.insert(0,str(ROOT))
from modules.reconstruction.smooth_pipeline_r2.axis_fma3_area_r14.flow_RTL_r1.verify_collected import View
HERE=ROOT/'modules/segmentation/axis_tensor_reader_r3/RTL_r1'
OUT=ROOT/'results/tensor_reader_R3_RTL_20261022_r1/axis_rtl'

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    project_storage.check(1_000_000);assert not (OUT/'verified_PC.json').exists()
    receipt=json.loads((OUT/'stream_collection_verified.json').read_text())
    cleanup=json.loads((OUT/'cleanup_verified_stream.json').read_text())
    assert cleanup['owned_root_confirmed_absent'] and cleanup['all_owned_member_bytes_and_closed_logs_stream_SHA_verified_locally']
    archive=OUT/'current_candidate.zip';assert sha(archive)==receipt['compact_archive_SHA256']
    admission=json.loads((HERE/'admission.json').read_text());native=json.loads((HERE.parent/'native_verified.json').read_text())
    prefix='workspace/'+HERE.relative_to(ROOT).as_posix()+'/'
    with ExitStack() as st:
        view=View(st,archive)
        for name in sorted(set(view.names)|set(view.aliases)):
            with view.stream(name) as f:
                digest=hashlib.file_digest(f,'sha256').hexdigest()
            assert digest==view.original.get(name,view.names.get(name)),name
        obj=lambda n:json.loads(view.read(n))
        assert obj('terminal.json')['tool_gates_passed']
        complete=obj(prefix+'complete.json');assert complete['all330_complete_frames_and8_actual_global_resets']
        assert complete['source_SHA256']==admission['source_SHA256']
        for n,h in admission['source_SHA256'].items():assert sha(ROOT/n)==h,n
        for n,h in admission['generated_RTL_SHA256'].items():
            assert hashlib.sha256(view.read(prefix+'source_RTL/'+n)).hexdigest()==h,n
        assert len([n for n in admission['generated_RTL_SHA256'] if n.endswith('.v')])==40
        results={};total_words=0
        for mode in ('ordinary','random'):
            base=prefix+f'run/{mode}/';text=view.read(base+'simulate.log').decode('utf-8',errors='replace')
            assert not any(s in text for s in ('ERROR:','Fatal:','FATAL:','cannot be opened for reading','WARNING: File'))
            frames=re.findall(r'READER_RTL_FRAME case=(\d+) invalid=(\d+) packets=(\d+) cycles=(\d+)',text)
            order=list(range(159))+[1,74,64,65,66,67];assert len(frames)==165
            words=0
            for row,index in zip(frames,order):
                n,invalid,packets,cycles=map(int,row);c=native['cases'][index]
                assert n==index and invalid==c['status'] and packets==c['packets'] and cycles>0
                if not invalid:
                    groups=(c['ca']+c['cb']+7)//8
                    expected=((c['h']*c['w']*groups*8+31)//32 if c['kernel']==1 else (c['h']+2)*(c['w']+2)*groups)
                    assert packets==expected
                words+=packets
            assert re.findall(r'READER_ACTUAL_RESET stage=(\d+)',text)==['0','1','2','3']
            assert text.count('READER_TWO_TRAILING_CALLS_NO_RESET_EXACT')==1
            final=re.findall(r'PASS READER_FULL159_TRAILING2_RESET4_RECOVERY4 frames=(\d+) resets=(\d+) reads=(\d+) beats=(\d+) axis_stalls=(\d+) ar_stalls=(\d+) r_stalls=(\d+)',text)
            assert len(final)==1 and tuple(map(int,final[0][:2]))==(165,4)
            counters=list(map(int,final[0]));assert counters[2]>0 and counters[3]>=counters[2]
            if mode=='random':assert counters[4]>0 and counters[5]>0
            contract=obj(base+'harness_contract.json');assert contract['case_count']==159 and len(contract['port_map'])==71
            assert contract['generated_SV_SHA256']==hashlib.sha256(view.read(base+'tb.sv')).hexdigest()
            assert contract['actual_model_LUT_hex_SHA256']==hashlib.sha256(view.read(base+'model_lut.hex')).hexdigest()
            assert hashlib.sha256(view.read(base+'tb.sv')).hexdigest()==sha(HERE/'preflight_r3'/mode/'tb.sv')
            assert view.read(base+'model_lut.hex')==(HERE/'preflight_r3'/mode/'model_lut.hex').read_bytes()
            stages={}
            for stage in ('setup','compile','elaborate','simulate'):
                v=obj(base+stage+'_receipt.json')
                assert v['exit_code']==0 and v['all_owned_processes_terminal'] and v['configured_limit_verified']
                assert not v['resource_failure'] and not v['elapsed_time_abort']
                stages[stage]=dict(seconds=v['elapsed_s'],peak_job_bytes=v['reported_peak_job_bytes'])
            results[mode]=dict(complete_frames=165,actual_resets=4,full_packet_words=words,
                counters=dict(zip(['frames','resets','read_requests','read_beats','AXIS_stall_cycles','AR_stall_cycles','R_stall_cycles'],counters)),stages=stages)
            total_words+=words
    result=dict(UTC=datetime.now(timezone.utc).isoformat(),
        actual_generated40RTL_full159_original_domains_both_schedules_passed=True,
        all330_full_frames_and8_actual_global_resets_verified=True,total_complete_output_packet_words=total_words,
        all_original_three_full_model_join_dimensions_and_LUTs_retained=True,
        all_full_packet_data_padding_keep_strb_last_and_next_frames_checked=True,
        original_AXIL_controls_actual_AXI_lowDDR_4K_ID_bounds_and_no_writes_preserved=True,
        actual_AXIL_AXI_AXIS_stalled_payload_monitors_preserved=True,actual_results=results,
        all_retained_members_and_canonical_aliases_reopened=True,all_owned_server_bytes_collected_and_exact_root_removed=True,
        archive_SHA256=sha(archive),source_HLS_archive_SHA256=admission['source_HLS_archive_SHA256'],
        source_and_evidence_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),HERE/'admission.json',HERE/'collect.py',HERE/'run.py',HERE/'generate.py',HERE/'testbench.sv.in']},
        standalone_RTL_not_whole_C5_100MHz_5PR_ARM139_system_qualification=True,
        PL_accessed=False,production_promoted=False,whole_goal_completed=False)
    with (OUT/'verified_PC.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_and_evidence_SHA256','actual_results')},indent=2))

if __name__=='__main__':main()
