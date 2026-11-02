"""Transfer only exact40RTL and a bounded full-frame test; no bulk extraction."""
from pathlib import Path
from contextlib import ExitStack
import argparse,ast,hashlib,inspect,json,sys,zipfile
import project_storage,server2_private_jobs_r2450 as jobs
ROOT=project_storage.SYSTEM;sys.path.insert(0,str(ROOT))
HERE=ROOT/'modules/segmentation/axis_tensor_reader_r3/RTL_r1'
OUT=ROOT/'results/tensor_reader_R3_RTL_20261022_r1/axis_rtl'
SOURCE=ROOT/'results/tensor_reader_R3_HLS_20261022_r1/axis_hls/current_candidate.zip'
from modules.reconstruction.smooth_pipeline_r2.axis_fma3_area_r14.flow_RTL_r1.verify_collected import View

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def configure():
    jobs.BASE=OUT.parent;jobs.selected_out=lambda n:OUT if n=='axis_rtl' else None
    branch=""" elif plan['kind']=='tensor_reader_full_RTL':
  accepted=json.loads((cwd/plan['output']/'complete.json').read_text())
  assert accepted['original142_valid17_invalid_full_domains_in_both_schedules']
  assert accepted['all330_complete_frames_and8_actual_global_resets']
  assert accepted['full_packet_data_keep_strb_last_padding_and_no_trailing_contamination_checked']
  assert accepted['AXI_read_bounds_lowDDR_4K_ID_response_and_no_writes_checked']
  assert accepted['AXI_AXIL_AXIS_holds_checked']
  assert len(accepted['actual_stages'])==8 and all(r['receipt']['exit_code']==0 for r in accepted['actual_stages'])
  for n,h in accepted['source_SHA256'].items():assert sha(cwd/n)==h,n
  assert not accepted['PL_accessed'] and not accepted['production_promoted'] and not accepted['whole_goal_completed']
"""
    edits=[("('smooth_full_HLS','smooth_full_RTL')","('smooth_full_HLS','smooth_full_RTL','tensor_reader_full_RTL')"),
        (" elif plan['kind']=='smooth_full_HLS':",branch+" elif plan['kind']=='smooth_full_HLS':")]
    original=jobs.WORKER;body=original
    for a,b in edits:assert body.count(a)==1;body=body.replace(a,b)
    reverse=body
    for a,b in reversed(edits):reverse=reverse.replace(b,a)
    assert reverse==original;ast.parse(body);jobs.WORKER=body
    source=inspect.getsource(jobs.launch)
    before="            with s.open(remote + '/release.json', 'wx') as f:\n                f.write(json.dumps(dict(verified_worker_PID=created['PID'])))"
    after="            with s.open(remote + '/release.pending', 'wx') as f:\n                f.write(json.dumps(dict(verified_worker_PID=created['PID'])))\n            s.rename(remote + '/release.pending',remote + '/release.json')"
    assert source.count(before)==1;changed=source.replace(before,after);assert changed.replace(after,before)==source
    exec(compile(changed,str(Path(__file__))+':atomic_owned_release','exec'),jobs.__dict__)
    return dict(worker_literal_edits=edits,atomic_release_edit=[before,after],exact_reverse_verified=True,
        child_memory_GiB=8,own_logical_cores=[8,9,10,11],separate_from_refill_cores=[0,1,2,3],max_threads=4,
        actual_full159_each_schedule_and4_resets_per_schedule_required=True,elapsed_time_abort=False)

