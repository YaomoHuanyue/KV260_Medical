"""Stream every owned compiler byte, retain the source/RTL/reports, remove exact root."""
from pathlib import Path
import importlib.util,io,json,stat,sys,zipfile
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'tools'))
OUT=ROOT/'results/tensor_reader_R3_HLS_20261022_r1/axis_hls'
PARENT=ROOT/'modules/reconstruction/mesh_topology_r1/rank_cache_URAM_r9/full_HLS_r1/collect.py'
OUTPUT=(HERE/'output').relative_to(ROOT).as_posix()

def select_required(names,z,plan,uploads):
    assert plan['output']==OUTPUT;prefix='workspace/'+OUTPUT+'/'
    selected=set(uploads)|set(plan['input_manifest'])
    selected.update(n for n in names if n in ('terminal.json','state.json','worker_started.json','own_worker_affinity.json',
        'task_started.json','raw_task_receipt.json','task.log','release.json'))
    selected.update(n for n in names if n.startswith(prefix) or n.startswith('h/tensor/hls/syn/verilog/') or n.startswith('h/tensor/hls/syn/report/'))
    terminal=json.loads(z.read('terminal.json'))
    if terminal['tool_gates_passed']:
        required={prefix+n for n in ('complete.json','reader.cfg','generated_members.json','csim_cli.log','csim_cli_receipt.json','csim_direct.log','csim_direct_receipt.json','direct_AP_source_binding.json','hls.log','hls_receipt.json')}
        required.add('h/tensor/hls/syn/report/ct_tensor_reader_csynth.xml')
        generated=json.loads(z.read(prefix+'generated_members.json'))
        assert generated and any(n.endswith('.v') for n in generated)
        required.update('h/tensor/'+n for n in generated)
    else:
        required={prefix+'failure.json'}
        # Keep diagnostics for failed numerical Csim/HLS, not just an outer exit code.
        selected.update(n for n in names if n.startswith('h/tensor/') and n.endswith(('.log','.rpt','.xml','.json','.tcl')))
    assert required<=set(names) and required<=selected,('Missing actual reader outputs',required-set(names))
    assert selected<=set(names)
    for n in selected:assert not stat.S_ISLNK(z.getinfo(n).external_attr>>16)
    return selected,required

def preflight():
    prefix='workspace/'+OUTPUT+'/'
    entries={'terminal.json':json.dumps(dict(tool_gates_passed=True)).encode()}
    for n in ('complete.json','reader.cfg','csim_cli.log','csim_cli_receipt.json','csim_direct.log','csim_direct_receipt.json','direct_AP_source_binding.json','hls.log','hls_receipt.json'):entries[prefix+n]=b'x'
    entries[prefix+'generated_members.json']=json.dumps({'hls/syn/verilog/ct_tensor_reader.v':'x'}).encode()
    entries['h/tensor/hls/syn/verilog/ct_tensor_reader.v']=b'x'
    entries['h/tensor/hls/syn/report/ct_tensor_reader_csynth.xml']=b'x';buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:
        for n,b in entries.items():z.writestr(n,b)
    with zipfile.ZipFile(buffer) as z:
        selected,required=select_required(entries,z,dict(output=OUTPUT,input_manifest={}),{})
        for missing in required:
            reduced=dict(entries);reduced.pop(missing)
            try:select_required(reduced,z,dict(output=OUTPUT,input_manifest={}),{})
            except AssertionError:pass
            else:raise AssertionError('Missing reader artifact admitted: '+missing)
    return dict(all_required_actual_reader_outputs_refused_when_missing=True,count=len(required))

def main():
    preflight();spec=importlib.util.spec_from_file_location('tensor_reader_closed_collector_parent',PARENT)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.CORE=HERE.parent;m.OUT=OUT;m.parent.OUT=OUT;m.helper.CANONICAL=[]
    def necessary(names,z,plan):
        selected,required=select_required(names,z,plan,m.parent.read(OUT/'upload_plan.json')['payload_sha256'])
        m.parent.COLLECTOR_DERIVATION['required_tensor_reader_Csim159_HLS_outputs']={n:names[n] for n in sorted(required)}
        return selected
    m.helper.ORIGINAL_SELECT=necessary
    from owned_windows_closed_collection import install
    from compact_closed_memory_transport_k2450_20261019 import run
    owner=m.parent.read(OUT/'owner.json');m.check_owner(owner);install(m,Path(__file__))
    run(m.helper,m.parent,owner['remote_root'],Path(__file__),0)
    proof=m.parent.read(OUT/'cleanup_verified_stream.json')
    assert proof['owned_root_confirmed_absent'] and proof['all_owned_member_bytes_and_closed_logs_stream_SHA_verified_locally']
    print('PASS every owned byte collected and exact reader task root removed')

if __name__=='__main__':
    print(json.dumps(preflight())) if sys.argv[1:]==['--preflight'] else main()
