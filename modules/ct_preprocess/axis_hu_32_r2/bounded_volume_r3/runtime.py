"""Bound CT lifetimes while retaining the frozen logits, previews, references and audit."""
from pathlib import Path
import ast
import gc
import hashlib
import inspect
import json
import time

import numpy as np
import SimpleITK as sitk
from modules.ct_preprocess.axis_hu_32_r2.bounded_volume_r2 import runtime as base

Geometry, VolumeShape = base.Geometry, base.VolumeShape
largest_airway_component = base.largest_airway_component


def geometry(image):
    return image if isinstance(image, Geometry) else Geometry(image)


def write_like(array, reference, path):
    return base.write_like(array, geometry(reference), path)


def restore_mask(mask, image, original):
    return base.restore_mask(mask, geometry(image), geometry(original))


def select_retained_inputs(args, original, image):
    """Retain only the pixel owner needed by each original requested output."""
    original_geometry, network_geometry = Geometry(original), Geometry(image)
    same = all(getattr(original_geometry, 'Get'+k)() == getattr(network_geometry, 'Get'+k)()
               for k in ('Size', 'Spacing', 'Origin', 'Direction'))
    ct = sitk.GetArrayViewFromImage(image)
    if ct.dtype != np.int16 or ct.ndim != 3 or min(ct.shape)<1 or max(ct.shape[1:])>512:
        raise ValueError('The original complete nonempty <=512x512 int16 CT grid is required')
    retain_network = same and (args.save_airway_logits or not args.no_preview)
    retain_original = not same and not args.no_preview
    # A raw CT array is consumed only by the same-grid audit. Otherwise all
    # network slices already come from the checked PL-quantized context volume.
    audit_view = same and args.save_airway_logits
    return dict(original=original if retain_original else original_geometry,
        image=image if retain_network else network_geometry,
        ct=ct if audit_view else VolumeShape(ct.shape),
        retention=dict(same_grid=same, network_pixels_retained_for_original_outputs=retain_network,
            original_pixels_retained_for_original_preview=retain_original,
            read_only_audit_CT_view=audit_view, full_numpy_CT_copy_created=False,
            diagnostic_logits_requested=bool(args.save_airway_logits), preview_requested=not args.no_preview,
            reference_comparison_requested=args.reference_dir is not None,
            original_pixel_bytes=int(sitk.GetArrayViewFromImage(original).nbytes), network_pixel_bytes=int(ct.nbytes)))


def require_mode(args):
    if args.scheduler != 'fused':
        raise ValueError('This bounded full-output entry requires the qualified fused physical-context model')


def prepare_ct(args):
    require_mode(args)
    from modules.ct_preprocess.axis_hu_32_r2.integrated_r1 import prepare as released
    started = time.perf_counter(); original = released.read_ct(args.input)
    phases = dict(ct_read_seconds=time.perf_counter()-started)
    plan = json.loads((args.model_dir/'graph.json').read_text())
    if args.model_dir.resolve() != released.MODEL.resolve() or 'preprocessing' not in plan:
        raise ValueError('The qualified physical-context model is required')
    tick = time.perf_counter(); image = released.prepare_grid(original)
    retained = select_retained_inputs(args, original, image)
    del original
    gc.collect()
    ct = sitk.GetArrayViewFromImage(image)
    phases['geometry_grid_seconds'] = time.perf_counter()-tick
    table, metadata = released.model_table()
    released.write_json(args.output/'status.json', dict(status='running', stage='PL_HU_preprocessing',
        backend='DFX_PL_HU_AXIS_D6', pid=released.os.getpid()))
    tick = time.perf_counter()
    with released.Session() as session:
        quantized, metrics = released.quantize_volume(session, ct, table, chunk_voxels=1<<23)
        metrics['open'] = session.open_metrics
    metrics.update(open_stream_and_drained_close_seconds=time.perf_counter()-tick,
        HU_quantization_backend='DFX_PL_HU_AXIS_D6', parallel_HU_lanes=32, input_word_loop_II=1,
        geometry_and_context_layout_backend='PS', quantized_SHA256=hashlib.sha256(quantized).hexdigest(),
        model=metadata, source_shape_zyx=list(ct.shape), no_PS_quantization_or_fallback=True,
        D6_drained_closed_and_isolated_before_C5_open=True,
        bounded_full_output_lifetimes=retained.pop('retention'))
    del ct, image
    gc.collect(); quantized.flags.writeable=False
    metrics['bounded_full_output_lifetimes']['all_slices_masks_logits_preview_reference_and_original_audit_policy_retained']=True
    metrics['bounded_full_output_lifetimes']['quantized_bytes']=quantized.nbytes
    phases['PL_HU_preprocessing_seconds']=metrics['open_stream_and_drained_close_seconds']
    released.write_json(args.output/'preprocessing.json', metrics)
    return dict(started=started, phases=phases, quantized=quantized, metadata=metadata, metrics=metrics, **retained)


def derive_worker(original_source, expected_SHA256):
    assert hashlib.sha256(original_source.encode()).hexdigest() == expected_SHA256
    old = """            pred=sitk.GetImageFromArray(mask);pred.CopyInformation(image)
            masks[name]=sitk.GetArrayFromImage(sitk.Resample(pred,original,sitk.Transform(),sitk.sitkNearestNeighbor,0,sitk.sitkUInt8))"""
    edits = [(old, '            masks[name]=restore_mask(mask,image,original)'),
        ('    finally:b.close()', '    finally:b.close()\n    del prepare\n    prepared.pop("quantized")\n    gc.collect()'),
        ('    post=time.perf_counter()-tick', '    post=time.perf_counter()-tick\n    if not a.save_airway_logits:raw_airway=None\n    gc.collect()')]
    candidate=original_source
    for before,after in edits:
        assert candidate.count(before)==1; candidate=candidate.replace(before,after)
    reverse=candidate
    for before,after in reversed(edits):
        assert reverse.count(after)==1; reverse=reverse.replace(after,before)
    assert reverse==original_source; ast.parse(candidate)
    return candidate,edits


def worker(args, prepared):
    require_mode(args)
    from modules.ct_preprocess.axis_hu_32_r2.integrated_r1 import run_segmentation as released
    proof=json.loads((Path(__file__).parent/'derivation.json').read_text())
    source=inspect.getsource(released.worker)
    candidate,_=derive_worker(source,proof['original_worker_function_SHA256'])
    namespace=dict(vars(released), write_like=write_like, restore_mask=restore_mask,
        largest_airway_component=largest_airway_component, gc=gc)
    exec(compile(candidate,str(Path(__file__))+':full_original_outputs_bounded_lifetimes','exec'),namespace)
    namespace['worker'](args,prepared)
