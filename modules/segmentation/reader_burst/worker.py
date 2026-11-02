"""Q15 reader migration with the original complete mixed segmentation worker.

Admission, native construction, stage tracking/locks and durable restoration are
provided by the caller. This module does not select firmware or touch the UI.
"""
from pathlib import Path
import ast,hashlib,inspect

ROOT=Path(__file__).resolve().parents[3]
BODY_SHA256='d37e8fdf66a333be264e2a4002009b6196fd20f55ae3d6aadadc511ace5f0433'
POLICY=dict(graph='FusedGraph_Q15_only',PL_reader_conv_ids=[15],Q15_channels=[16,16],Q15_factors=[1,1],
    Q15_shape=[1,32,512,512],PS_pool_chains=3,fused_activations=8,L14_original_order=True,
    PS_airway_cleanup='deferred_to_existing_cleanup',silent_PS_fallback=False,
    shared_backend_across_stages=False,allocation_sampling_added=False)


def require(ok,message):
    if not ok:raise ValueError(message)


def replace_exact(source,edits):
    original=source
    for before,after in edits:
        require(source.count(before)==1,'Changed or ambiguous original worker boundary: '+before[:80])
        source=source.replace(before,after)
    reverse=source
    for before,after in reversed(edits):reverse=reverse.replace(after,before)
    require(reverse==original,'Worker derivation must reverse exactly');ast.parse(source);return source


def derive(mixed=None):
    if mixed is None:
        from modules.segmentation.mixed_r30 import segmentation as mixed
    released,bounded,source,parent=mixed.derive()
    require(hashlib.sha256(source.encode()).hexdigest()==BODY_SHA256,'Original complete mixed worker body changed')
    edits=[('        from ct_pl.fused_graph import FusedGraph\n        graph_type=FusedGraph',
            '        from modules.segmentation.reader_burst.graph import get_graph_type\n        graph_type=get_graph_type()')]
    selected=replace_exact(source,edits)
    return released,bounded,selected,dict(parent=parent,reader_burst_policy=POLICY,literal_edits=edits,
        parent_worker_SHA256=BODY_SHA256,source_SHA256=hashlib.sha256(selected.encode()).hexdigest(),reverse_exact=True,
        threshold_geometry_LogitRecorder_status_save_and_finally_unchanged=True)


def derive_runner(mixed):
    source=inspect.getsource(mixed.run_worker)
    edits=[
        ('    expected=18*(1+args.repeats*slices)','    expected=18*(1+args.repeats*slices)\n    expected_reader=1+args.repeats*slices'),
        ('transform=0','transform=expected_reader'),('pl_reader_calls=0','pl_reader_calls=expected_reader'),
        ('actual_PL_reader_transform_calls=0','actual_PL_reader_transform_calls=expected_reader'),
        ("functional_candidate='explicit_hybrid_r30'","functional_candidate='reader_burst_Q15',reader_burst_policy=POLICY"),
        ("'eight fused activation chains']","'eight fused activation chains','Q15 dual16 factor1 source quantization/join in the PL reader over AXIS']"),
        ("'remaining LUT/resize/concat tensor operators'","'remaining LUT/resize/concat tensor operators except Q15'"),
        ('selection=\'Explicit hybrid selected before computation; no runtime fallback\'',
         'selection=\'Q15 reader selected before computation; other operators retain the original mixed policy; no runtime fallback\''),
        ('eight fused activation chains; AXIS payloads\'',
         'eight fused activation chains; Q15 dual16 factor1 PL reader quantization/join; AXIS payloads\''),
        ('pooling, remaining LUT/resize/concat, scheduling','pooling, remaining LUT/resize/concat except Q15, scheduling')]
    selected=replace_exact(source,edits)
    namespace=dict(vars(mixed),derive=lambda:derive(mixed),POLICY=POLICY)
    exec(compile(selected,str(Path(__file__))+':original_mixed_runner','exec'),namespace)
    return namespace['run_worker'],dict(parent_runner_SHA256=hashlib.sha256(source.encode()).hexdigest(),
        selected_runner_SHA256=hashlib.sha256(selected.encode()).hexdigest(),literal_edits=edits,reverse_exact=True,
        original_SelectedHybrid_constructor_close_tracker_and_counter_capture_unchanged=True)


def run_worker(args,prepared,record):
    from modules.segmentation.mixed_r30 import segmentation as mixed
    runner,_=derive_runner(mixed)
    # The original runner constructs/closes native.ReaderXRT through the stage's
    # installed tracker. It executes the complete original worker, then enforces
    # conv18*(1+repeats*slices), reader1+repeats*slices and pool0 on one context.
    return runner(args,prepared,record)
