"""Reuse the closed actual package; restore only proven tool-added monitor text."""
from pathlib import Path
from contextlib import ExitStack
import argparse,hashlib,io,json,sys,zipfile
import project_storage
import start_tensor_R3_IP_20261022_r1 as parent
ROOT=project_storage.SYSTEM;sys.path.insert(0,str(ROOT))
from modules.reconstruction.smooth_pipeline_r2.axis_fma3_area_r14.flow_RTL_r1.verify_collected import View
HERE=ROOT/'modules/segmentation/axis_tensor_reader_r3/IP_r2'
OUT=ROOT/'results/tensor_reader_R3_IP_R2_20261022_r1/axis_hls'
OLD=ROOT/'results/tensor_reader_R3_IP_20261022_r1/axis_hls'

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def prepare(recipe):
    project_storage.check(2_000_000);assert not OUT.exists() and not (HERE/'admission.json').exists()
    assert json.loads((OLD/'cleanup_verified_stream.json').read_text())['owned_root_confirmed_absent']
    old=OLD/'current_candidate.zip';receipt=json.loads((OLD/'stream_collection_verified.json').read_text())
    assert sha(old)==receipt['compact_archive_SHA256']
    rtl=ROOT/'results/tensor_reader_R3_RTL_20261022_r1/axis_rtl/verified_PC.json'
    assert json.loads(rtl.read_text())['all330_full_frames_and8_actual_global_resets_verified']
    with ExitStack() as st:
        view=View(st,old)
        for n in sorted(set(view.names)|set(view.aliases)):
            with view.stream(n) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==view.original.get(n,view.names.get(n)),n
        prefix='workspace/modules/segmentation/axis_tensor_reader_r3/HLS_r1/output/'
        raw=view.read(prefix+'export.zip');pristine=view.read('h/tensor/hls/syn/verilog/ct_tensor_reader.v')
        terminal=json.loads(view.read('terminal.json'));assert not terminal['tool_gates_passed']
        fail=json.loads(view.read('workspace/modules/segmentation/axis_tensor_reader_r3/IP_r1/output/failure.json'))
        assert "Export differs from exact tested RTL" in fail['traceback']
        stages=[]
        for leaf in ('csim_cli','csim_direct','hls'):
            v=json.loads(view.read(prefix+leaf+'_receipt.json'))
            assert v['exit_code']==0 and v['all_owned_processes_terminal'] and not v['resource_failure']
            stages.append(dict(stage=leaf,receipt=v))
        v=json.loads(view.read('workspace/modules/segmentation/axis_tensor_reader_r3/IP_r1/output/package_receipt.json'))
        assert v['exit_code']==0 and v['all_owned_processes_terminal'] and not v['resource_failure'];stages.append(dict(stage='package',receipt=v))
        expected=json.loads((HERE.parent/'RTL_r1/admission.json').read_text())['generated_RTL_SHA256']
        assert hashlib.sha256(pristine).hexdigest()==expected['ct_tensor_reader.v']
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            members={n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if not z.getinfo(n).is_dir()}
            differences=[leaf for leaf,h in expected.items() if members['hdl/verilog/'+leaf]!=h]
            assert differences==['ct_tensor_reader.v']
            end=b'endmodule //ct_tensor_reader\r\n'
            injection=(b'\r\nreg find_df_deadlock = 0;\r\n// synthesis translate_off\r\n'
                b'`include "ct_tensor_reader_hls_deadlock_detector.vh"\r\n// synthesis translate_on\r\n\r\n'
                b'reg find_kernel_block = 0;\r\n// synthesis translate_off\r\n'
                b'`include "ct_tensor_reader_hls_deadlock_kernel_monitor_top.vh"\r\n// synthesis translate_on\r\n\r\n')
            assert pristine.endswith(end) and z.read('hdl/verilog/ct_tensor_reader.v')==pristine[:-len(end)]+injection+end+b'\r\n'
    parent.jobs.write(HERE/'parent_closed.json',dict(all_four_actual_original_tool_stages_exit0=True,
        only_exact_tool_simulation_monitor_injection_differs=True,actual_RTL330_frames8resets_qualified=True,
        actual_four_original_tool_stages=stages,raw_export_members_SHA256=members,expected_RTL_SHA256=expected,
        exact_added_bytes_hex=injection.hex(),closed_parent_archive_SHA256=sha(old),
        original_failed_checker_record_preserved=True,whole_goal_completed=False))
    paths=[Path(__file__),HERE/'run.py',HERE/'refresh.tcl',HERE/'parent_closed.json',HERE.parent/'IP_r1/run.py',rtl,
        OLD/'stream_collection_verified.json',OLD/'cleanup_verified_stream.json',ROOT/'dfx/navigation_profile/rtl_r74/job_limit_r74.py']
    bindings={p.relative_to(ROOT).as_posix():sha(p) for p in paths}
    artifacts={'payload/raw_export.zip':hashlib.sha256(raw).hexdigest(),'payload/syn_top.v':hashlib.sha256(pristine).hexdigest()}
    parent.jobs.write(HERE/'admission.json',dict(source_SHA256=bindings,artifact_SHA256=artifacts,
        exact_prior_full159_HLS_package_and330_RTL_scope_preserved=True,whole_goal_completed=False))
    paths.append(HERE/'admission.json');OUT.mkdir(parents=True);parent.jobs.write(OUT/'recipe.json',recipe)
    manifest={'workspace/'+p.relative_to(ROOT).as_posix():sha(p) for p in paths}
    payload={'payload/raw_export.zip':raw,'payload/syn_top.v':pristine}
    manifest.update({'workspace/'+HERE.relative_to(ROOT).as_posix()+'/'+n:h for n,h in artifacts.items()})
    with zipfile.ZipFile(OUT/'input.zip','x',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for p in paths:z.write(p,'workspace/'+p.relative_to(ROOT).as_posix())
        for n,b in payload.items():z.writestr('workspace/'+HERE.relative_to(ROOT).as_posix()+'/'+n,b)
        z.writestr('input_manifest.json',json.dumps(manifest))
    parent.jobs.write(OUT/'plan.json',dict(job='axis_hls',kind='tensor_reader_IP',cwd='workspace',
        runner=(HERE/'run.py').relative_to(ROOT).as_posix(),output=(HERE/'output').relative_to(ROOT).as_posix(),
        own_worker_affinity_mask=61440,max_threads=4,required_free_commit_GiB=16,required_physical_GiB=8,
        timeout_abort=False,input_manifest=manifest,input_archive_sha256=sha(OUT/'input.zip')))
    print('PASS actual closed full159/package and330RTL bound; exact monitor-only restoration prepared')

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','launch','snapshot']);a=p.parse_args()
    parent.HERE=HERE;parent.OUT=OUT;recipe=parent.configure()
    if a.action=='prepare':prepare(recipe)
    elif a.action=='snapshot':parent.jobs.snapshot('axis_hls')
    else:
        project_storage.check(1_000_000)
        for n,h in json.loads((HERE/'admission.json').read_text())['source_SHA256'].items():assert sha(ROOT/n)==h,n
        parent.jobs.launch('axis_hls')

if __name__=='__main__':main()
