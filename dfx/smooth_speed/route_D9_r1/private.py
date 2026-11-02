"""Admit and dispatch offline D9 PR with direct immutable inputs, no PC bulk copy."""
from pathlib import Path
import argparse
import ast
import importlib.util
import inspect
import json
import sys
import zipfile

import preflight
from check_reports import REFERENCES, sha

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / 'results/smooth_AXIS_D9_PR_r1/smooth'
sys.path.insert(0, str(ROOT / 'tools'))
import project_storage


def supplemental():
    result = {'area_source.zip': ROOT / 'results/smooth_AXIS_D9_tile1024_area_r2/smooth_area/current_candidate_dedup_r1.zip',
              'static_source.dcp': ROOT / 'dfx/medical/build/static_routed.dcp'}
    result.update({'reference_' + ref + '_source.dcp': ROOT / ('dfx/medical/build/config_' + ref + '.dcp')
                   for ref in REFERENCES})
    return result


def configure():
    spec = importlib.util.spec_from_file_location('D9_owned_offline_dispatch', ROOT / 'modules/reconstruction/smooth_pipeline_r2/area_dispatch_short_r3.py')
    dispatch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dispatch)
    dispatch.BASE = OUT.parent
    dispatch.selected_out = lambda job: OUT if job == 'smooth' else None
    branch = """ elif plan['kind']=='D9_offline_route':
  accepted=json.loads((cwd/plan['output']/'complete.json').read_text())
  assert accepted['actual_same_version_100MHz_route_and_five_reference_fullPR_passed']
  assert accepted['all_five_firmware_artifacts_present']
  assert accepted['original_Windows_native_Csim_full14_monitors_and40_flow_gates_preserved']
  assert accepted['ARM_XRT_and_board_PS4_still_required']
  assert not accepted['PL_accessed'] and not accepted['production_promoted'] and not accepted['whole_goal_completed']
  for n,h in accepted['source_and_evidence_SHA256'].items():assert sha(cwd/n)==h,n
"""
    source = dispatch.WORKER
    edits = [("('smooth_full_HLS','smooth_area_probe')", "('smooth_full_HLS','smooth_area_probe','D9_offline_route')"),
             (" elif plan['kind']=='smooth_area_probe':", branch + " elif plan['kind']=='smooth_area_probe':")]
    for before, after in edits:
        assert source.count(before) == 1
        source = source.replace(before, after)
    ast.parse(source)
    dispatch.WORKER = source
    launch = inspect.getsource(dispatch.launch)
    anchor = "    write(src / 'manifest.json', {n: sha(p) for n, p in entries.items()})"
    assert launch.count(anchor) == 1
    launch = launch.replace(anchor, '    entries.update(D9_DIRECT_SUPPLEMENTAL)\n' + anchor)
    dispatch.D9_DIRECT_SUPPLEMENTAL = supplemental()
    exec(compile(launch, str(Path(__file__)) + ':owned_launcher_with_direct_immutable_payloads', 'exec'), dispatch.__dict__)
    return dispatch


def prepare():
    project_storage.check(130_000_000)
    admission = preflight.admit()
    assert not OUT.exists()
    payloads = supplemental()
    admission['direct_payloads'] = {name: dict(SHA256=sha(path), workspace_path=path.relative_to(ROOT).as_posix())
                                    for name, path in payloads.items()}
    files = [HERE / name for name in ('private.py', 'run.py', 'check_reports.py', 'implement_D9_r1.tcl', 'preflight.py')]
    files.append(ROOT / 'tools/collect_D9_route_r1.py')
    assert all(path.is_file() for path in files)
    OUT.mkdir(parents=True)
    archive = OUT / 'input.zip'
    manifest = {}
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=1) as output:
        for path in files:
            name = 'workspace/' + path.relative_to(ROOT).as_posix()
            output.write(path, name)
            manifest[name] = sha(path)
        name = 'workspace/' + (HERE / 'input/admission_verified.json').relative_to(ROOT).as_posix()
        raw = (json.dumps(admission, indent=2) + '\n').encode()
        output.writestr(name, raw)
        manifest[name] = __import__('hashlib').sha256(raw).hexdigest()
        output.writestr('input_manifest.json', json.dumps(manifest, sort_keys=True))
    plan = dict(job='smooth', kind='D9_offline_route', cwd='workspace',
        runner=(HERE / 'run.py').relative_to(ROOT).as_posix(), output=HERE.relative_to(ROOT).as_posix(),
        required_free_commit_GiB=32, required_physical_GiB=24,
        own_worker_affinity_mask=15, max_logical_processors=4, job_memory_limit_GiB=32,
        timeout_abort=False, input_manifest=manifest, input_archive_sha256=sha(archive),
        input_archive_bytes=archive.stat().st_size, direct_payloads=admission['direct_payloads'],
        no_new_local_bulk_payload_copy=True, ARM_XRT_board_PS4_and_release_still_required=True,
        production_promoted=False, whole_goal_completed=False)
    for name, value in (('admission.json', admission), ('plan.json', plan)):
        with (OUT / name).open('x', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
    print('PASS admitted offline D9 route inputs prepared; large inputs reused directly, no board promotion')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('inspect', 'prepare', 'launch', 'snapshot'))
    args = parser.parse_args()
    dispatch = configure()
    if args.action == 'inspect':
        proof = preflight.inspect()
        print(json.dumps(dict(status=proof['status'], admitted=proof['offline_route_admitted'],
                              pending=proof['pending_before_start'], worker_syntax_checked=True,
                              no_remote_mutation=True), indent=2))
    elif args.action == 'prepare':
        prepare()
    elif args.action == 'launch':
        project_storage.check(130_000_000)
        current = preflight.admit()
        planned = json.loads((OUT / 'admission.json').read_text())
        assert all(planned[key] == value for key, value in current.items())
        dispatch.launch('smooth')
    else:
        dispatch.snapshot('smooth')
