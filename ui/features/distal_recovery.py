"""Load separate, identified recovery evidence into CT review only."""
from pathlib import Path
import json
import numpy as np
import SimpleITK as sitk
from .airway_audit import sha, validate_geometry


def append_recovery_masks(result, image, packed, meta, input_sha):
    folder = Path(result) / 'airway_detail'
    path = folder / 'report.json'
    if not path.exists():
        return
    report = json.loads(path.read_text(encoding='utf-8'))
    if (report.get('schema') != 'kv260.airway_detail.recovery.v1' or
            report.get('status') != 'completed' or report.get('input_sha256') != input_sha or
            report.get('accepted_mask_changed') is not False or
            report.get('default_reconstruction_navigation_mask_replaced') is not False):
        raise ValueError('Invalid independent recovery report')
    expected = {'experimental_merged.nii.gz', 'high.nii.gz', 'review.nii.gz', 'evidence.nii.gz'}
    if set(report['files']) != expected:
        raise ValueError('Unexpected recovery output files')
    recorded = {Path(name).name: digest for name, digest in report['inputs_sha256'].items()}
    for name in ('airway_mask_network.nii.gz', 'airway_mask.nii.gz', 'nodule_mask.nii.gz',
                 'airway_logits.json', 'airway_logits.npy', 'report.json'):
        if sha(Path(result)/'segmentation'/name) != recorded.get(name):
            raise ValueError('Recovery evidence belongs to different segmentation')
    for name in sorted(expected):
        path = folder / name
        if sha(path) != report['files'][name]:
            raise ValueError('Recovery output identity mismatch')
        other = sitk.ReadImage(str(path)); validate_geometry(image, other)
        values = sitk.GetArrayViewFromImage(other)
        if name == 'evidence.nii.gz':
            if not np.isfinite(values).all() or values.min() < 0 or values.max() > 1:
                raise ValueError('Invalid recovery evidence range')
            continue
        if np.any((values != 0) & (values != 1)):
            raise ValueError('Invalid recovery binary mask')
        bit = {'high.nii.gz': 32, 'review.nii.gz': 64, 'experimental_merged.nii.gz': 128}[name]
        for z in range(len(values)):
            selected = values[z] > 0
            if bit == 32:
                selected = selected | ((packed[z] & 2) > 0)
            packed[z] |= selected.astype(np.uint8) * bit
    meta['distal_recovery'] = report
    meta.setdefault('airway_masks', {}).update(recovery_high=dict(bit=32),
        recovery_review=dict(bit=64), recovery_experimental=dict(bit=128))
