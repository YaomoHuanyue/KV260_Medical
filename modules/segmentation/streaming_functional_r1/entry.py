"""Functional D6 -> C5 convolution/three-pool entry, original complete outputs.

An explicit owned trial coordinates the qualified C5 partial. This entry never
installs firmware, changes the formal CLI, or falls back to PS pooling.
"""
from pathlib import Path
import argparse,ast,hashlib,json,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def configure_imports():
    # The formal worker normally establishes these paths before preparation.
    # A standalone entry must do so before prepare_ct imports ct_pl.run.
    sys.path[:0]=[str(ROOT),str(ROOT/'modules/segmentation'),str(ROOT/'dfx/medical')]


def verify(admission):
    path=Path(admission).resolve()
    if not path.is_file():raise RuntimeError('Explicit functional candidate admission required before imports, outputs or hardware')
    if not path.is_relative_to(ROOT):raise ValueError('Admission must belong to this integration project')
    record=json.loads(path.read_text())
    if record.get('schema')!='kv260.streaming.functional.segmentation.v1':raise ValueError('Unsupported functional candidate admission')
    if record.get('candidate_kind')!='functional_not_performance_qualified' or record.get('all_operators_on_PL') is not False:
        raise ValueError('Candidate must retain its incomplete-network and failed-speed disclosure')
    required={'full139_pool_board','full139_fair_comparison','pool_hardware_admission','full139_D6_outputs'}
    if set(record.get('proofs',{}))!=required:raise ValueError('All existing functional hardware proofs required')
    for name,digest in record['source_SHA256'].items():
        p=(ROOT/name).resolve()
        if not p.is_relative_to(ROOT) or not p.is_file() or sha(p)!=digest:raise ValueError('Changed candidate source: '+name)
    for role,row in record['proofs'].items():
        p=(ROOT/row['path']).resolve()
        if not p.is_relative_to(ROOT) or sha(p)!=row['SHA256']:raise ValueError('Changed functional proof: '+role)
    comparison=json.loads((ROOT/record['proofs']['full139_fair_comparison']['path']).read_text())
    if comparison.get('all16_complete139_volumes_and2224_original_float32_tensors_exact') is not True:
        raise ValueError('Complete actual full139 output proof required')
    if comparison.get('actual_complete139_performance_gate_passed') is not False:
        raise ValueError('Do not rewrite the original failed speed gate')
    actual=json.loads((ROOT/record['proofs']['full139_pool_board']['path']).read_text())
    if actual.get('all139_actual_ARM_PL_2502_layer_inputs139_logits417_pools_exact') is not True:
        raise ValueError('Actual full139 PL pool correctness proof required')
    hardware=json.loads((ROOT/record['proofs']['pool_hardware_admission']['path']).read_text())
    if (hardware.get('schema')!='kv260.ct_pool.hardware_trial.v1' or hardware.get('writer_control_address_bits')!=8 or
        hardware.get('pool_shape_offset')!=128 or hardware.get('partial_SHA256')!=record['new_partial_SHA256'] or
        hardware.get('library_SHA256')!=record['source_SHA256'].get(record['pool_library'])):
        raise ValueError('Exact qualified eight-bit-control pool host and partial required')
    return record


def derive_worker():
    """Keep the complete accepted worker, including bounded lifetimes and audit."""
    sys.path.insert(0,str(ROOT))
    import inspect
    from modules.ct_preprocess.axis_hu_32_r2.integrated_r1 import run_segmentation as released
    from modules.ct_preprocess.axis_hu_32_r2.bounded_volume_r3 import runtime as bounded
    proof=json.loads((bounded.Path(bounded.__file__).parent/'derivation.json').read_text())
    original=inspect.getsource(released.worker)
    source,_=bounded.derive_worker(original,proof['original_worker_function_SHA256'])
    before='        from ct_pl.fused_graph import FusedGraph\n        graph_type=FusedGraph'
    after='        from modules.segmentation.ct_pool_fusion_r1.integration_r1.pool_graph import PoolGraph\n        graph_type=PoolGraph'
    if source.count(before)!=1:raise RuntimeError('The complete original worker changed')
    candidate=source.replace(before,after)
    if candidate.replace(after,before)!=source:raise RuntimeError('Worker derivation is not exactly reversible')
    ast.parse(candidate)
    return released,bounded,candidate,dict(parent_worker_SHA256=hashlib.sha256(original.encode()).hexdigest(),
        bounded_worker_SHA256=hashlib.sha256(source.encode()).hexdigest(),
        candidate_worker_SHA256=hashlib.sha256(candidate.encode()).hexdigest(),literal_edit=[before,after])


