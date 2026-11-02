"""Actual D6/C5 AXIS convolution with explicitly selected PS layer operators."""
from pathlib import Path
import argparse,ast,gc,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from modules.segmentation.mixed_r30.admission import ROOT,HERE,verify,read,write,sha
sys.path[:0]=[str(ROOT),str(ROOT/'modules/segmentation'),str(ROOT/'dfx/medical')]

def derive():
    from modules.segmentation.axis_tensor_reader_r3.streaming_r1.functional import derive_worker
    released,bounded,source,parent=derive_worker()
    edits=[
        ('        from modules.segmentation.axis_tensor_reader_r3.graph_r1.reader_graph import ReaderGraph\n        graph_type=ReaderGraph',
         '        from ct_pl.fused_graph import FusedGraph\n        graph_type=FusedGraph'),
        ("    if physical:masks['airway'],refinement=largest_airway_component(masks['airway'])\n    else:masks['airway'],refinement=refine_airway(image,masks['airway'],include_proximal=False)",
         "    if not physical:raise ValueError('Hybrid candidate requires the qualified physical model')\n    refinement=dict(policy='deferred_PS_hybrid_cleanup',PS_connected_component_executed=False)"),
        ('    if logits_metadata is not None and same_grid:','    if False and logits_metadata is not None and same_grid:'),
        ("    report={'status':'completed'","    report={'mask_foreground_voxels':{n:int(np.count_nonzero(v))for n,v in masks.items()},'status':'completed'")]
    before=source
    for a,b in edits:
        if source.count(a)!=1:raise ValueError('Changed hybrid worker boundary: '+a[:70])
        source=source.replace(a,b)
    reverse=source
    for a,b in reversed(edits):reverse=reverse.replace(b,a)
    assert reverse==before;ast.parse(source)
    return released,bounded,source,dict(parent=parent,literal_edits=edits,source_SHA256=hashlib.sha256(source.encode()).hexdigest(),reverse_exact=True)

def run_worker(args,prepared,record):
    released,bounded,source,derivation=derive()
    from modules.segmentation.axis_tensor_reader_r3.host_r1 import backend as native
    captures=[]
    class SelectedHybrid(native.ReaderXRT):
        def __init__(self,output_pool=False):
            if output_pool is not True:raise ValueError('Qualified output BO leases required')
            super().__init__(ROOT/record['pool_library'],ROOT/record['proofs']['pool_hardware_admission']['path'])
        def close(self):
            if self.handle:captures.append(dict(conv=self.calls,pool=self.pool_calls,transform=self.reader_calls))
            return super().close()
    namespace=dict(vars(released),backend=SelectedHybrid,write_like=bounded.write_like,
                   restore_mask=bounded.restore_mask,largest_airway_component=bounded.largest_airway_component,gc=gc)
    exec(compile(source,str(HERE/'segmentation.py')+':explicit_mixed_original_worker','exec'),namespace)
    namespace['worker'](args,prepared);gc.collect()
    slices=read(args.output/'preprocessing.json')['source_shape_zyx'][0]
    expected=18*(1+args.repeats*slices)
    if len(captures)!=1 or captures[0]!=dict(conv=expected,pool=0,transform=0):
        raise RuntimeError('Actual hybrid operator assignment differs from the selected policy')
    r=read(args.output/'report.json')
    r.update(status='awaiting_PS_airway_cleanup',backend='explicit_hybrid_D6_C5_PS_layers',
        functional_candidate='explicit_hybrid_r30',source_worker_derivation=derivation,
        pl_pool_calls=0,pl_reader_calls=0,all_three_original_pools_on_PL=False,
        PS_airway_CCL_executed=False,airway_cleanup_pending=dict(backend='PS_original_clean_mask',closing=1),
        silent_PS_fallback=False,all_operators_on_PL=False,
        operator_assignment=dict(PL=['D6 HU clipping/normalization/INT8 quantization over AXIS',
            'all18 C5 INT8 convolutions/requantization over AXIS','eight fused activation chains'],
            PS=['file decoding and geometry','bounded five-plane context layout','three max-pool chains',
                'remaining LUT/resize/concat tensor operators','layer scheduling and final mask threshold',
                'geometry restoration and saving'],
            selection='Explicit hybrid selected before computation; no runtime fallback',
            actual_PL_convolution_calls=expected,actual_PL_pool_calls=0,actual_PL_reader_transform_calls=0),
        pl_operators='D6 HU clipping/normalization/INT8 quantization; all18 C5 INT8 convolutions/requantization; eight fused activation chains; AXIS payloads',
        ps_operators='file decoding/geometry, five-plane context layout, pooling, remaining LUT/resize/concat, scheduling, final mask threshold, saving; main airway cleanup deferred',
        airway_detail=dict(status='deferred_until_explicit_PS_cleanup'))
    write(args.output/'operator_assignment.json',r['operator_assignment'])
    write(args.output/'deferred_worker_derivation.json',derivation)
    return r

def main():
    p=argparse.ArgumentParser();p.add_argument('--admission',type=Path,required=True);p.add_argument('--admission-sha256',required=True)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--job-lock-fd',type=int);p.add_argument('--repeats',type=int,default=1)
    a=p.parse_args();verify(a.admission,a.admission_sha256)
    if not 1<=a.repeats<=5:raise ValueError('Repeats outside1..5')
    from modules.segmentation.axis_tensor_reader_r3.streaming_r1 import entry as stage,functional
    original=functional.run_worker;functional.run_worker=run_worker
    a.reference_dir=None;a.preview=False
    try:stage.run(a)
    finally:functional.run_worker=original
    write(a.output/'status.json',dict(status='awaiting_PS_airway_cleanup',backend='explicit_hybrid_D6_C5_PS_layers'))

if __name__=='__main__':main()
