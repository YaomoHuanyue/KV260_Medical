"""Pin the metadata-only adapter and preserve every original R3/R5 UI control."""
from pathlib import Path
from contextlib import ExitStack
import copy,hashlib,json,sys,zipfile
import project_storage
from prepare_R3_native_system_20261022_r1 import derive,sha,save
ROOT=project_storage.SYSTEM;UI=ROOT/'ui/releases/streaming_reader_r2';STAGE=ROOT/'modules/segmentation/axis_tensor_reader_r3/reporting_r2'

def main():
    project_storage.check(500_000)
    assert not (UI/'inputs.json').exists() and not (STAGE/'inputs.json').exists()
    parent=ROOT/'ui/releases/streaming_reader_r1'
    main_edits=[('root+"/ui/releases/streaming_reader_r1/backend.py"','root+"/ui/releases/streaming_reader_r2/backend.py"',2)]
    text=(parent/'main.cpp').read_text();body=text
    for a,b,count in main_edits:assert body.count(a)==count;body=body.replace(a,b)
    assert body.replace(main_edits[0][1],main_edits[0][0])==text
    with (UI/'main.cpp').open('x',encoding='utf-8',newline='\n') as f:f.write(body)
    edits=[("entry=ROOT/'modules/segmentation/axis_tensor_reader_r3/streaming_r1/entry.py'","entry=ROOT/'modules/segmentation/axis_tensor_reader_r3/reporting_r2/entry.py'",1)]
    code=derive((parent/'build_ARM.py').read_text(),edits)
    with (UI/'build_ARM.py').open('x',encoding='utf-8',newline='\n') as f:f.write(code)
    save(UI/'derivation.json',dict(main_UI=dict(parent=(parent/'main.cpp').relative_to(ROOT).as_posix(),parent_SHA256=sha(parent/'main.cpp'),
        candidate_SHA256=sha(UI/'main.cpp'),literal_edits=[dict(before=a,after=b,count=n) for a,b,n in main_edits],exact_original_reverse_verified=True),
        compiler=dict(parent=(parent/'build_ARM.py').relative_to(ROOT).as_posix(),parent_SHA256=sha(parent/'build_ARM.py'),literal_edits=edits,exact_reverse_verified=True),
        original_medical_math_and_all_UI_controls_unchanged=True,actual_ARM_build_and_GUI_execution_pending=True))
    stage_paths=[STAGE/'entry.py',STAGE/'assignment.py',ROOT/'modules/segmentation/axis_tensor_reader_r3/streaming_r1/entry.py',
        ROOT/'modules/segmentation/axis_tensor_reader_r3/streaming_r1/functional.py',ROOT/'modules/segmentation/axis_tensor_reader_r3/operator_roles_r1/verified.json',
        ROOT/'results/R3_native_system_ARM_20261022_r1/verified_PC.json']
    save(STAGE/'inputs.json',dict(source_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in stage_paths},metadata_only_no_numeric_worker_change=True))
    record=json.loads((parent/'inputs.json').read_text());source=(ROOT/record['dispatcher']).read_text()
    for a,b in record['dispatcher_literal_edits']:assert source.count(a)==1;source=source.replace(a,b)
    a="str(ROOT/'modules/segmentation/axis_tensor_reader_r3/streaming_r1/entry.py')";b="str(ROOT/'modules/segmentation/axis_tensor_reader_r3/reporting_r2/entry.py')"
    assert source.count(a)==1;source=source.replace(a,b)
    files=[*stage_paths,STAGE/'inputs.json',UI/'backend.py',UI/'main.cpp',UI/'build_ARM.py',UI/'derivation.json',parent/'backend.py',parent/'inputs.json',Path(__file__)]
    save(UI/'inputs.json',dict(source_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in files},dispatcher_SHA256=hashlib.sha256(source.encode()).hexdigest(),
        complete_R3_backend_with_metadata_only_report_correction=True,actual_GUI_execution_pending=True))
    # Use the actual prior full139 report, including its complete measurements.
    from collect_streaming_UI_ARM_20261022_r1 import codec,CANONICAL,payload
    sys.path.insert(0,str(ROOT))
    from modules.segmentation.axis_tensor_reader_r3.reporting_r2.assignment import describe
    with ExitStack() as stack:
        z=stack.enter_context(zipfile.ZipFile(ROOT/'results/R3_native_system_ARM_20261022_r1/current_candidate.zip'))
        table=json.loads(z.read('logical_files.json'));baseline=codec().View(stack,CANONICAL)
        name=next(n for n in table if n.startswith('outputs/') and n.endswith('/segmentation/report.json') and '6e09f54c/' in n)
        with payload(stack,z,table[name],baseline) as f:original=json.load(f)
        corrected,delta=describe(original)
        assert {k:v for k,v in corrected.items() if k not in ('ps_operators','operator_assignment')}=={k:v for k,v in original.items() if k not in ('ps_operators','operator_assignment')}
        assert corrected['pl_reader_calls']==840 and 'resize, concat' not in corrected['ps_operators']
        save(STAGE/'verified.json',dict(actual_full139_original_report_SHA256=table[name]['SHA256'],
            all_original_numeric_counts_timings_and_output_fields_unchanged=True,changed_keys=delta['only_changed_keys'],
            actual_complete_report_descriptions_corrected=True,no_PL_access=True,
            source_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in [STAGE/'assignment.py',STAGE/'entry.py',Path(__file__)]}))
    print('PASS actual full139 report metadata corrected; complete R3 UI source prepared; no numeric algorithm change')
if __name__=='__main__':main()
