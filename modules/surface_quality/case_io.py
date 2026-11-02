"""Bind scalar preparation to the completed CT/model result and original grid."""
from pathlib import Path
import hashlib
import json
import numpy as np
import SimpleITK as sitk
from .field import geometry


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()


def assert_unchanged(identity):
    for name, digest in identity['inputs_sha256'].items():
        if sha(name) != digest: raise RuntimeError('Surface input changed: '+name)


def same_geometry(a, b):
    def components(image):
        return image.GetNumberOfComponentsPerPixel() if isinstance(image, sitk.Image) else image.GetNumberOfComponents()
    return (a.GetDimension() == b.GetDimension() == 3 and
        components(a) == components(b) == 1 and
        a.GetSize() == b.GetSize() and all(np.allclose(getattr(a, method)(), getattr(b, method)(),
        rtol=0, atol=1e-6) for method in ['GetSpacing', 'GetOrigin', 'GetDirection']))


def load_case(ct, segmentation, source):
    if source not in ('accepted_binary', 'network_probability'):
        raise ValueError('Unknown scalar source')
    ct, folder = Path(ct).resolve(), Path(segmentation).resolve()
    paths = [ct, folder/'report.json', folder/'airway_mask.nii.gz']
    if source == 'network_probability':
        paths += [folder/'airway_logits.json', folder/'airway_logits.npy', folder/'airway_mask_network.nii.gz']
    digests = {str(p): sha(p) for p in paths}
    report = json.loads((folder/'report.json').read_text(encoding='utf-8'))
    if report.get('status') != 'completed' or report.get('input_sha256') != digests[str(ct)]:
        raise ValueError('Completed segmentation must identify this CT')
    # Metadata check does not load the complete CT into a second in-memory array.
    reader = sitk.ImageFileReader(); reader.SetFileName(str(ct)); reader.ReadImageInformation()
    image = sitk.ReadImage(str(folder/'airway_mask.nii.gz'))
    if not same_geometry(image, reader):
        raise ValueError('Mask/CT geometry mismatch; no implicit resampling')
    mask = sitk.GetArrayFromImage(image)
    if np.any((mask != 0) & (mask != 1)) or not mask.any():
        raise ValueError('Require nonempty binary accepted airway mask')
    if source == 'network_probability':
        meta = json.loads((folder/'airway_logits.json').read_text(encoding='utf-8'))
        if (meta['file'] != 'airway_logits.npy' or meta['sha256'] != digests[str(folder/'airway_logits.npy')] or
                meta['input_sha256'] != digests[str(ct)] or meta['model_sha256'] != report['model_sha256']):
            raise ValueError('Logit CT/model/file identity mismatch')
        for name, method in [('size_xyz','GetSize'), ('spacing_xyz_mm','GetSpacing'),
                             ('origin_xyz_mm','GetOrigin'), ('direction','GetDirection')]:
            if not np.allclose(meta[name], getattr(image,method)(), rtol=0, atol=1e-6):
                raise ValueError('Logit geometry mismatch')
        raw_image = sitk.ReadImage(str(folder/'airway_mask_network.nii.gz'))
        if not same_geometry(image, raw_image): raise ValueError('Raw mask geometry mismatch')
        raw = sitk.GetArrayFromImage(raw_image)
        if np.any((raw != 0) & (raw != 1)): raise ValueError('Nonbinary raw mask')
        logits = np.load(folder/'airway_logits.npy', mmap_mode='r', allow_pickle=False)
        if (logits.shape != mask.shape or logits.dtype != np.dtype(meta['dtype']) or
                logits.dtype not in [np.dtype('int8'), np.dtype('float32')]):
            raise ValueError('Unsupported recorded logits')
        scale, zero = float(meta['scale']), float(meta['zero'])
        if not np.isfinite([scale,zero]).all() or scale <= 0: raise ValueError('Invalid logit quantization')
        values = np.empty(logits.shape, np.float32)
        for z in range(len(logits)):
            if not np.isfinite(logits[z]).all() or not np.array_equal(logits[z] >= zero, raw[z] > 0):
                raise ValueError('Recorded probability threshold mismatch')
            scalar = (logits[z].astype(np.float32)-zero)*scale
            values[z] = 1/(1+np.exp(-np.clip(scalar,-80,80)))
        probability = sitk.GetImageFromArray(values); probability.CopyInformation(image); image = probability
    identity = dict(input_sha256=digests[str(ct)], model_sha256=report['model_sha256'],
        scalar_source=source, inputs_sha256=digests, input_geometry=geometry(image),
        probability_mask_gating_applied=False, accepted_mask_replaced=False)
    assert_unchanged(identity)
    return image, identity


def save_field(folder, field, identity):
    assert_unchanged(identity)
    folder = Path(folder).resolve(); folder.mkdir(parents=True, exist_ok=False)
    target = folder/'field.npz'
    np.savez_compressed(target, format_version=np.array(6), sdf_q_zyx=field.sdf_q_zyx,
        spacing_xyz=field.spacing_xyz, origin_xyz=field.origin_xyz, direction=field.direction,
        bounds_lo=field.bounds_lo, bounds_hi=field.bounds_hi, scale_mm=np.array(field.scale_mm),
        gradient_sigma_mm=np.array(field.gradient_sigma_mm))
    from .field import c6_capacity
    report = dict(**field.report, identity=identity, C6_capacity=c6_capacity(field),
                  files={'field.npz':sha(target)})
    assert_unchanged(identity)
    (folder/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return report
