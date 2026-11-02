"""Independently inspect actual whole-C5 synthesis, boundary and owned collection."""
from pathlib import Path
from contextlib import ExitStack
import hashlib,importlib.util,json,re,sys
HERE=Path(__file__).resolve().parent;CORE=HERE.parent;ROOT=CORE.parents[2]
OUT=ROOT/'results/tensor_reader_R3_C5_SYN_20261022_r1/axis_hls'
CODEC=ROOT/'modules/reconstruction/smooth_pipeline_r2/axis_fma3_area_r14/flow_RTL_r1/verify_collected.py'

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    target=OUT/'verified_Windows.json';assert not target.exists()
    receipt=json.loads((OUT/'stream_collection_verified.json').read_text());cleanup=json.loads((OUT/'cleanup_verified_stream.json').read_text())
    assert cleanup['owned_root_confirmed_absent'] and cleanup['all_owned_member_bytes_and_closed_logs_stream_SHA_verified_locally']
    archive=OUT/'current_candidate.zip';assert sha(archive)==receipt['compact_archive_SHA256']
    spec=importlib.util.spec_from_file_location('independent_C5_SYN_view',CODEC);codec=importlib.util.module_from_spec(spec);spec.loader.exec_module(codec)
    prefix='workspace/'+(HERE/'output').relative_to(ROOT).as_posix()+'/'
    with ExitStack() as stack:
        view=codec.View(stack,archive);terminal=json.loads(view.read('terminal.json'));passed=terminal['tool_gates_passed'];failure=None;result=None
        if passed:
            result=json.loads(view.read(prefix+'complete.json'))
            for key in ('actual_complete_three_role_BD_synthesis_passed','all_three_exact_packaged_IP_members_verified',
                'writer_control8_required_pool_shape_offset128','R3_reader_control8_LUT_resize_concat_inside_same_C5_RM','all_frozen_RP_physical_bits_and_directions_exact'):assert result[key],key
            stage=result['stage'];assert stage['exit_code']==0 and stage['all_owned_processes_terminal'] and stage['configured_limit_verified']
            assert not stage['resource_failure'] and not stage['elapsed_time_abort']
            for n,h in result['output_SHA256'].items():
                with view.stream(n) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==h,n
            for n,h in result['source_and_evidence_SHA256'].items():
                assert sha(ROOT/n)==h,n;assert view.original['workspace/'+n]==h,n
            assert stage['job_memory_limit_bytes']==24*1024**3
            expected_IPs=json.loads((HERE/'expected_IPs.json').read_text())
            inventory=json.loads(view.read(prefix+'IP_members_verified.json'))
            assert set(inventory)==set(expected_IPs['roles'])=={'ct_tensor_reader','ct_conv','ct_writer_pool'}
            for role,actual_IP in inventory.items():
                assert actual_IP['all_members_SHA256']==expected_IPs['roles'][role]['all_members_SHA256'],role
            ports=[]
            for line in view.read(prefix+'physical_ports.tsv').decode().splitlines():
                name,direction=line.split('\t');ports.append((name,{'IN':'input','OUT':'output','INOUT':'inout'}[direction.upper()]))
            expected=[]
            for direction,width,name in json.loads((ROOT/'dfx/medical/build/rp_ports.json').read_text()):
                if width:
                    a,b=map(int,re.fullmatch(r'\[(\d+):(\d+)\]',width).groups())
                    expected.extend((f'{name}[{i}]',direction) for i in range(min(a,b),max(a,b)+1))
                else:expected.append((name,direction))
            assert len(ports)==len(set(ports)) and set(ports)==set(expected)
            rpt=view.read('b/rm_ct_synth_util.rpt').decode(errors='replace')
            rows=[s for s in rpt.splitlines() if re.match(r'^\|\s*rm_medical\s*\|',s)];assert len(rows)==1
            values=[s.strip() for s in rows[0].split('|')[1:-1]];assert len(values)==11
            measured=dict(zip(('LUT','Logic_LUT','LUTRAM','SRL','FF','RAMB36','RAMB18','URAM','DSP'),map(int,values[2:])))
            assert measured==result['resources']
            log=view.read(prefix+'synthesis.log').decode(errors='replace');assert 'PASS complete C5 synthesis and physical port inventory' in log
        else:failure=json.loads(view.read(prefix+'failure.json'))
    proof=dict(status='actual_complete_C5_SYN_and_RP_independently_verified_not_route_or_board' if passed else 'actual_C5_SYN_failed_owned_evidence_preserved',
        actual_whole_C5_synthesis_qualified=passed,resources=None if result is None else result['resources'],
        physical_RP_bits=None if result is None else result['physical_RP_bit_count'],failure=failure,
        all_owned_bytes_and_closed_logs_verified_exact_root_absent=True,archive_SHA256=sha(archive),
        original_archive_metadata=receipt['original_archive_metadata'],
        still_requires_full_RTL100MHz_route_all5PR_ARM_board139_PS_speed_integration=True,
        source_and_evidence_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in (Path(__file__),HERE/'admission.json',
            OUT/'stream_collection_verified.json',OUT/'cleanup_verified_stream.json')},
        PL_accessed=False,production_promoted=False,whole_goal_completed=False)
    with target.open('x',encoding='utf-8') as f:json.dump(proof,f,indent=2)
    print(json.dumps(dict(qualified=passed,resources=proof['resources'],failure=None if failure is None else failure['traceback'][-1800:])),flush=True)

if __name__=='__main__':main()
