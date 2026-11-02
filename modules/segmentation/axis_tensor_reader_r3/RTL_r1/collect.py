"""Stream-verify all owned bytes; retain complete tests and concise actual logs."""
from pathlib import Path,PureWindowsPath
import inspect,json,stat,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import collect_AXIS_DFX_area_dedup_r2 as helper
import collect_server2_four_register_HLS_r2450 as legacy
parent=helper.parent;OUT=ROOT/'results/tensor_reader_R3_RTL_20261022_r1/axis_rtl'
parent.OUT=OUT;parent.legacy=legacy

def check_owner(owner):
    win=PureWindowsPath(owner['windows_root'])
    assert win.parent==PureWindowsPath('D:/') and win.name==owner['name']
    assert win.name.startswith('k26-r2450-') and len(win.name)==26 and all(c in '0123456789abcdef' for c in win.name[10:])
    assert owner['remote_root']=='/'+win.as_posix() and owner['job']=='axis_rtl'==OUT.name
    return win,owner['remote_root']

def select_required(names,z,plan):
    assert plan['output']==HERE.relative_to(ROOT).as_posix();prefix='workspace/'+plan['output']+'/'
    selected=set(parent.read(OUT/'upload_plan.json')['payload_sha256'])|set(plan['input_manifest'])
    selected.update(n for n in names if n in ('terminal.json','state.json','worker_started.json','own_worker_affinity.json',
        'task_started.json','raw_task_receipt.json','task.log','release.json'))
    for n in names:
        if n.startswith(prefix) and n.endswith(('.json','.log','.sv','.hex','.jou','.tcl','.v')):selected.add(n)
        if n.startswith('s/') and n.endswith(('/compile.bat','/elaborate.bat','/simulate.bat','/xvlog.log','/xelab.log','/xsim.log','/xsim.ini','/model_lut.hex')):selected.add(n)
    terminal=json.loads(z.read('terminal.json'));required={'terminal.json','task.log'}
    if terminal['tool_gates_passed']:
        required.add(prefix+'complete.json')
        complete=json.loads(z.read(prefix+'complete.json'))
        assert complete['all330_complete_frames_and8_actual_global_resets']
        for mode in ('ordinary','random'):
            required.update(prefix+f'run/{mode}/'+n for n in ('tb.sv','hold.sv','model_lut.hex','harness_contract.json',
                'initializers_staged.json','setup_receipt.json','compile_receipt.json','elaborate_receipt.json','simulate_receipt.json','simulate.log'))
    assert required<=set(names) and required<=selected,('Missing actual full RTL evidence',required-set(names))
    assert selected<=set(names)
    for n in selected:parent.safe_name(n);assert not stat.S_ISLNK(z.getinfo(n).external_attr>>16)
    parent.COLLECTOR_DERIVATION['required_full159_RTL_evidence']={n:names[n] for n in sorted(required)}
    return selected

parent.check_owner=check_owner;helper.ORIGINAL_SELECT=select_required
helper.CANONICAL=[ROOT/'results/tensor_reader_R3_HLS_20261022_r1/axis_hls/current_candidate.zip']

def main():
    from owned_windows_closed_collection import install
    import compact_closed_memory_transport_k2450_20261019 as memory
    owner=parent.read(OUT/'owner.json');check_owner(owner);install(sys.modules[__name__],Path(__file__))
    largest=max((ROOT/'results/storage_cleanup_20261015'/n).stat().st_size for n in ('protected.json','current_dependencies.json'))
    source=inspect.getsource(memory.run);before="'project_storage.check(bound+24_000_000+OTHER_COLLECTION_RESERVE)'"
    after=f"'project_storage.check(bound+{largest+2_000_000}+OTHER_COLLECTION_RESERVE)'"
    assert source.count(before)==1;changed=source.replace(before,after);assert changed.replace(after,before)==source
    parent.project_storage.check(largest+2_100_000)
    record=dict(original_RAM_collector_SHA256=parent.sha(Path(memory.__file__)),literal_reservation_edit=[before,after],
        exact_reverse_verified=True,largest_actual_atomic_map_bytes=largest,metadata_headroom_bytes=2_000_000,
        full_compact_bound_still_checked_before_output=True,all_owned_bytes_closed_logs_and_exact_cleanup_gates_preserved=True)
    target=OUT/'actual_collection_peak_admission.json'
    if target.exists():assert parent.read(target)==record
    else:parent.save(target,record)
    exec(compile(changed,str(Path(__file__))+':measured_metadata_peak','exec'),memory.__dict__)
    memory.run(helper,parent,owner['remote_root'],Path(__file__),0)
    proof=parent.read(OUT/'cleanup_verified_stream.json')
    assert proof['owned_root_confirmed_absent'] and proof['all_owned_member_bytes_and_closed_logs_stream_SHA_verified_locally']
    print('PASS every owned RTL byte collected and exact task root removed')

if __name__=='__main__':main()
