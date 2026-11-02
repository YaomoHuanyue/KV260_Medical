"""Identified inputs and independent review outputs; preserve scalar geometry."""
from pathlib import Path
import hashlib
import json
import time
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def geometry(image):
    return dict(size_xyz=list(image.GetSize()), spacing_xyz_mm=list(image.GetSpacing()),
                origin_lps_mm=list(image.GetOrigin()), direction=list(image.GetDirection()))


def load_inputs(ct_path, segmentation, lesion_index):
    ct_path, folder = Path(ct_path).resolve(), Path(segmentation).resolve()
    report = json.loads((folder / 'report.json').read_text(encoding='utf-8'))
    if report.get('status') != 'completed':
        raise ValueError('Require completed segmentation')
    lm = json.loads((folder / 'airway_logits.json').read_text(encoding='utf-8'))
    logit_path = (folder / lm['file']).resolve()
    if logit_path.parent != folder or logit_path.name != lm['file']:
        raise ValueError('Invalid logit path')
    digest = sha(ct_path)
    if (digest != report['input_sha256'] or digest != lm['input_sha256'] or
            lm['model_sha256'] != report['model_sha256'] or sha(logit_path) != lm['sha256']):
        raise ValueError('CT/model/logit identity mismatch')
    image = sitk.ReadImage(str(ct_path))
    if image.GetDimension() != 3 or image.GetNumberOfComponentsPerPixel() != 1:
        raise ValueError('Require scalar 3D CT')
    expected = geometry(image)
    direction = np.asarray(image.GetDirection()).reshape(3, 3)
    if (not np.isfinite(direction).all() or not np.allclose(direction.T @ direction, np.eye(3), rtol=0, atol=1e-6)
            or not np.isfinite(image.GetSpacing()).all() or min(image.GetSpacing()) <= 0):
        raise ValueError('Require positive spacing and orthonormal image direction')
    for key, method in [('size_xyz', 'GetSize'), ('spacing_xyz_mm', 'GetSpacing'),
                        ('origin_xyz_mm', 'GetOrigin'), ('direction', 'GetDirection')]:
        if not np.allclose(lm[key], getattr(image, method)(), rtol=0, atol=1e-6):
            raise ValueError('Logit geometry mismatch; no implicit resampling')
    arrays, protected = {}, [ct_path, logit_path, folder / 'report.json', folder / 'airway_logits.json']
    before = {str(p): sha(p) for p in protected}
    if before[str(ct_path)] != digest or before[str(logit_path)] != lm['sha256']:
        raise ValueError('Input changed during initial validation')
    for name in ['airway_mask_network.nii.gz', 'airway_mask.nii.gz', 'nodule_mask.nii.gz']:
        path = folder / name; before[str(path)] = sha(path); other = sitk.ReadImage(str(path))
        if (other.GetDimension() != 3 or other.GetNumberOfComponentsPerPixel() != 1 or
                other.GetSize() != image.GetSize() or any(not np.allclose(getattr(image, method)(), getattr(other, method)(), rtol=0, atol=1e-6)
                for method in ['GetSpacing', 'GetOrigin', 'GetDirection'])):
            raise ValueError('Mask geometry mismatch; no implicit resampling')
        values = sitk.GetArrayFromImage(other)
        if np.any((values != 0) & (values != 1)):
            raise ValueError('Non-binary mask')
        arrays[name] = values > 0; protected.append(path)
    labels, count = ndi.label(arrays['nodule_mask.nii.gz'], np.ones((3, 3, 3), np.uint8))
    sizes = np.bincount(labels.ravel()); order = sorted(range(1, count + 1), key=lambda i: (-sizes[i], i))
    if not 0 <= lesion_index < count:
        raise ValueError('Candidate index outside available components')
    label = int(order[lesion_index]); lesion = labels == label
    ct = sitk.GetArrayFromImage(image); logits = np.load(logit_path, mmap_mode='r', allow_pickle=False)
    if logits.shape != ct.shape or logits.dtype != np.dtype(lm['dtype']) or logits.dtype not in [np.dtype('int8'), np.dtype('float32')]:
        raise ValueError('Unsupported recorded logits')
    scale, zero = float(lm['scale']), float(lm['zero'])
    if not np.isfinite([scale, zero]).all() or scale <= 0:
        raise ValueError('Invalid stored quantization')
    probability = np.empty(ct.shape, np.float32)
    for z in range(len(ct)):
        if (not np.isfinite(ct[z]).all() or not np.isfinite(logits[z]).all() or
                not np.array_equal(logits[z] >= zero, arrays['airway_mask_network.nii.gz'][z])):
            raise ValueError('CT/logit values or recorded threshold mismatch')
        values = (logits[z].astype(np.float32) - zero) * scale
        probability[z] = 1 / (1 + np.exp(-np.clip(values, -80, 80)))
    if before != {str(p): sha(p) for p in protected}:
        raise ValueError('Input changed while being read')
    identity = dict(input_sha256=digest, model_sha256=lm['model_sha256'], geometry=expected,
        inputs_sha256=before, candidate_index_zero_based=lesion_index,
        candidate_component_label=label, candidate_voxels=int(sizes[label]),
        candidate_status='model_candidate_not_confirmed_lesion')
    return image, ct, arrays['airway_mask_network.nii.gz'], lesion, probability, identity


def save_outputs(output, image, results, identity, elapsed, source_sha256):
    save_begin = time.perf_counter()
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    recovered, high, review, candidates, details = results
    files = {}
    for name, values in [('experimental_merged', recovered), ('high', high), ('review', review), ('evidence', details['evidence'])]:
        name += '.nii.gz'
        saved = sitk.GetImageFromArray(values.astype(np.float32 if name.startswith('evidence') else np.uint8))
        saved.CopyInformation(image); sitk.WriteImage(saved, str(output / name), useCompression=True)
        files[name] = sha(output / name)
    for path, digest in identity['inputs_sha256'].items():
        if sha(path) != digest:
            raise RuntimeError('Protected input changed')
    report = dict(schema='kv260.airway_detail.recovery.v1', status='completed',
        **identity, summary=details['summary'], candidates=[c.to_dict() for c in candidates],
        backend=details['backend'], algorithm_seconds=details['total_seconds'],
        preparation_and_algorithm_seconds=elapsed, total_seconds=elapsed + time.perf_counter() - save_begin,
        files=files, source_sha256=source_sha256,
        accepted_mask_changed=False, synthetic_bridges='experimental_proposals_only',
        default_reconstruction_navigation_mask_replaced=False, PL_speed_claim=False)
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return report
