"""Bound whole-volume lifetimes; retain frozen HU/convolution/26-connectivity math.

The validation entry omits diagnostic logits and previews, as did its baseline.
It retains every source slice, all model outputs and original physical geometry.
"""
from pathlib import Path
import ast
import gc
import hashlib
import inspect
import json
import time

import numpy as np
import SimpleITK as sitk

SYSTEM = Path(__file__).resolve().parents[4]


class Geometry:
    def __init__(self, image):
        for key in ('Size', 'Spacing', 'Origin', 'Direction'):
            setattr(self, key.lower(), tuple(getattr(image, 'Get' + key)()))

    def GetSize(self): return self.size
    def GetSpacing(self): return self.spacing
    def GetOrigin(self): return self.origin
    def GetDirection(self): return self.direction

    def apply(self, image):
        assert image.GetSize() == self.size
        for key in ('Spacing', 'Origin', 'Direction'):
            getattr(image, 'Set' + key)(getattr(self, 'Get' + key)())


class VolumeShape:
    def __init__(self, shape): self.shape = tuple(shape)
    def __len__(self): return self.shape[0]


def write_like(array, reference, path):
    if tuple(array.shape) != tuple(reversed(reference.GetSize())):
        raise ValueError('Array shape differs from CT')
    image = sitk.GetImageFromArray(array)
    reference.apply(image)
    sitk.WriteImage(image, str(path), True)


def restore_mask(mask, image, original):
    pred = sitk.GetImageFromArray(mask)
    image.apply(pred)
    filt = sitk.ResampleImageFilter()
    filt.SetSize(original.GetSize())
    for key in ('Spacing', 'Origin', 'Direction'):
        getattr(filt, 'SetOutput' + key)(getattr(original, 'Get' + key)())
    filt.SetTransform(sitk.Transform())
    filt.SetInterpolator(sitk.sitkNearestNeighbor)
    filt.SetDefaultPixelValue(0)
    filt.SetOutputPixelType(sitk.sitkUInt8)
    return sitk.GetArrayFromImage(filt.Execute(pred))


def largest_airway_component(raw):
    """Same 26-connected largest-component rule; bound bincount's intp copy."""
    from scipy import ndimage as ndi
    mask = np.asarray(raw, dtype=bool)
    if not np.any(mask):
        return np.zeros(mask.shape, np.uint8), dict(policy='largest_26_connected', input_voxels=0, kept_voxels=0)
    bounds = []
    for axis in range(3):
        idx = np.flatnonzero(np.any(mask, axis=tuple(a for a in range(3) if a != axis)))
        bounds.append(slice(int(idx[0]), int(idx[-1]) + 1))
    region = tuple(bounds)
    lab, n = ndi.label(mask[region], np.ones((3, 3, 3), np.uint8))
    counts = np.zeros(n + 1, np.int64)
    flat = lab.reshape(-1)
    for start in range(0, len(flat), 1 << 20):
        counts += np.bincount(flat[start:start + (1 << 20)], minlength=n + 1)
    counts[0] = 0
    selected = int(np.argmax(counts))
    out = np.zeros(mask.shape, np.uint8)
    out[region] = lab == selected
    return out, dict(policy='largest_26_connected', input_voxels=int(mask.sum()),
                     kept_voxels=int(counts[selected]), components=int(n))


def require_mode(args):
    if args.scheduler != 'fused' or args.save_airway_logits or not args.no_preview or args.reference_dir is not None:
        raise ValueError('This validation entry requires fused complete masks, no diagnostic logits/preview/reference comparison')


