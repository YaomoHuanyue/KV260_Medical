"""Reopen all artifacts, IPX receipt, original four stages and exact40 RTL."""
from contextlib import ExitStack
from pathlib import Path
from datetime import datetime,timezone
import hashlib,io,json,sys,zipfile
import project_storage
ROOT=project_storage.SYSTEM;sys.path.insert(0,str(ROOT))
from modules.reconstruction.smooth_pipeline_r2.axis_fma3_area_r14.flow_RTL_r1.verify_collected import View
HERE=ROOT/'modules/segmentation/axis_tensor_reader_r3/IP_r2'
OUT=ROOT/'results/tensor_reader_R3_IP_R2_20261022_r1/axis_hls'

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    project_storage.check(1_000_000);assert not (OUT/'verified_PC.json').exists()
    receipt=json.loads((OUT/'stream_collection_verified.json').read_text());cleanup=json.loads((OUT/'cleanup_verified_stream.json').read_text())
    archive=OUT/'current_candidate.zip';assert sha(archive)==receipt['compact_archive_SHA256']
    assert cleanup['owned_root_confirmed_absent'] and cleanup['all_owned_member_bytes_and_closed_logs_stream_SHA_verified_locally']
    admission=json.loads((HERE/'admission.json').read_text());parent=json.loads((HERE/'parent_closed.json').read_text())
    assert parent['actual_RTL330_frames8resets_qualified'] and parent['all_four_actual_original_tool_stages_exit0']
    assert [s['stage'] for s in parent['actual_four_original_tool_stages']]==['csim_cli','csim_direct','hls','package']
    for stage in parent['actual_four_original_tool_stages']:
        v=stage['receipt'];assert v['exit_code']==0 and v['all_owned_processes_terminal'] and not v['resource_failure'] and not v['elapsed_time_abort']
    prefix='workspace/'+HERE.relative_to(ROOT).as_posix()+'/output/'
    with ExitStack() as st:
        view=View(st,archive)
        for n in sorted(set(view.names)|set(view.aliases)):
            with view.stream(n) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==view.original.get(n,view.names.get(n)),n
        obj=lambda n:json.loads(view.read(n))
        assert obj('terminal.json')['tool_gates_passed'];v=obj(prefix+'complete.json')
        assert v['actual_current_Vivado_IPX_exit0'] and v['all40_generated_and_exported_RTL_byte_identical_to_prior_HLS']
        assert v['four_original_actual_tool_stages_reused_not_reexecuted']
        assert v['exact_tool_added_simulation_monitors_removed_original_RTL_restored']
        assert v['source_SHA256']==admission['source_SHA256']
        for n,h in admission['source_SHA256'].items():assert sha(ROOT/n)==h,n
        actual=obj(prefix+'refresh_receipt.json');assert actual['exit_code']==0 and actual['all_owned_processes_terminal'] and actual['configured_limit_verified']
        assert not actual['resource_failure'] and not actual['elapsed_time_abort']
        log=view.read(prefix+'refresh.log').decode(errors='replace')
        assert 'PASS R3_READER_CANONICAL_IPX_CHECKSUMS' in log and 'ERROR:' not in log
        data=view.read(prefix+'export.zip');assert hashlib.sha256(data).hexdigest()==v['export']['archive_SHA256']
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            assert len(z.namelist())==len(set(z.namelist()))
            for n,h in v['export']['all_members_SHA256'].items():assert hashlib.sha256(z.read(n)).hexdigest()==h,n
            for leaf,h in parent['expected_RTL_SHA256'].items():assert hashlib.sha256(z.read('hdl/verilog/'+leaf)).hexdigest()==h,leaf
            assert len([n for n in parent['expected_RTL_SHA256'] if n.endswith('.v')])==40
        assert set(v['changed_package_members'])<=set(('component.xml','hdl/verilog/ct_tensor_reader.v'))
        registers=v['export']['registers'];assert all(registers.get(n)==off for n,off in [('height',32),('width',40),('cin',48),
            ('kernel',56),('mode',96),('channels_a',104),('channels_b',112),('factor_a',120),('factor_b',128),('status',136)])
    result=dict(UTC=datetime.now(timezone.utc).isoformat(),actual_Vivado_IPX_checksum_refresh_and_integrity_passed=True,
        all40_exported_RTL_exact_full330_frame8reset_qualified_R3=True,
        only_exact_tool_added_simulation_monitor_injection_removed_and_XML_checksums_refreshed=True,
        prior_four_actual159_AP_Csim_HLS_package_stages_reused_not_rerun=True,
        every_retained_export_and_artifact_reopened_full_SHA=True,all_owned_server_files_collected_exact_root_removed=True,
        archive_SHA256=sha(archive),export_SHA256=v['export']['archive_SHA256'],export_member=prefix+'export.zip',
        control_registers=registers,current_IPX_seconds=actual['elapsed_s'],current_IPX_peak_job_bytes=actual['reported_peak_job_bytes'],
        source_and_evidence_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),HERE/'run.py',HERE/'admission.json',HERE/'collect.py',HERE/'parent_closed.json',HERE/'refresh.tcl']},
        whole_C5_100MHz_all5PR_ARM139_system_integration_still_required=True,
        PL_accessed=False,production_promoted=False,whole_goal_completed=False)
    with (OUT/'verified_PC.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print('PASS actual IPX integrity, every40 original tested RTL exact, all owned files collected; C5 physical/board remains')

if __name__=='__main__':main()
