"""Own four cores12--15, reuse the strict159 HLS flow and export only this IP."""
from pathlib import Path
import argparse,ast,hashlib,inspect,json,zipfile
import project_storage,server2_private_jobs_r2450 as jobs
ROOT=project_storage.SYSTEM;HERE=ROOT/'modules/segmentation/axis_tensor_reader_r3/IP_r1'
HLS=HERE.parent/'HLS_r1';OUT=ROOT/'results/tensor_reader_R3_IP_20261022_r1/axis_hls'

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def configure():
    jobs.BASE=OUT.parent;jobs.selected_out=lambda n:OUT if n=='axis_hls' else None
    branch=""" elif plan['kind']=='tensor_reader_IP':
  accepted=json.loads((cwd/plan['output']/'complete.json').read_text())
  assert accepted['actual_full159_CLI_and_direct_AP_HLS_and_package_exit0']
  assert accepted['all40_generated_and_exported_RTL_byte_identical_to_prior_HLS']
  assert accepted['original_control_offsets_through_status136_and_input_skip_LUT_pointers_verified']
  assert sha(cwd/accepted['export_path'])==accepted['export']['archive_SHA256']
  for n,h in accepted['source_SHA256'].items():assert sha(cwd/n)==h,n
  assert not accepted['PL_accessed'] and not accepted['production_promoted'] and not accepted['whole_goal_completed']
"""
    edits=[("('smooth_full_HLS','smooth_full_RTL')","('smooth_full_HLS','smooth_full_RTL','tensor_reader_IP')"),
        (" elif plan['kind']=='smooth_full_HLS':",branch+" elif plan['kind']=='smooth_full_HLS':")]
    body=jobs.WORKER
    for a,b in edits:assert body.count(a)==1;body=body.replace(a,b)
    reverse=body
    for a,b in reversed(edits):reverse=reverse.replace(b,a)
    assert reverse==jobs.WORKER;ast.parse(body);jobs.WORKER=body
    source=inspect.getsource(jobs.launch)
    a="            with s.open(remote + '/release.json', 'wx') as f:\n                f.write(json.dumps(dict(verified_worker_PID=created['PID'])))"
    b="            with s.open(remote + '/release.pending', 'wx') as f:\n                f.write(json.dumps(dict(verified_worker_PID=created['PID'])))\n            s.rename(remote + '/release.pending',remote + '/release.json')"
    assert source.count(a)==1;changed=source.replace(a,b);assert changed.replace(b,a)==source
    exec(compile(changed,str(Path(__file__))+':atomic_owned_release','exec'),jobs.__dict__)
    return dict(worker_literal_edits=edits,atomic_release_literal_edit=[a,b],exact_reverse_verified=True,
        own_logical_cores=[12,13,14,15],max_threads=4,child_memory_GiB=8,
        no_existing_server_job_changed=True,no_elapsed_time_abort=True)

def prepare(recipe):
    project_storage.check(2_000_000);assert not OUT.exists() and not (HERE/'admission.json').exists()
    parent=json.loads((HLS/'admission.json').read_text());paths={n:ROOT/n for n in parent['source_SHA256']}
    for n,h in parent['source_SHA256'].items():assert sha(paths[n])==h,n
    for p in [Path(__file__),HERE/'run.py',HLS/'admission.json',HERE.parent/'RTL_r1/admission.json']:
        paths[p.relative_to(ROOT).as_posix()]=p
    bindings={n:sha(p) for n,p in paths.items()}
    expected=json.loads((HERE.parent/'RTL_r1/admission.json').read_text())['generated_RTL_SHA256']
    assert len([n for n in expected if n.endswith('.v')])==40
    jobs.write(HERE/'admission.json',dict(source_SHA256=bindings,expected_RTL_SHA256=expected,
        same_original159_CLI_direct_AP_HLS_and_export_required=True,
        standalone_packaging_not_whole_C5_or_board_qualification=True,whole_goal_completed=False))
    paths[(HERE/'admission.json').relative_to(ROOT).as_posix()]=HERE/'admission.json'
    OUT.mkdir(parents=True);jobs.write(OUT/'recipe.json',recipe)
    manifest={'workspace/'+n:sha(p) for n,p in paths.items()}
    with zipfile.ZipFile(OUT/'input.zip','x',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for n,p in paths.items():z.write(p,'workspace/'+n)
        z.writestr('input_manifest.json',json.dumps(manifest))
    assert (OUT/'input.zip').stat().st_size<300_000
    jobs.write(OUT/'plan.json',dict(job='axis_hls',kind='tensor_reader_IP',cwd='workspace',
        runner=(HERE/'run.py').relative_to(ROOT).as_posix(),output=(HERE/'output').relative_to(ROOT).as_posix(),
        own_worker_affinity_mask=61440,max_threads=4,required_free_commit_GiB=16,required_physical_GiB=8,
        timeout_abort=False,input_manifest=manifest,input_archive_sha256=sha(OUT/'input.zip')))
    print('PASS strict159/same40RTL IP packaging task prepared; no IP result claimed')

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','launch','snapshot']);a=p.parse_args();recipe=configure()
    if a.action=='snapshot':jobs.snapshot('axis_hls');return
    if a.action=='prepare':prepare(recipe);return
    project_storage.check(1_000_000)
    for n,h in json.loads((HERE/'admission.json').read_text())['source_SHA256'].items():assert sha(ROOT/n)==h,n
    jobs.launch('axis_hls')

if __name__=='__main__':main()
