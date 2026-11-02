"""Accepted complete dispatcher plus mandatory, explicit B7 cleanup stage."""
from pathlib import Path
import argparse,ast,hashlib,json,sys
from admission import ROOT,HERE,verify,read
sys.path.insert(0,str(ROOT))
def derived_dispatch():
    source=(ROOT/'ui/releases/streaming_functional_r1/dispatch.py').read_text()
    r1=read(ROOT/'ui/releases/streaming_reader_r1/inputs.json')
    for a,b in r1['dispatcher_literal_edits']:
        if source.count(a)!=1:raise ValueError('Changed qualified R3 dispatcher')
        source=source.replace(a,b)
    a="str(ROOT/'modules/segmentation/axis_tensor_reader_r3/streaming_r1/entry.py')";b="str(ROOT/'modules/segmentation/axis_tensor_reader_r3/reporting_r2/entry.py')"
    assert source.count(a)==1;source=source.replace(a,b)
    if hashlib.sha256(source.encode()).hexdigest()!=read(ROOT/'ui/releases/streaming_reader_r2/inputs.json')['dispatcher_SHA256']:raise ValueError('Accepted complete dispatcher SHA changed')
    edits=[("['segmentation', 'reconstruction', 'navigation'] if mode=='all'", "['segmentation', 'airway-cleanup', 'reconstruction', 'navigation'] if mode=='all'"),
           (b,"str(_b7_here/'segmentation.py'),'--admission',str(_b7_admission),'--admission-sha256',_b7_admission_sha"),
           ("    command = {", "    command = {\n        'airway-cleanup':[str(_b7_here/'cleanup.py'),'--admission',str(_b7_admission),'--admission-sha256',_b7_admission_sha,'--ct',str(input_path),'--segmentation',str(output/'segmentation'),'--job-lock-fd',str(_candidate_job_fd)]+(['--stop-file',str(stop_file)]if stop_file else []),"),
           ("child=subprocess.Popen(argv,cwd=MEDICAL,stdout=log,stderr=subprocess.STDOUT,pass_fds=(_candidate_job_fd,))", "child=subprocess.Popen(argv,cwd=MEDICAL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,pass_fds=(_candidate_job_fd,))"),
           ("                rc=child.wait()", "                for line in iter(child.stdout.readline,b''):\n                    text=line.decode('utf8',errors='replace');log.write(text);log.flush()\n                    if stage=='airway-cleanup':\n                        try:event=json.loads(text)\n                        except ValueError:continue\n                        if event.get('event')=='progress':emit('progress',text=event['text'])\n                rc=child.wait()"),
           ("            emit('stage', stage=stage", "            if stage=='navigation'and mode=='all':\n                availability=_b7_navigation_availability(output)\n                report['navigation_availability']=availability\n                if not availability['available']:\n                    write(output/'navigation_availability.json',availability)\n                    phases.append(dict(stage=stage,status='not_available',reason=availability['reason'],PL_invoked=False,wall_seconds=0.))\n                    emit('progress',text=availability['text'])\n                    emit('stage_done',stage=stage,seconds=0.)\n                    continue\n            emit('stage', stage=stage")]
    before=source
    for a,b in edits:
        if source.count(a)!=1:raise ValueError('B7 dispatcher boundary changed: '+a[:80])
        source=source.replace(a,b)
    reverse=source
    for a,b in reversed(edits):reverse=reverse.replace(b,a)
    assert reverse==before;ast.parse(source);return source,edits
def navigation_availability(output):
    r=read(Path(output)/'segmentation/report.json');counts=r.get('mask_foreground_voxels',{})
    if r.get('status')!='completed'or set(counts)!={'lung','airway','nodule'}or any(type(n)is not int or n<0 for n in counts.values()):raise ValueError('Verified final-mask counts required before navigation')
    if not counts['airway']:return dict(available=False,reason='empty_airway',PL_invoked=False,text='气道掩膜为空，本次不生成导航；分割与重建结果已保留。')
    if not counts['nodule']:return dict(available=False,reason='empty_lesion_candidates',PL_invoked=False,text='无病灶候选，本次不生成导航；分割与重建结果已保留。')
    return dict(available=True,reason='airway_and_lesion_provided',PL_invoked=None)
def install(admission,digest,run_parent=None):
    verify(admission,digest)
    from ui.releases.streaming_reader_r2.backend import install as parent
    backend=parent();source,_=derived_dispatch()
    backend.__dict__.update(_b7_here=HERE,_b7_admission=Path(admission),_b7_admission_sha=digest,_b7_navigation_availability=navigation_availability)
    exec(compile(source,str(HERE/'backend.py')+':mandatory_B7_complete_dispatch','exec'),backend.__dict__)
    backend.CANDIDATE_RUNS=ROOT/'ui/runs'if run_parent is None else Path(run_parent).resolve()
    if not backend.CANDIDATE_RUNS.is_relative_to(ROOT):raise ValueError('Result parent outside project')
    return backend
def main():
    p=argparse.ArgumentParser(add_help=False);p.add_argument('--admission',type=Path,required=True);p.add_argument('--admission-sha256',required=True);p.add_argument('--run-parent',type=Path)
    a,rest=p.parse_known_args();install(a.admission,a.admission_sha256,a.run_parent);sys.argv=[sys.argv[0],*rest]
    import backend_selected_r1 as accepted
    return accepted.main()
if __name__=='__main__':
    try:main()
    except Exception as e:print(json.dumps(dict(event='error',text=str(e)),ensure_ascii=False),flush=True);raise
