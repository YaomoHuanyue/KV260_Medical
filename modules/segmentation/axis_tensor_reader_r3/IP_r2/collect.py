"""Keep unchanged full owned-byte transport, select current IPX/package evidence."""
from pathlib import Path
import hashlib,importlib.util,json,stat,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
OUT=ROOT/'results/tensor_reader_R3_IP_R2_20261022_r1/axis_hls'

def main():
    original=HERE.parent/'IP_r1/collect.py'
    name='exact_owned_reader_IP_R2_collector_parent'
    spec=importlib.util.spec_from_file_location(name,original);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
    m.HERE=HERE;m.OUT=OUT;m.parent.OUT=OUT;m.__file__=str(Path(__file__))
    m.helper.CANONICAL=[ROOT/'results/tensor_reader_R3_HLS_20261022_r1/axis_hls/current_candidate.zip']
    def select_required(names,z,plan):
        assert plan['output']==(HERE/'output').relative_to(ROOT).as_posix()
        prefix='workspace/'+plan['output']+'/'
        selected=set(m.parent.read(OUT/'upload_plan.json')['payload_sha256'])|set(plan['input_manifest'])
        selected.update(n for n in names if n in ('terminal.json','state.json','worker_started.json','own_worker_affinity.json',
            'task_started.json','raw_task_receipt.json','task.log','release.json'))
        selected.update(n for n in names if n.startswith(prefix))
        required={'terminal.json','task.log'};terminal=json.loads(z.read('terminal.json'))
        if terminal['tool_gates_passed']:
            required.update(prefix+n for n in ('complete.json','export.zip','refresh.log','refresh_receipt.json','refresh_started.json','vivado.log','vivado.jou'))
            assert json.loads(z.read(prefix+'complete.json'))['actual_current_Vivado_IPX_exit0']
        assert required<=set(names) and required<=selected,('Missing current IPX evidence',required-set(names))
        assert selected<=set(names)
        for n in selected:m.parent.safe_name(n);assert not stat.S_ISLNK(z.getinfo(n).external_attr>>16)
        m.parent.COLLECTOR_DERIVATION['current_required_full_RTL_identical_IPX_outputs']={n:names[n] for n in sorted(required)}
        return selected
    m.helper.ORIGINAL_SELECT=select_required
    record=dict(parent_source=original.relative_to(ROOT).as_posix(),parent_SHA256=hashlib.sha256(original.read_bytes()).hexdigest(),
        unchanged_full_member_SHA_closed_logs_and_exact_owner_cleanup_transport=True,
        only_owned_current_selector_paths_and_adapter_identity_changed=True,whole_goal_completed=False)
    p=OUT/'collector_derivation.json'
    if p.exists():assert json.loads(p.read_text())==record
    else:
        with p.open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
    m.main()

if __name__=='__main__':main()
