"""Derive the complete existing five-case native trial, retaining every check."""
from pathlib import Path
import ast,hashlib,json
import project_storage
ROOT=project_storage.SYSTEM
UI=ROOT/'ui/releases/streaming_reader_r1'
TRIAL=ROOT/'ui/candidates/streaming_reader_trial_r1/trial.py'
STAGE=ROOT/'modules/segmentation/axis_tensor_reader_r3/streaming_r1'

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,indent=2)
def derive(source,edits):
    body=source
    for a,b,count in edits:assert body.count(a)==count,(a,body.count(a));body=body.replace(a,b)
    reverse=body
    for a,b,count in reversed(edits):assert reverse.count(b)==count,(b,reverse.count(b));reverse=reverse.replace(b,a)
    assert reverse==source;ast.parse(body)
    return body

def main():
    project_storage.check(500_000)
    assert not (UI/'inputs.json').exists() and not TRIAL.exists()
    dispatcher='ui/releases/streaming_functional_r1/dispatch.py'
    dispatch_edits=[("str(ROOT/'modules/segmentation/streaming_stage_r1/entry.py')","str(ROOT/'modules/segmentation/axis_tensor_reader_r3/streaming_r1/entry.py')",1),
        ("str(Path(__file__).parent/'navigation_task_r6.py')","str(ROOT/'modules/navigation_comparison/current_release_r1/task.py')",1)]
    body=derive((ROOT/dispatcher).read_text(),dispatch_edits)
    paths=[UI/'backend.py',STAGE/'entry.py',STAGE/'functional.py',STAGE/'derivation.json',STAGE/'admission_template.json',STAGE/'stage_inputs.json',
        ROOT/dispatcher,ROOT/'ui/releases/streaming_functional_r1/backend.py',ROOT/'ui/releases/streaming_functional_r2/backend.py',
        ROOT/'ui/releases/streaming_functional_r5/backend.py',ROOT/'ui/releases/streaming_functional_r5/inputs.json',
        ROOT/'results/tensor_reader_R3_actual_ARM_20261022_r1/verified_PC.json',Path(__file__)]
    source=ROOT/'ui/candidates/streaming_native_trial_r1/trial.py'
    edits=[('from modules.segmentation.streaming_stage_r1.entry import recover_pending','from modules.segmentation.axis_tensor_reader_r3.streaming_r1.entry import recover_pending',1),
        ("backend=ROOT/'ui/releases/streaming_functional_r1/backend.py'","backend=ROOT/'ui/releases/streaming_reader_r1/backend.py'",1),
        ("ROOT/'ui/releases/streaming_functional_r1/runs'","ROOT/'ui/releases/streaming_reader_r1/runs'",1),
        ("ROOT/'modules/segmentation/streaming_stage_r1/pending_transaction.json'","ROOT/'modules/segmentation/axis_tensor_reader_r3/streaming_r1/pending_transaction.json'",2),
        ("seg['pl_conv_calls']==2520 and seg['pl_pool_calls']==420 and seg['no_PS_pool_fallback']","seg['pl_conv_calls']==2520 and seg['pl_pool_calls']==420 and seg['pl_reader_calls']==840 and seg['no_PS_pool_fallback']",1),
        ('normal_path_without_qualification_probes=True','normal_path_without_qualification_probes=True,actual_R3_reader_840_calls_including_warmup=True',1)]
    text=derive(source.read_text(),edits);TRIAL.parent.mkdir()
    with TRIAL.open('x',encoding='utf-8',newline='\n') as f:f.write(text)
    save(TRIAL.parent/'derivation.json',dict(parent=source.relative_to(ROOT).as_posix(),parent_SHA256=sha(source),
        trial_SHA256=sha(TRIAL),literal_edits=edits,exact_reverse_verified=True,
        original_missing_input_source_cancel_full139_partial_probability_and_all_output_checks_preserved=True))
    paths.extend([TRIAL,TRIAL.parent/'derivation.json',source])
    save(UI/'inputs.json',dict(schema='kv260.R3.native_system.functional.v1',source_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in paths},
        dispatcher=dispatcher,dispatcher_literal_edits=[[a,b] for a,b,_ in dispatch_edits],
        dispatcher_output_SHA256=hashlib.sha256(body.encode()).hexdigest(),
        actual_new_system_and_native_GUI_execution_still_required=True,production_promoted=False,whole_goal_completed=False))
    print('PASS original complete dispatcher and five-case actual native-backend trial derived; hardware not accessed')
if __name__=='__main__':main()
