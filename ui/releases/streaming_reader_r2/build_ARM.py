"""Qualify the actual ARM CLI help path and compile the backend/surface-route UI delta, keeping the formal UI live."""
from pathlib import Path
import hashlib
import json
import os
import resource
import shlex
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=HERE/'build_ARM'
sys.path.insert(0,str(ROOT))


def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def read(p):return json.loads(p.read_text())
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')


def identity():
    state=read(ROOT/'tools/storage_runtime_identity.json');p=Path('/proc',str(state['UI_PID']))
    fields=(p/'stat').read_text().rsplit(')',1)[1].split()
    assert int(fields[19])==state['UI_start_ticks'] and fields[0]!='Z'
    assert sha(p/'exe')==state['binary_sha256']
    return dict(PID=state['UI_PID'],ticks=state['UI_start_ticks'],ELF=state['binary_sha256'],
        runtime_identity_SHA256=sha(ROOT/'tools/storage_runtime_identity.json'))


def main():
    assert os.geteuid()==0 and os.uname().machine=='aarch64' and not OUT.exists()
    available=int(next(v.split()[1] for v in Path('/proc/meminfo').read_text().splitlines() if v.startswith('MemAvailable:')))*1024
    assert available>=1400*1024**2
    assert os.statvfs(ROOT).f_bavail*os.statvfs(ROOT).f_frsize>=100_000_000
    before=identity()
    from modules.segmentation.axis_tensor_reader_r3.streaming_r1.entry import verify_qualification
    assert not (ROOT/'modules/segmentation/axis_tensor_reader_r3/streaming_r1/pending_transaction.json').exists()
    inputs,record,qualified=verify_qualification()
    assert qualified.verify(ROOT/inputs['qualified_template'])==record
    d=read(HERE/'derivation.json')['main_UI'];parent=ROOT/d['parent']
    assert sha(parent)==d['parent_SHA256'];body=parent.read_text()
    for e in d['literal_edits']:assert body.count(e['before'])==e['count'];body=body.replace(e['before'],e['after'])
    assert body==(HERE/'main.cpp').read_text() and sha(HERE/'main.cpp')==d['candidate_SHA256']
    original=ROOT/'ui/releases/probability_cleanup_r1/build_ARM'
    proof=read(original/'verified.json')
    for n,h in proof['source_and_evidence_SHA256'].items():assert sha(ROOT/n)==h,n
    command=read(original/'compile.json')['command']
    common=command[:command.index('-MMD')];objects=[Path(n) for n in command if n.endswith('.o')]
    assert len(objects)==3
    libraries=command[command.index('-lQt5OpenGL'):command.index('-o')]
    argv=common+['-MMD','-MF',str(OUT/'main.d'),str(HERE/'main.cpp'),*map(str,objects),*libraries,'-o',str(OUT/'medical_ui_streaming_candidate')]
    object_SHA={str(p.relative_to(ROOT)):sha(p) for p in objects}
    OUT.mkdir();os.nice(15);os.sched_setaffinity(0,{3})
    entry=ROOT/'modules/segmentation/axis_tensor_reader_r3/reporting_r2/entry.py'
    wrapper='''import json,runpy,sys
from pathlib import Path
forbidden=[]
def audit(event,args):
 bad=event in ('os.kill','subprocess.Popen')
 if event=='open' and isinstance(args[0],str):bad=bad or args[0].startswith(('/dev/mem','/dev/dri/','/sys/class/fpga_manager/')) or args[0]=='/tmp/kv260-ct-pl.lock'
 if event=='ctypes.dlopen' and isinstance(args[0],str):bad=bad or any(v in args[0] for v in ('libmedical_dfx','libhu','libct_pool','libmc_axis','libD9'))
 if bad:forbidden.append(event);raise AssertionError('No GUI/PL mutation in actual CLI help check')
sys.addaudithook(audit)
sys.argv=[ENTRY,'--help']
try:runpy.run_path(ENTRY,run_name='__main__')
except SystemExit as e:assert e.code==0
else:raise AssertionError('Original argparse help did not exit')
assert not forbidden
Path(OUTPUT).write_text(json.dumps(dict(status='actual_ARM_original_CLI_help_and_complete_qualification_passed_no_PL',forbidden_events=forbidden,PL_accessed=False,whole_goal_completed=False),indent=2)+'\\n')
'''
    code='ENTRY='+repr(str(entry))+'\nOUTPUT='+repr(str(OUT/'CLI_help_verified.json'))+'\n'+wrapper
    with (OUT/'CLI_help.log').open('xb') as log:
        child=subprocess.Popen([sys.executable,'-B','-c',code],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        save(OUT/'CLI_help_started.json',dict(PID=child.pid,argv=[sys.executable,'-B','-c','audited_original_entry_help']))
        rc=child.wait()
    assert rc==0,'Preserve actual CLI failure and running formal UI'
    def limit():resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    tick=time.perf_counter()
    with (OUT/'compile.log').open('xb') as log:
        child=subprocess.Popen(argv,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,preexec_fn=limit)
        ticks=int(Path('/proc',str(child.pid),'stat').read_text().rsplit(')',1)[1].split()[19])
        save(OUT/'started.json',dict(PID=child.pid,start_ticks=ticks,argv=argv))
        rc=child.wait()
    receipt=dict(exit_code=rc,seconds=time.perf_counter()-tick,command=argv,log_SHA256=sha(OUT/'compile.log'),
        peak_child_RSS_KiB=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        one_core_affinity=[3],nice=15,compiler_address_space_limit_bytes=2*1024**3)
    save(OUT/'compile.json',receipt);assert rc==0,'Keep failed diagnostics; do not replace the formal UI'
    assert identity()==before
    for n,h in object_SHA.items():assert sha(ROOT/n)==h
    bindings={}
    for word in shlex.split((OUT/'main.d').read_text().replace('\\\n',' ').split(':',1)[1]):
        p=Path(word).resolve()
        if p.is_relative_to(ROOT):bindings[p.relative_to(ROOT).as_posix()]=sha(p)
    for p in [Path(__file__),HERE/'backend.py',HERE/'inputs.json',HERE/'derivation.json',entry,
              ROOT/'modules/segmentation/axis_tensor_reader_r3/streaming_r1/stage_inputs.json',
              OUT/'medical_ui_streaming_candidate',OUT/'CLI_help_verified.json']:
        bindings[p.relative_to(ROOT).as_posix()]=sha(p)
    save(OUT/'verified.json',dict(status='actual_ARM_general_PL_stage_help_and_complete_UI_route_candidate_compiled_formal_UI_unchanged',
        formal_UI_before=before,formal_UI_after=identity(),original_three_render_objects_SHA256=object_SHA,
        candidate_backend_and_surface_action_routes_changed_original_medical_algorithms_preserved=True,
        complete_real_PL_pair_bound_not_a_new_bitstream_or_kernel_performance_claim=True,
        actual_general_stage_full139_GUI_dispatch_and_physical_HDMI_acceptance_still_required=True,
        source_and_evidence_SHA256=bindings,PL_accessed=False,production_promoted=False,whole_goal_completed=False))
    print('PASS actual ARM CLI help and UI delta compiled; formal UI/objects unchanged; full real pipeline still required',flush=True)


if __name__=='__main__':main()
