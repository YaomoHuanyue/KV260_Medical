"""Restore the exact RTL-tested top, then perform actual Vivado IPX validation."""
from pathlib import Path,PurePosixPath
import hashlib,importlib.util,json,os,stat,sys,traceback,zipfile
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'dfx/navigation_profile/rtl_r74'))
from job_limit_r74 import run,system_memory

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def save(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,indent=2)

def main():
    admission=json.loads((HERE/'admission.json').read_text());bindings=admission['source_SHA256']
    def verify():
        for n,h in bindings.items():assert sha(ROOT/n)==h,n
        for n,h in admission['artifact_SHA256'].items():assert sha(HERE/n)==h,n
    verify();assert os.name=='nt' and not (HERE/'output').exists();(HERE/'output').mkdir()
    memory=system_memory();assert memory['free_commit_bytes']>=16*1024**3 and memory['physical_available_bytes']>=8*1024**3
    parent=json.loads((HERE/'parent_closed.json').read_text());assert parent['all_four_actual_original_tool_stages_exit0']
    assert parent['only_exact_tool_simulation_monitor_injection_differs'] and parent['actual_RTL330_frames8resets_qualified']
    owned=ROOT.parent;destination=owned/'i/tensor';assert not destination.exists();destination.mkdir(parents=True)
    raw=HERE/'payload/raw_export.zip';top=HERE/'payload/syn_top.v'
    try:
        with zipfile.ZipFile(raw) as z:
            for info in z.infolist():
                p=PurePosixPath(info.filename.rstrip('/'))
                assert not p.is_absolute() and '\\' not in info.filename and ':' not in info.filename and '..' not in p.parts
                assert not stat.S_ISLNK(info.external_attr>>16)
                if info.is_dir():continue
                target=destination/p;assert target.resolve().is_relative_to(destination.resolve())
                target.parent.mkdir(parents=True,exist_ok=True);data=z.read(info)
                assert hashlib.sha256(data).hexdigest()==parent['raw_export_members_SHA256'][info.filename]
                with target.open('xb') as f:f.write(data)
            original=top.read_bytes();end=b'endmodule //ct_tensor_reader\r\n'
            assert original.endswith(end)
            injection=bytes.fromhex(parent['exact_added_bytes_hex'])
            assert z.read('hdl/verilog/ct_tensor_reader.v')==original[:-len(end)]+injection+end+b'\r\n'
        (destination/'hdl/verilog/ct_tensor_reader.v').write_bytes(original)
        out=HERE/'output'
        receipt=run([str(Path('D:/AMDDesignTools/2025.2.1/Vivado/bin/vivado.bat')),'-mode','batch','-notrace',
            '-source',str(HERE/'refresh.tcl'),'-log',str(out/'vivado.log'),'-journal',str(out/'vivado.jou')],
            cwd=owned,env=dict(os.environ,PROCESSOR_ARCHITECTURE='AMD64',PYTHONUTF8='1',R3_READER_IP_ROOT=destination.as_posix()),
            log=out/'refresh.log',started=out/'refresh_started.json',limit=8*1024**3)
        save(out/'refresh_receipt.json',receipt)
        assert receipt['exit_code']==0 and receipt['all_owned_processes_terminal'] and receipt['configured_limit_verified']
        assert not receipt['resource_failure'] and not receipt['elapsed_time_abort']
        assert 'PASS R3_READER_CANONICAL_IPX_CHECKSUMS' in (out/'refresh.log').read_text(errors='replace')
        package=out/'export.zip'
        with zipfile.ZipFile(raw) as source,zipfile.ZipFile(package,'x',zipfile.ZIP_DEFLATED,compresslevel=1) as target:
            for info in source.infolist():
                if info.is_dir():target.writestr(info,b'');continue
                data=(destination/info.filename).read_bytes() if info.filename in ('component.xml','hdl/verilog/ct_tensor_reader.v') else source.read(info)
                target.writestr(info,data)
        spec=importlib.util.spec_from_file_location('original_strict_R3_export_checks',ROOT/'modules/segmentation/axis_tensor_reader_r3/IP_r1/run.py')
        checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
        exported=checker.package_proof(package,parent['expected_RTL_SHA256'])
        changes=[n for n,h in exported['all_members_SHA256'].items() if h!=parent['raw_export_members_SHA256'][n]]
        assert set(exported['all_members_SHA256'])==set(parent['raw_export_members_SHA256'])
        assert set(changes)<=set(('component.xml','hdl/verilog/ct_tensor_reader.v')) and 'hdl/verilog/ct_tensor_reader.v' in changes
        verify()
        save(out/'complete.json',dict(status='actual_IPX_verified_exact_RTL330_tested_R3_reader',
            actual_full159_CLI_and_direct_AP_HLS_and_package_exit0=True,
            four_original_actual_tool_stages_reused_not_reexecuted=True,actual_current_Vivado_IPX_exit0=True,
            all40_generated_and_exported_RTL_byte_identical_to_prior_HLS=True,
            original_control_offsets_through_status136_and_input_skip_LUT_pointers_verified=True,
            exact_tool_added_simulation_monitors_removed_original_RTL_restored=True,
            changed_package_members=changes,export=exported,export_path=package.relative_to(ROOT).as_posix(),
            source_SHA256=bindings,parent_actual_stages=parent['actual_four_original_tool_stages'],
            current_refresh_receipt=receipt,whole_C5_100MHz_all5PR_ARM139_system_integration_pending=True,
            PL_accessed=False,production_promoted=False,whole_goal_completed=False))
        print('PASS actual IPX checksums and every40 exact RTL; no whole-C5/board claim',flush=True)
    except BaseException:
        save(HERE/'output/failure.json',dict(traceback=traceback.format_exc(),source_SHA256=bindings,whole_goal_completed=False));raise

if __name__=='__main__':main()