def prepare(recipe):
    project_storage.check(4_000_000);assert not OUT.exists() and not (HERE/'admission.json').exists()
    proof_path=SOURCE.with_name('verified_PC.json');proof=json.loads(proof_path.read_text())
    assert proof['actual_CLI_Csim_exit0'] and proof['actual_direct_AP_Csim_exit0'] and proof['actual_HLS_exit0']
    assert proof['actual_generated_Verilog_modules']==40 and proof['all_generated_RTL_and_initializers_SHA256_read']
    assert proof['actual142_valid17_invalid_full_frame_data_sidebands_padding_guards_exact']
    preflight=json.loads((HERE/'preflight_r3/verified.json').read_text());assert preflight['both_full159_harness_syntax_compilations_passed']
    for p in [proof,preflight]:
        for n,h in p.get('source_and_evidence_SHA256',p.get('source_SHA256',{})).items():assert sha(ROOT/n)==h,n
    hold=ROOT/'modules/reconstruction/mesh_topology_r1/rank_cache_URAM_r9/full_RTL_memory_init_r2/hold.sv'
    paths=[Path(__file__),proof_path,HERE/'preflight_r3/verified.json',HERE/'generate.py',HERE/'run.py',HERE/'testbench.sv.in',HERE/'build_sim.tcl',
        HERE.parent/'native_verified.json',hold,ROOT/'dfx/navigation_profile/rtl_r74/job_limit_r74.py']
    for mode in ('ordinary','random'):
        paths += [HERE/'preflight_r3'/mode/n for n in ('tb.sv','model_lut.hex','harness_contract.json','compile_receipt.json')]
    bindings={p.relative_to(ROOT).as_posix():sha(p) for p in paths};assets={};payload={}
    with ExitStack() as stack:
        view=View(stack,SOURCE)
        for name in sorted(set(view.names)|set(view.aliases)):
            if name.startswith('h/tensor/hls/syn/verilog/'):
                raw=view.read(name);leaf=Path(name).name;assert leaf not in assets
                assets[leaf]=hashlib.sha256(raw).hexdigest();payload[leaf]=raw
    assert len([n for n in assets if n.endswith('.v')])==40
    jobs.write(HERE/'admission.json',dict(source_SHA256=bindings,generated_RTL_SHA256=assets,
        source_HLS_archive_SHA256=sha(SOURCE),hold_source=hold.relative_to(ROOT).as_posix(),
        full330_frames8_resets_required=True,whole_goal_completed=False))
    paths.append(HERE/'admission.json');OUT.mkdir(parents=True);jobs.write(OUT/'recipe.json',recipe)
    manifest={'workspace/'+p.relative_to(ROOT).as_posix():sha(p) for p in paths}
    manifest.update({'workspace/'+HERE.relative_to(ROOT).as_posix()+'/source_RTL/'+n:h for n,h in assets.items()})
    with zipfile.ZipFile(OUT/'input.zip','x',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for p in paths:z.write(p,'workspace/'+p.relative_to(ROOT).as_posix())
        for n,raw in payload.items():z.writestr('workspace/'+HERE.relative_to(ROOT).as_posix()+'/source_RTL/'+n,raw)
        z.writestr('input_manifest.json',json.dumps(manifest))
    assert (OUT/'input.zip').stat().st_size<2_000_000
    jobs.write(OUT/'plan.json',dict(job='axis_rtl',kind='tensor_reader_full_RTL',cwd='workspace',
        runner=(HERE/'run.py').relative_to(ROOT).as_posix(),output=HERE.relative_to(ROOT).as_posix(),
        own_worker_affinity_mask=3840,max_threads=4,required_free_commit_GiB=16,required_physical_GiB=8,
        timeout_abort=False,input_manifest=manifest,input_archive_sha256=sha(OUT/'input.zip'),
        local_peak_reservation_bytes=4_000_000,other_user_files_and_processes_unchanged=True))
    print('PASS exact40RTL/full159 test package prepared; no RTL execution claimed')

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','launch','snapshot']);a=p.parse_args();recipe=configure()
    if a.action=='snapshot':jobs.snapshot('axis_rtl');return
    if a.action=='prepare':prepare(recipe);return
    project_storage.check(2_000_000)
    admission=json.loads((HERE/'admission.json').read_text())
    for n,h in admission['source_SHA256'].items():assert sha(ROOT/n)==h,n
    jobs.launch('axis_rtl')

if __name__=='__main__':main()
