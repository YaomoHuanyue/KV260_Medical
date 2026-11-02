"""Launch two independent, owned SSH2 jobs; never alter existing server files."""
from pathlib import Path, PureWindowsPath
import argparse, hashlib, json, sys, time, uuid
import paramiko

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'results/smooth_pipeline_r2_area_private_r3'
sys.path.insert(0, str(ROOT / 'tools'))
from server2_transport_r2228 import connect, command
from run_server2_navigation_PR_r2233 import process


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def write(p, value):
    with p.open('x', encoding='utf8') as f:
        json.dump(value, f, indent=2); f.write('\n')


def selected_out(job):
    assert job in ('smooth', 'heatmap', 'c9', 'smooth_hls', 'smooth_area')
    return BASE / job


WORKER = r'''from pathlib import Path, PurePosixPath
import hashlib,importlib.util,json,os,stat,sys,time,traceback,zipfile
root=Path(__file__).resolve().parent
assert hashlib.sha256((root/'owned_windows_paths_r2418.py').read_bytes()).hexdigest()==json.loads((root/'manifest.json').read_text())['owned_windows_paths_r2418.py']
from owned_windows_paths_r2418 import install as install_owned_paths
Path=install_owned_paths(root);root=Path(str(root))
sys.stdin=open('NUL','r')
sys.stdout=open(root/'stdout.log','a',encoding='utf8',buffering=1)
sys.stderr=open(root/'stderr.log','a',encoding='utf8',buffering=1)
from job_limit_r74 import run,system_memory
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def write(p,v):
 with p.open('x',encoding='utf8') as f:json.dump(v,f,indent=2);f.write('\n')
def state(**kw):
 p=root/'state.new'
 with p.open('w',encoding='utf8') as f:json.dump(dict(PID=os.getpid(),**kw),f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(p,root/'state.json')
owner=json.loads((root/'owner.json').read_text());plan=json.loads((root/'plan.json').read_text())
assert root==Path(owner['windows_root']).resolve() and root.name==owner['name'] and owner['job']==plan['job']
manifest=json.loads((root/'manifest.json').read_text())
if plan['kind'] in ('smooth_full_HLS','smooth_area_probe'):
 import ctypes
 api=ctypes.WinDLL('kernel32',use_last_error=True)
 api.GetCurrentProcess.restype=ctypes.c_void_p
 api.GetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.POINTER(ctypes.c_size_t)]
 api.SetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
 handle=api.GetCurrentProcess();mask=plan['own_worker_affinity_mask'];before=ctypes.c_size_t();system=ctypes.c_size_t()
 assert api.GetProcessAffinityMask(handle,ctypes.byref(before),ctypes.byref(system))
 assert system.value&mask==mask and mask.bit_count()==4
 assert api.SetProcessAffinityMask(handle,mask)
 after=ctypes.c_size_t();assert api.GetProcessAffinityMask(handle,ctypes.byref(after),ctypes.byref(system)) and after.value==mask
 write(root/'own_worker_affinity.json',dict(PID=os.getpid(),own_worker_only=True,before_mask=before.value,actual_mask=after.value,logical_processors=4,server_global_configuration_changed=False))
for n,h in manifest.items():assert sha(root/n)==h,n
write(root/'worker_started.json',dict(PID=os.getpid(),inputs_sha256_verified=True,root=str(root)))
state(stage='awaiting_verified_release',job=plan['job'])
while not(root/'release.json').exists():time.sleep(.2)
assert json.loads((root/'release.json').read_text())['verified_worker_PID']==os.getpid()
failure=None;receipt=None
try:
 assert sha(root/'input.zip')==plan['input_archive_sha256']
 with zipfile.ZipFile(root/'input.zip') as z:
  inputs=json.loads(z.read('input_manifest.json'));assert inputs==plan['input_manifest']
  assert set(z.namelist())==set(inputs)|{'input_manifest.json'} and len(z.namelist())==len(set(z.namelist()))
  for n,h in inputs.items():
   p=PurePosixPath(n)
   assert not p.is_absolute() and p.as_posix()==n and '\\' not in n and ':' not in n and all(c not in ('','.','..') for c in n.split('/'))
   assert not stat.S_ISLNK(z.getinfo(n).external_attr>>16)
   dest=root.joinpath(*p.parts);assert dest.resolve().is_relative_to(root.resolve()) and not dest.exists()
   dest.parent.mkdir(parents=True,exist_ok=True)
   with z.open(n) as src,dest.open('xb') as dst:
    for b in iter(lambda:src.read(1048576),b''):dst.write(b)
   assert sha(dest)==h,n
 (root/'tmp').mkdir()
 env=dict(os.environ,PROCESSOR_ARCHITECTURE='AMD64',PYTHONUTF8='1',TEMP=str(root/'tmp'),TMP=str(root/'tmp'),PYTHONPYCACHEPREFIX=str(root/'pycache'))
 while True:
  m=system_memory();state(stage='memory_admission',job=plan['job'],actual_memory=m)
  if m['free_commit_bytes']>=plan['required_free_commit_GiB']*1024**3 and m['physical_available_bytes']>=plan['required_physical_GiB']*1024**3:break
  time.sleep(15)
 cwd=root/plan['cwd'];state(stage=plan['kind'],job=plan['job'],actual_admission_memory=m,threads=4)
 if plan['kind']=='smooth_full_PR':
  build=cwd/'build';build.mkdir()
  argv=['D:/AMDDesignTools/2025.2.1/Vivado/bin/vivado.bat','-mode','batch','-source',(cwd/plan['tcl']).as_posix(),'-log',(build/'vivado.log').as_posix(),'-journal',(build/'vivado.jou').as_posix(),'-notrace']
 else:
  argv=[sys.executable,'-X','utf8',str(cwd/plan['runner'])]
 receipt=run(argv,cwd=cwd,env=env,log=root/'task.log',started=root/'task_started.json',limit=32*1024**3)
 write(root/'raw_task_receipt.json',receipt)
 assert receipt['all_owned_processes_terminal'] and receipt['configured_limit_verified'] and receipt['actual_default_memory_API']
 assert receipt['exit_code']==0 and receipt['job_memory_limit_bytes']==32*1024**3 and not receipt['resource_failure'] and not receipt['job_memory_limit_rejection_observed'] and not receipt['elapsed_time_abort']
 if plan['kind']=='smooth_full_PR':
  names=['config_smooth_compact_r2288'+s for s in ('.dcp','.bit','.bin','_pblock_rp_partial.bit','_pblock_rp_partial.bin')]+['OFFLINE_COMPLETE_compact_r2288.txt','timing_compact_r2288.rpt','utilization_compact_r2288.rpt','drc_compact_r2288.rpt','pr_verify_compact_r2288.log']
  for n in names:assert (build/n).is_file() and (build/n).stat().st_size>0,n
  spec=importlib.util.spec_from_file_location('reports',cwd/plan['reports']);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  reports=module.reports(*[(build/n).read_text(errors='replace') for n in ('timing_compact_r2288.rpt','drc_compact_r2288.rpt','pr_verify_compact_r2288.log','utilization_compact_r2288.rpt')])
  write(root/'reports_validated.json',reports)
 elif plan['kind']=='smooth_area_probe':
  observed=json.loads((cwd/plan['output']/'area_probe.json').read_text())
  assert observed['actual_complete_wrapper_synthesis_measured'] and observed['actual_source_and_synthesized_RTL_unchanged']
  assert observed['zero_unresolved_blackboxes'] and observed['HLS_estimate_capacity_failure_retained']
  assert observed['full14_RTL_qualification_pending'] and not observed['actual_RM_qualification_passed']
  assert not observed['route_passed'] and not observed['PL_accessed'] and not observed['production_promoted']
  assert [r['stage'] for r in observed['completed']]==['package','synthesis']
  for n,h in observed['source_and_evidence_sha256'].items():assert sha(root/'workspace'/n)==h,n
 elif plan['kind']=='smooth_full_HLS':
  accepted=json.loads((cwd/plan['output']/'job.json').read_text())
  assert accepted['Csim_all_seven_full_cases_passed'] and accepted['Windows_and_ARM_all_144_and_18_cases_passed']
  assert [r['stage'] for r in accepted['completed']]==['native_compile','native_run','csim','hls']
  assert all(r['exit_code']==0 and r['all_owned_processes_terminal'] and r['configured_limit_verified'] and not r['resource_failure'] and not r['elapsed_time_abort'] for r in accepted['completed'])
  assert accepted['requested_cached_lanes']==2 and accepted['previous_cached_lanes']==1
  assert accepted['HLS_capacity_gate_passed'], 'Complete HLS resource/clock estimate gate failed; retain complete result, no promotion'
  assert accepted['row_rounds_actual_II1'] and accepted['configured_graph_dual_read_ports_verified'] and accepted['configured_cached_throughput_gate_passed']
  assert accepted['cached_graph_actual_read_ports']==[['0','0'],['0','1']]
  assert not accepted['full_RTL_passed'] and not accepted['PL_accessed'] and not accepted['production_promoted']
  for n,h in accepted['source_and_evidence_sha256'].items():assert sha(root/'workspace'/n)==h,n
 else:
  accepted=json.loads((cwd/plan['output']/'acceptance.json').read_text())
  if plan['kind']=='R11_full_RTL':
   assert accepted['ordinary_passed'] and accepted['random_passed'] and accepted['all_original_68_cases_each_required'] and not accepted['original_suites_reduced']
  else:
   assert plan['kind']=='C9_full_RTL'
   assert accepted['ordinary_passed'] and accepted['random_passed'] and accepted['full_RTL_passed']
   assert accepted['original_full_transactions_each']==763 and accepted['full_original_input_words_each']==4782585 and not accepted['original_suites_reduced']
   assert accepted['all_original_six_output_files_compared'] and accepted['canonical_complete_coverage_export_verified'] and accepted['reference_complete_coverage_export_verified']
 for n,h in manifest.items():assert sha(root/n)==h,n
 for n,h in inputs.items():assert sha(root/n)==h,n
except BaseException:failure=traceback.format_exc()
terminal=dict(stage='terminal',job=plan['job'],tool_gates_passed=failure is None,failure=failure,all_owned_compiler_processes_terminal=receipt is None or receipt['all_owned_processes_terminal'],full_original_test_scope_preserved=True,PL_accessed=False,production_promoted=False,whole_goal_completed=False)
write(root/'terminal.json',terminal);state(stage='terminal',job=plan['job'],tool_gates_passed=failure is None)
files={p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file() and p.name not in ('stdout.log','stderr.log')}
with zipfile.ZipFile(root/'result.zip','x',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
 for n in files:z.write(root/n,n)
 z.writestr('outputs_manifest.json',json.dumps(files,sort_keys=True))
write(root/'download.json',dict(archive='result.zip',sha256=sha(root/'result.zip'),bytes=(root/'result.zip').stat().st_size,count=len(files),compiler_terminal=True))
print('Task terminal; collect and verify all owned files before deleting this root',flush=True)
'''


