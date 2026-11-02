"""Complete system dispatcher with an explicit, source-bound hybrid selection."""
from pathlib import Path
import argparse,ast,json,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from modules.segmentation.mixed_r30.admission import ROOT,HERE,verify,read,sha
sys.path.insert(0,str(ROOT))

def derive(source):
    edits=[("str(_b7_here/'segmentation.py')","str(_mixed_here/'segmentation.py')"),
           ("str(_b7_here/'cleanup.py')","str(_mixed_here/'cleanup.py')"),
           ('str(_b7_admission)','str(_mixed_admission)'),('_b7_admission_sha','_mixed_admission_sha'),
           ('PL_cleanup_mandatory=True',"PL_cleanup_mandatory=False,airway_cleanup_backend='PS_original_clean_mask',explicit_hybrid=True"),
           ("else 'dfx_pl',input_sha256=digest","else 'explicit_hybrid_PL_medical',input_sha256=digest")]
    before=source;counts=[]
    for a,b in edits:
        count=source.count(a)
        if count!=(2 if a in ['str(_b7_admission)','_b7_admission_sha'] else 1):raise ValueError('Changed complete dispatcher: '+a)
        counts.append(count);source=source.replace(a,b)
    reverse=source
    for a,b in reversed(edits):reverse=reverse.replace(b,a)
    assert reverse==before;ast.parse(source);return source,dict(literal_edits=edits,counts=counts,reverse_exact=True)

def install(admission,digest,run_parent,repeats):
    candidate=verify(admission,digest)
    from modules.segmentation.standalone_B7_r1 import backend as parent
    binding=ROOT/candidate['parent_runtime_manifest'];backend=parent.install(binding,candidate['parent_runtime_manifest_SHA256'],run_parent,repeats)
    original,_=parent.derive(parent.parent_module().derived_dispatch()[0]);source,record=derive(original)
    backend.__dict__.update(_mixed_here=HERE,_mixed_admission=Path(admission),_mixed_admission_sha=digest)
    exec(compile(source,str(HERE/'backend.py')+':explicit_hybrid_complete_dispatch','exec'),backend.__dict__)
    backend.hybrid_dispatch_derivation=record
    return backend

def main():
    p=argparse.ArgumentParser(add_help=False);p.add_argument('--admission',type=Path,required=True);p.add_argument('--admission-sha256',required=True)
    p.add_argument('--run-parent',type=Path,required=True);p.add_argument('--repeats',type=int,default=1);a,rest=p.parse_known_args()
    backend=install(a.admission,a.admission_sha256,a.run_parent,a.repeats)
    head=argparse.ArgumentParser(add_help=False);head.add_argument('action');head.add_argument('--mode');known,_=head.parse_known_args(rest)
    if known.action=='run' and known.mode=='segmentation':
        q=argparse.ArgumentParser();q.add_argument('action');q.add_argument('--mode');q.add_argument('--input',type=Path,required=True);q.add_argument('--stop-file',type=Path)
        v=q.parse_args(rest);return backend.run(v.input,'segmentation',None,0,1.,.2,v.stop_file,0.)
    sys.argv=[sys.argv[0],*rest]
    import backend_selected_r1 as accepted
    return accepted.main()

if __name__=='__main__':
    try:main()
    except Exception as e:print(json.dumps(dict(event='error',text=str(e)),ensure_ascii=False),flush=True);raise