def run_worker(args,prepared,record):
    released,bounded,source,derivation=derive_worker()
    import gc,os,time
    from modules.segmentation.ct_pool_fusion_r1.host_dual_r1.backend import PoolXRT
    captures=[]
    class CandidatePool(PoolXRT):
        def __init__(self,output_pool=False):
            if output_pool is not True:raise ValueError('Full and pooled native leases required')
            super().__init__(ROOT/record['pool_library'],ROOT/record['proofs']['pool_hardware_admission']['path'])
        def close(self):
            if self.handle:
                captures.append(dict(real_PL_convolution_calls=self.calls,real_PL_pool_calls=self.pool_calls))
            return super().close()
    namespace=dict(vars(released),backend=CandidatePool,write_like=bounded.write_like,restore_mask=bounded.restore_mask,
        largest_airway_component=bounded.largest_airway_component,gc=gc)
    exec(compile(source,str(HERE/'entry.py')+':original_complete_worker_with_PL_pools','exec'),namespace)
    namespace['worker'](args,prepared)
    gc.collect()
    if len(captures)!=1:raise RuntimeError('Missing or repeated pool backend lifecycle')
    counts=captures[0]
    slices=json.loads((args.output/'preprocessing.json').read_text())['source_shape_zyx'][0]
    if counts['real_PL_convolution_calls']!=18*(1+args.repeats*slices) or counts['real_PL_pool_calls']!=3*(1+args.repeats*slices):
        raise RuntimeError('Incomplete PL convolution/pool coverage')
    report=json.loads((args.output/'report.json').read_text())
    report.update(functional_candidate='DFX_D6_HU32_C5_three_PL_pools_r1',candidate_kind='functional_not_performance_qualified',
        all_operators_on_pl=False,pl_pool_calls=counts['real_PL_pool_calls'],all_three_original_pools_on_PL=True,
        no_PS_pool_fallback=True,complete_original_masks_logits_audit_geometry_and_reference_outputs_retained=True,
        source_worker_derivation=derivation,known_performance_regression_vs_formal_C5=True,
        phase2_performance_qualification_pending=True)
    report['pl_operators']+='; all three original max-pool/ReLU/requantize chains fused into C5 AXIS writer'
    report['ps_operators']=report['ps_operators'].replace(', pooling,',',')
    released.write_json(args.output/'report.json',report)
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--admission',type=Path,required=True)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--trial-coordinator',type=Path,required=True)
    args=parser.parse_args()
    record=verify(args.admission)
    # The coordinator is an owned explicit transaction, never a user bypass.
    coordinator=args.trial_coordinator.resolve()
    expected=record['coordinator']
    if not coordinator.is_relative_to(ROOT) or sha(coordinator)!=expected['SHA256']:
        raise RuntimeError('Unqualified functional DFX coordinator')
    args.input=args.input.resolve();args.output=args.output.resolve()
    if args.output.exists() or not args.output.is_relative_to(ROOT):raise ValueError('Fresh result directory inside this project required')
    if sha(args.input)!=record['input_CT_SHA256']:raise ValueError('This first complete-system trial requires the original full CT')
    configure_imports();sys.path.insert(0,str(coordinator.parent))
    import importlib.util
    spec=importlib.util.spec_from_file_location('owned_streaming_functional_transaction',coordinator)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    # No output creation or PL access until source/CT/coordinator gates pass.
    module.run(args,record,run_worker)


if __name__=='__main__':main()
