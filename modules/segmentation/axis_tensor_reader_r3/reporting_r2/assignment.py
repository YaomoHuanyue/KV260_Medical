"""Correct operator descriptions without changing tensors, timings or algorithms."""
from pathlib import Path
import copy,hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
PS='file decoding and geometry conversion, bounded five-plane context layout, layer scheduling and scalar/lease metadata, final mask threshold, main airway connected component, sparse discarded-airway candidate audit, geometry restoration and saving'

def describe(report):
    if report.get('functional_candidate')!='DFX_D6_HU32_C5_R3_reader_LUT_resize_concat_three_PL_pools_r1':
        raise ValueError('Operator descriptions require the actual qualified R3 worker')
    conv,pool,reader=[report.get(n,0) for n in ('pl_conv_calls','pl_pool_calls','pl_reader_calls')]
    if conv<=0 or conv%18 or pool!=conv//6 or reader!=conv//3:
        raise ValueError('Incomplete actual R3 convolution/pool/reader coverage')
    if report.get('PS_layer_transform_status')!='ReaderGraph sends all six transformed tensors directly to qualified PL reader; no PS transform fallback':
        raise ValueError('Missing R3 transform execution declaration')
    result=copy.deepcopy(report)
    result['ps_operators']=PS
    result['operator_assignment']=dict(schema='kv260.ct_R3.actual_operator_assignment.v2',
        PL=['D6 HU clipping/normalization/INT8 quantization','all18 INT8 convolution/requantization',
            'eight fused activation chains','three max-pool/ReLU/requantization chains',
            'six deferred LUT/nearest-resize/channel-concat tensor transforms'],
        PS=['file decoding and geometry conversion','bounded five-plane context layout','layer scheduling and scalar/lease metadata',
            'final mask threshold','main airway connected component and sparse discarded-candidate audit','geometry restoration and saving'],
        graph_Relu_Resize_Concat_nodes_are_PS_metadata_full_payload_is_PL=True,
        per_slice_reader_transform_calls=6,actual_reader_calls=reader,
        source_inventory='modules/segmentation/axis_tensor_reader_r3/operator_roles_r1/verified.json',
        all_operators_on_PL=False,silent_PS_fallback=False)
    unchanged={k:v for k,v in result.items() if k not in ('ps_operators','operator_assignment')}
    original={k:v for k,v in report.items() if k not in ('ps_operators','operator_assignment')}
    assert unchanged==original
    return result,dict(only_changed_keys=['ps_operators','operator_assignment'],
        original_PS_description=report['ps_operators'],new_PS_description=PS,
        all_computational_outputs_counts_and_timing_fields_unchanged=True)

def write_report(args,report):
    result,delta=describe(report)
    output=Path(args.output)
    receipt=output/'operator_assignment.json'
    if receipt.exists():raise FileExistsError('Do not rewrite a previous assignment receipt')
    delta.update(assignment_source_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        source_inventory_SHA256=hashlib.sha256((ROOT/'modules/segmentation/axis_tensor_reader_r3/operator_roles_r1/verified.json').read_bytes()).hexdigest())
    with receipt.open('x',encoding='utf-8') as f:json.dump(delta,f,indent=2)
    # The parent stage owns this fresh output and publishes its final report
    # after adding its normal lifecycle/timing fields. No sealed result changes.
    return result
