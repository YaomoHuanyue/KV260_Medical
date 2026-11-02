"""Standalone D6/C5 inference plus mandatory B7 cleanup; no CPU CCL path."""
from pathlib import Path
import argparse,ast,hashlib,importlib.util,json,os,sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
B7=ROOT/'modules/airway_tree_cleanup/volume_axis_r4/system_pipeline_r1'
B7_MANIFEST_SHA='26875f9341495089dff10db0f92b83895f4e6dba7635bc74ba4cc63f7309c76d'
sys.dont_write_bytecode=True
sys.path[:0]=[str(ROOT),str(B7)]

def sha(path):
    with Path(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def require_binding(path,digest):
    path=Path(path).resolve(strict=True)
    if not path.is_relative_to(ROOT)or sha(path)!=digest:raise ValueError('Explicit standalone PL runtime binding SHA required')
    r=read(path)
    if(r.get('schema')!='kv260.standalone_B7.runtime.v1'or r.get('silent_PS_fallback')is not False
       or r.get('PL_cleanup_mandatory')is not True):raise ValueError('Unsupported standalone PL binding')
    for name,expected in r['source_SHA256'].items():
        p=(ROOT/name).resolve(strict=True)
        if not p.is_relative_to(ROOT)or sha(p)!=expected:raise ValueError('Changed standalone PL source: '+name)
    if sha(B7/'manifest.json')!=B7_MANIFEST_SHA:raise ValueError('Qualified complete-B7 manifest changed')
    for name,expected in read(B7/'manifest.json')['source_SHA256'].items():
        p=(ROOT/name).resolve(strict=True)
        if not p.is_relative_to(ROOT)or sha(p)!=expected:raise ValueError('Changed qualified B7 dependency: '+name)
    return r

def repeat_count(value):
    if type(value)is not int or not 1<=value<=5:raise ValueError('Segmentation repeats must be an integer from 1 to 5')
    return value

def parent_module():
    spec=importlib.util.spec_from_file_location('standalone_frozen_B7_parent',B7/'backend.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def derive(source):
    """Change only fresh-input admission, two-stage selection and repeat argument."""
    edits=[
        ("    if mode != 'all':", "    if mode not in ('all','segmentation'):"),
        ("    if source and mode != 'all':", "    if source and mode not in ('all','segmentation'):"),
        ("['segmentation', 'airway-cleanup', 'reconstruction', 'navigation'] if mode=='all' else ['navigation' if mode=='comparison' else mode]",
         "['segmentation', 'airway-cleanup', 'reconstruction', 'navigation'] if mode=='all' else (['segmentation','airway-cleanup'] if mode=='segmentation' else ['navigation' if mode=='comparison' else mode])"),
        ("'--output',str(output/'segmentation'),'--job-lock-fd'", "'--output',str(output/'segmentation'),'--repeats',str(_standalone_repeats if mode=='segmentation' else 1),'--job-lock-fd'"),
        ("functional_streaming_candidate=True,performance_qualification_pending=True,all_operators_on_PL=False)",
         "functional_streaming_candidate=True,performance_qualification_pending=True,all_operators_on_PL=False,segmentation_only=mode=='segmentation',repeats=_standalone_repeats if mode=='segmentation' else 1,silent_PS_fallback=False,PL_cleanup_mandatory=True)")]
    before=source
    for a,b in edits:
        if source.count(a)!=1:raise ValueError('Changed qualified standalone boundary: '+a[:100])
        source=source.replace(a,b)
    reverse=source
    for a,b in reversed(edits):
        if reverse.count(b)!=1:raise ValueError('Ambiguous inverse standalone edit')
        reverse=reverse.replace(b,a)
    if reverse!=before:raise ValueError('Standalone derivation lost parent behavior')
    ast.parse(source);return source,edits

def install(binding,digest,run_parent=None,repeats=1):
    require_binding(binding,digest);parent=parent_module()
    backend=parent.install(B7/'manifest.json',B7_MANIFEST_SHA,run_parent)
    source,edits=derive(parent.derived_dispatch()[0])
    backend._standalone_repeats=repeat_count(repeats)
    exec(compile(source,str(HERE/'backend.py')+':standalone_two_PL_stages','exec'),backend.__dict__)
    return backend

def main():
    p=argparse.ArgumentParser(add_help=False)
    p.add_argument('--binding',type=Path,required=True);p.add_argument('--binding-sha256',required=True)
    p.add_argument('--repeats',type=int,default=1);p.add_argument('--run-parent',type=Path)
    a,rest=p.parse_known_args();backend=install(a.binding,a.binding_sha256,a.run_parent,a.repeats)
    head=argparse.ArgumentParser(add_help=False);head.add_argument('action');head.add_argument('--mode')
    known,_=head.parse_known_args(rest)
    if known.action=='run'and known.mode=='segmentation':
        q=argparse.ArgumentParser();q.add_argument('action',choices=['run']);q.add_argument('--mode',choices=['segmentation'],required=True)
        q.add_argument('--input',type=Path,required=True);q.add_argument('--stop-file',type=Path)
        v=q.parse_args(rest)
        if hasattr(os,'nice'):os.nice(10)
        os.environ.setdefault('ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS','2');os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
        return backend.run(v.input,'segmentation',None,0,1.,.2,v.stop_file,0.)
    sys.argv=[sys.argv[0],*rest]
    import backend_selected_r1 as accepted
    return accepted.main()

if __name__=='__main__':
    try:main()
    except Exception as e:
        print(json.dumps(dict(event='error',text=str(e)),ensure_ascii=False),flush=True);sys.exit(1)