def launch(job):
    out = selected_out(job)
    plan = json.loads((out / 'plan.json').read_text())
    assert not (out / 'owner.json').exists()
    assert sha(out / 'input.zip') == plan['input_archive_sha256']
    name = 'k26-r2602-' + uuid.uuid4().hex[:16]
    win = PureWindowsPath('D:/') / name
    remote = '/' + win.as_posix()
    owner = dict(job=job, name=name, windows_root=str(win), remote_root=remote)
    write(out / 'owner.json', owner)
    src = out / 'server_input'; src.mkdir()
    with (src / 'worker.py').open('x', encoding='utf8', newline='\n') as f:
        f.write(WORKER)
    write(src / 'owner.json', owner)
    entries = {n: p for n, p in [('worker.py', src / 'worker.py'), ('owner.json', src / 'owner.json'),
        ('plan.json', out / 'plan.json'), ('input.zip', out / 'input.zip'),
        ('job_limit_r74.py', ROOT / 'dfx/navigation_profile/rtl_r74/job_limit_r74.py'),
        ('owned_windows_paths_r2418.py', ROOT / 'tools/owned_windows_paths_r2418.py')]}
    write(src / 'manifest.json', {n: sha(p) for n, p in entries.items()})
    entries['manifest.json'] = src / 'manifest.json'
    write(out / 'upload_plan.json', dict(payload_sha256={n: sha(p) for n, p in entries.items()},
        bytes=sum(p.stat().st_size for p in entries.values()), private_parallel_authorized=True,
        other_server_files_modified=False))
    t = connect()
    try:
        with paramiko.SFTPClient.from_transport(t) as s:
            try: s.lstat(remote)
            except FileNotFoundError: pass
            else: raise AssertionError('Task root already exists')
            s.mkdir(remote)
            for n, p in entries.items():
                s.put(str(p), remote + '/' + n)
        python = 'D:/AMDDesignTools/2025.2.1/Vivado/tps/win64/python-3.13.0/python.exe'
        cmd = '"' + python + '" -X utf8 -X pycache_prefix=' + win.as_posix() + '/pycache "' + win.as_posix() + '/worker.py"'
        script = "[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)\n$ProgressPreference='SilentlyContinue'\n"
        script += "$startup=New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[UInt16]0}\n"
        script += "$r=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='" + cmd.replace("'", "''") + "';CurrentDirectory='" + win.as_posix() + "';ProcessStartupInformation=$startup}\n"
        script += '[ordered]@{return_code=$r.ReturnValue;PID=$r.ProcessId}|ConvertTo-Json -Compress'
        code, data, err = command(t, script)
        assert code == 0, err.decode(errors='replace')[:500]
        created = json.loads(data.decode('utf-8-sig'))
        dispatch = out / 'dispatch'; dispatch.mkdir()
        write(dispatch / 'created.json', created)
        assert created['return_code'] == 0
        first = process(t, created['PID'])
        assert first and win.as_posix() in first['argv'].replace('\\', '/')
        write(dispatch / 'first_actual_process.json', first)
    finally:
        t.close()
    t = connect()
    try:
        second = process(t, created['PID']); assert second == first
        with paramiko.SFTPClient.from_transport(t) as s:
            while True:
                try:
                    with s.open(remote + '/worker_started.json') as f: started = json.load(f)
                    break
                except FileNotFoundError:
                    assert process(t, created['PID']) == second
                    time.sleep(.2)
            assert started['PID'] == created['PID'] and started['inputs_sha256_verified']
            with s.open(remote + '/release.json', 'wx') as f:
                f.write(json.dumps(dict(verified_worker_PID=created['PID'])))
        write(dispatch / 'released.json', dict(actual_process=second, survived_launching_SSH_disconnect=True,
            private_parallel_authorized=True, no_service_task_autostart_created=True))
        print(job, 'released on SSH2, actual persistent worker PID', created['PID'], flush=True)
    finally:
        t.close()


def snapshot(job):
    out = selected_out(job)
    owner = json.loads((out / 'owner.json').read_text())
    started = json.loads((out / 'dispatch/first_actual_process.json').read_text())
    t = connect()
    try:
        live = process(t, started['PID'])
        same = bool(live and live['creation_FILETIME'] == started['creation_FILETIME'])
        with paramiko.SFTPClient.from_transport(t) as s:
            with s.open(owner['remote_root'] + '/state.json') as f: state = json.load(f)
        print(json.dumps(dict(job=job, actual_original_worker_live=same, process=live, state=state), indent=2))
    finally:
        t.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('job', choices=('smooth', 'heatmap', 'c9', 'smooth_hls', 'smooth_area'))
    p.add_argument('mode', choices=('launch', 'snapshot'))
    a = p.parse_args()
    {'launch': launch, 'snapshot': snapshot}[a.mode](a.job)