def prepare_ct(args):
    require_mode(args)
    from modules.ct_preprocess.axis_hu_32_r2.integrated_r1 import prepare as released
    started = time.perf_counter()
    original = released.read_ct(args.input)
    phases = dict(ct_read_seconds=time.perf_counter() - started)
    plan = json.loads((args.model_dir / 'graph.json').read_text())
    if args.model_dir.resolve() != released.MODEL.resolve() or 'preprocessing' not in plan:
        raise ValueError('The qualified physical-context model is required')
    tick = time.perf_counter()
    image = released.prepare_grid(original)
    original_geometry, network_geometry = Geometry(original), Geometry(image)
    source_bytes = int(sitk.GetArrayViewFromImage(original).nbytes)
    del original
    gc.collect()
    # A read-only view shares the SITK storage and avoids another full int16 CT.
    ct = sitk.GetArrayViewFromImage(image)
    if ct.dtype != np.int16 or ct.ndim != 3 or min(ct.shape) < 1 or max(ct.shape[1:]) > 512:
        raise ValueError('The original nonempty <=512x512 int16 network grid is required')
    phases['geometry_grid_seconds'] = time.perf_counter() - tick
    table, metadata = released.model_table()
    released.write_json(args.output / 'status.json', dict(status='running', stage='PL_HU_preprocessing',
        backend='DFX_PL_HU_AXIS_D6', pid=released.os.getpid()))
    tick = time.perf_counter()
    with released.Session() as session:
        quantized, metrics = released.quantize_volume(session, ct, table, chunk_voxels=1 << 23)
        metrics['open'] = session.open_metrics
    metrics.update(open_stream_and_drained_close_seconds=time.perf_counter() - tick,
        HU_quantization_backend='DFX_PL_HU_AXIS_D6', parallel_HU_lanes=32, input_word_loop_II=1,
        geometry_and_context_layout_backend='PS', quantized_SHA256=hashlib.sha256(quantized).hexdigest(),
        model=metadata, source_shape_zyx=list(ct.shape), no_PS_quantization_or_fallback=True,
        D6_drained_closed_and_isolated_before_C5_open=True)
    shape = ct.shape
    released_bytes = source_bytes + 2 * ct.nbytes
    del ct, image
    gc.collect()
    metrics['bounded_data_lifetime'] = dict(original_pixels_released_before_HU=True,
        full_int16_copy_not_created=True, network_pixels_released_before_C5=True,
        original_and_network_geometry_preserved=True,
        released_or_avoided_full_volume_bytes_before_C5=released_bytes,
        retained_quantized_bytes=quantized.nbytes, no_slice_or_voxel_subset=True)
    quantized.flags.writeable = False
    phases['PL_HU_preprocessing_seconds'] = metrics['open_stream_and_drained_close_seconds']
    released.write_json(args.output / 'preprocessing.json', metrics)
    return dict(started=started, original=original_geometry, image=network_geometry,
        ct=VolumeShape(shape), phases=phases, quantized=quantized, metadata=metadata, metrics=metrics)


def derive_worker(original_source, expected_SHA256):
    assert hashlib.sha256(original_source.encode()).hexdigest() == expected_SHA256
    old = """            pred=sitk.GetImageFromArray(mask);pred.CopyInformation(image)
            masks[name]=sitk.GetArrayFromImage(sitk.Resample(pred,original,sitk.Transform(),sitk.sitkNearestNeighbor,0,sitk.sitkUInt8))"""
    edits = [(old, '            masks[name]=restore_mask(mask,image,original)'),
        ('    finally:b.close()', '    finally:b.close()\n    del prepare\n    prepared.pop("quantized")\n    gc.collect()'),
        ('    post=time.perf_counter()-tick', '    post=time.perf_counter()-tick\n    del raw_airway\n    gc.collect()')]
    candidate = original_source
    for before, after in edits:
        assert candidate.count(before) == 1, before
        candidate = candidate.replace(before, after)
    reverse = candidate
    for before, after in reversed(edits):
        assert reverse.count(after) == 1
        reverse = reverse.replace(after, before)
    assert reverse == original_source
    ast.parse(candidate)
    return candidate, edits


def worker(args, prepared):
    require_mode(args)
    from modules.ct_preprocess.axis_hu_32_r2.integrated_r1 import run_segmentation as released
    manifest = json.loads((Path(__file__).parent / 'derivation.json').read_text())
    original = inspect.getsource(released.worker)
    candidate, _ = derive_worker(original, manifest['original_worker_function_SHA256'])
    namespace = dict(vars(released), write_like=write_like, restore_mask=restore_mask,
        largest_airway_component=largest_airway_component, gc=gc)
    exec(compile(candidate, str(Path(__file__)) + ':exact_frozen_worker_lifetimes', 'exec'), namespace)
    namespace['worker'](args, prepared)
