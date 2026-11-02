"""Validate self-contained partial segmentation and its derived results."""
from pathlib import Path
import numpy as np
import SimpleITK as sitk
from .importer import CLASSES, SCHEMA, geometry, header, inside, read, same_geometry, sha, validate_bundle


def validate_source(ct, folder):
    folder = Path(folder).resolve()
    report_file = folder / 'segmentation/report.json'
    if not report_file.is_file():
        return None
    report = read(report_file)
    if report.get('schema') != 'kv260.external.segmentation.v2':
        return None
    if (folder / 'external_import.json').exists():
        return validate_bundle(ct, folder)
    pipeline = read(folder / 'pipeline.json')
    if (pipeline.get('external_segmentation_report_sha256') != sha(report_file)
            or pipeline.get('input_sha256') != sha(ct)):
        raise ValueError('Derived external segmentation identity changed')
    _, g = header(ct)
    names = report.get('declared_structures')
    if (not isinstance(names, list) or not names
            or names != [n for n in CLASSES if n in names]
            or report.get('status') != 'completed'
            or report.get('input_sha256') != sha(ct)
            or not same_geometry(g, report.get('geometry', {}))):
        raise ValueError('Invalid derived partial segmentation catalogue')
    unavailable = [n for n in CLASSES if n not in names]
    if (report.get('unavailable_structures') != unavailable
            or report.get('structure_availability') != {n:'provided' if n in names else 'not_provided' for n in CLASSES}
            or pipeline.get('available_structures') != names
            or pipeline.get('unavailable_structures') != unavailable
            or set(report.get('images', {})) != set(names)):
        raise ValueError('Derived partial structure availability changed')
    expected = {f'segmentation/{n}_mask.nii.gz' for n in names}
    for name, item in report['images'].items():
        if item.get('selection') not in ('mask', 'probability_threshold'):
            raise ValueError('Invalid partial selection')
        if item.get('probability'):
            if item['probability'].get('file') != f'{name}_probability.nrrd':
                raise ValueError('Invalid partial probability artifact')
            expected.add(f'segmentation/{name}_probability.nrrd')
        if item['selection'] == 'probability_threshold' and 'mask' in item.get('sources', {}):
            expected.add(f'segmentation/{name}_mask_provided.nrrd')
    if set(report.get('files', {})) != expected:
        raise ValueError('Derived partial artifact inventory changed')
    for relative, digest in report['files'].items():
        path = inside(folder, relative)
        if sha(path) != digest or not same_geometry(g, header(path)[1]):
            raise ValueError('Derived partial image changed: '+relative)
    return report


def validate_selected_masks(ct, folder):
    """Complete input checks before opening XRT; no missing-class substitutes."""
    folder = Path(folder).resolve()
    report = validate_source(ct, folder)
    if report is None:
        raise ValueError('Expected an explicitly declared partial external result')
    inputs = {}
    for name in report['declared_structures']:
        path = folder / 'segmentation' / f'{name}_mask.nii.gz'
        image = sitk.ReadImage(str(path))
        a = sitk.GetArrayViewFromImage(image)
        if not same_geometry(geometry(image), report['geometry']) or not np.all((a == 0) | (a == 1)):
            raise ValueError('Partial mask must be binary in the CT coordinate system: '+name)
        count = int(np.count_nonzero(a))
        if count != report['images'][name]['foreground_voxels']:
            raise ValueError('Partial foreground count changed: '+name)
        inputs[name] = dict(filename=path.name, sha256=sha(path), foreground_voxels=count)
    for name in report['unavailable_structures']:
        if (folder / 'segmentation' / f'{name}_mask.nii.gz').exists():
            raise ValueError('Unexpected undeclared structure: '+name)
    return report, inputs


def require_navigation(ct, folder):
    report, inputs = validate_selected_masks(ct, folder)
    if not {'airway', 'nodule'}.issubset(inputs):
        raise ValueError('导航需要已提供的气道和病灶候选掩膜')
    if not inputs['airway']['foreground_voxels'] or not inputs['nodule']['foreground_voxels']:
        raise ValueError('导航需要非空的气道和病灶候选掩膜')
    return report
