"""Keep real D6/C5 inference; defer PS airway CCL/audit to the following B7 stage."""
from pathlib import Path
import argparse,ast,hashlib,json,sys
from admission import ROOT,HERE,verify,read,write,sha
sys.path.insert(0,str(ROOT))
def derive(source):
    edits=[('    if physical:masks[\'airway\'],refinement=largest_airway_component(masks[\'airway\'])\n    else:masks[\'airway\'],refinement=refine_airway(image,masks[\'airway\'],include_proximal=False)',
            "    if not physical:raise ValueError('Complete B7 route requires physical-context model')\n    refinement=dict(policy='deferred_PL_B7',PS_connected_component_executed=False)"),
           ('    if logits_metadata is not None and same_grid:', '    if False and logits_metadata is not None and same_grid:'),
           ("    report={'status':'completed'", "    report={'mask_foreground_voxels':{n:int(np.count_nonzero(v))for n,v in masks.items()},'status':'completed'")]
    before=source
    for a,b in edits:
        if source.count(a)!=1:raise ValueError('Changed original worker cleanup/audit boundary')
        source=source.replace(a,b)
    reverse=source
    for a,b in reversed(edits):reverse=reverse.replace(b,a)
    assert reverse==before;ast.parse(source)
    return source,edits
def main():
    p=argparse.ArgumentParser();p.add_argument('--admission',type=Path,required=True);p.add_argument('--admission-sha256',required=True)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--job-lock-fd',type=int);p.add_argument('--repeats',type=int,default=1);a=p.parse_args();verify(a.admission,a.admission_sha256)
    from modules.segmentation.axis_tensor_reader_r3.streaming_r1 import entry as stage,functional
    from modules.segmentation.axis_tensor_reader_r3.reporting_r2.assignment import describe
    old_derive=functional.derive_worker;old_run=functional.run_worker
    def derived():
        released,bounded,source,record=old_derive();source,edits=derive(source)
        record.update(complete_B7_source_SHA256=hashlib.sha256(source.encode()).hexdigest(),complete_B7_literal_edits=edits)
        return released,bounded,source,record
    def run(args,prepared,record):
        r,delta=describe(old_run(args,prepared,record))
        r.update(status='awaiting_PL_airway_cleanup',airway_detail=dict(status='deferred_until_PL_cleanup'),PS_airway_CCL_executed=False,
                 airway_cleanup_pending=dict(backend='PL_B7_U8_AXIS',closing=1,admission_SHA256=a.admission_sha256),
                 complete_B7_candidate=True)
        r['agreement_with_pc'].pop('airway',None)
        r['ps_operators']=r['ps_operators'].replace(', main airway connected component','').replace(', sparse discarded-airway candidate audit','')
        r['operator_assignment']['PS']=[v for v in r['operator_assignment']['PS']if 'main airway connected component'not in v]
        write(args.output/'deferred_worker_derivation.json',r['source_worker_derivation'])
        write(args.output/'operator_assignment.json',dict(delta,deferred_CCL_and_audit=True))
        return r
    functional.derive_worker=derived;functional.run_worker=run
    a.reference_dir=None;a.preview=False
    try:stage.run(a)
    finally:functional.derive_worker=old_derive;functional.run_worker=old_run
    write(a.output/'status.json',dict(status='awaiting_PL_airway_cleanup',stage='airway-cleanup',PS_airway_CCL_executed=False))
if __name__=='__main__':main()
