"""Import declared-CT binary masks/probabilities without implicit resampling.

SHA identity is a declaration by the producer, not anatomical or clinical proof.
This module performs file/geometry/value validation on PS. Its independent
segmentation bundle is consumable by the existing PL MC and smoothing stages.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import time
import uuid
import numpy as np
import SimpleITK as sitk

SCHEMA = 'kv260.external.images.v1'
CLASSES = ('lung', 'airway', 'nodule')
MAX_VOXELS = 256*1024*1024


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def inside(folder, name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise ValueError('Image file must be a relative POSIX path')
    rel = PurePosixPath(name)
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('Image file escapes the manifest directory')
    path = (Path(folder)/name).resolve()
    if not path.is_relative_to(Path(folder).resolve()) or not path.is_file():
        raise ValueError('Missing image or path escapes manifest directory')
    return path


def geometry(image):
    components = (image.GetNumberOfComponentsPerPixel() if isinstance(image, sitk.Image)
                  else image.GetNumberOfComponents())
    if image.GetDimension() != 3 or components != 1:
        raise ValueError('Require a scalar 3D image')
    size = list(image.GetSize()); spacing = list(image.GetSpacing())
    origin = list(image.GetOrigin()); direction = list(image.GetDirection())
    if (min(size) < 1 or math.prod(size) > MAX_VOXELS or min(spacing) <= 0
            or not np.isfinite(spacing+origin+direction).all()):
        raise ValueError('Invalid or oversized image geometry')
    d = np.asarray(direction).reshape(3, 3)
    if not np.allclose(d.T@d, np.eye(3), rtol=0, atol=1e-6):
        raise ValueError('Image direction must be orthonormal')
    return dict(size_xyz=size, spacing_xyz_mm=spacing, origin_lps_mm=origin,
                direction_row_major=direction, coordinates='LPS', units='mm', array_order='zyx')


def header(path):
    path = Path(path)
    lower = path.name.lower()
    if not lower.endswith(('.nrrd', '.nii', '.nii.gz')):
        raise ValueError('Only self-contained NRRD or NIfTI images are supported')
    if lower.endswith('.nrrd'):
        with path.open('rb') as stream:
            prefix = stream.read(65536)
        text = re.split(br'\r?\n\r?\n', prefix, maxsplit=1)
        if (len(text) != 2 or not text[0].startswith(b'NRRD')
                or re.search(br'^\s*data\s*file\s*:', text[0], re.I | re.M)):
            raise ValueError('Detached NRRD payloads require a different multi-file identity contract')
    reader = sitk.ImageFileReader(); reader.SetFileName(str(path)); reader.ReadImageInformation()
    return reader, geometry(reader)


def same_geometry(a, b):
    return a['size_xyz'] == b['size_xyz'] and all(np.allclose(a[k], b[k], rtol=0, atol=1e-6)
        for k in ('spacing_xyz_mm', 'origin_lps_mm', 'direction_row_major'))


def set_geometry(image, g):
    image.SetSpacing(g['spacing_xyz_mm']); image.SetOrigin(g['origin_lps_mm'])
    image.SetDirection(g['direction_row_major'])


def unchanged(bindings):
    for name, digest in bindings.items():
        if sha(name) != digest:
            raise ValueError('Input changed during import: '+name)


def import_bundle(ct, manifest, output):
    """Create a new self-contained mask/probability result for this exact CT."""
    ct, manifest, output = (Path(p).resolve() for p in (ct, manifest, output))
    if output.exists():
        raise FileExistsError('Choose a new output folder; imported results are immutable')
    if output == manifest.parent or manifest.parent in output.parents:
        raise ValueError('Output must be outside the input manifest directory')
    start = time.perf_counter(); spec = read(manifest)
    if spec.get('schema') != SCHEMA or set(spec.get('images', {})) != set(CLASSES):
        raise ValueError('Manifest must declare lung, airway and nodule images')
    digest = sha(ct)
    if spec.get('ct_sha256') != digest:
        raise ValueError('External images declare a different CT SHA256')
    provenance = spec.get('provenance')
    if not isinstance(provenance, dict) or not isinstance(provenance.get('origin'), str) or not provenance['origin'].strip():
        raise ValueError('Declare the external image producer in provenance.origin')
    reader, ct_geometry = header(ct)
    bindings = {str(ct):digest, str(manifest):sha(manifest)}
    sources = {}
    # Header/file checks precede all image allocations and output creation.
    for name in CLASSES:
        entry = spec['images'][name]
        if not isinstance(entry, dict) or entry.get('selection') not in ('mask', 'probability_threshold'):
            raise ValueError('Explicit mask/probability_threshold selection required: '+name)
        required = 'mask' if entry['selection'] == 'mask' else 'probability'
        if required not in entry or not set(entry).issubset({'mask', 'probability', 'selection'}):
            raise ValueError('Invalid image selection: '+name)
        sources[name] = {}
        for kind in ('mask', 'probability'):
            if kind not in entry:
                continue
            item = entry[kind]
            if not isinstance(item, dict) or not re.fullmatch(r'[0-9a-f]{64}', str(item.get('sha256', ''))):
                raise ValueError('Require the producer file SHA256: '+name)
            path = inside(manifest.parent, item.get('file'))
            if sha(path) != item['sha256']:
                raise ValueError('External image file SHA256 mismatch: '+name+'/'+kind)
            _, g = header(path)
            if not same_geometry(ct_geometry, g):
                raise ValueError('Image geometry does not match CT; no implicit resampling: '+name+'/'+kind)
            if kind == 'probability':
                t = item.get('threshold')
                if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or not 0 < t < 1:
                    raise ValueError('Probability threshold must be explicit and between 0 and 1')
            bindings[str(path)] = item['sha256']
            sources[name][kind] = dict(path=path, spec=item, input_geometry=g)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name('.'+output.name+'.'+uuid.uuid4().hex+'.import')
    temporary.mkdir(); (temporary/'segmentation').mkdir()
    outputs = {}; rows = {}; thresholds_seconds = 0.
    try:
        for name in CLASSES:
            selected = spec['images'][name]['selection']; mask = None; probability = None
            row = dict(selection=selected, sources={})
            for kind, item in sources[name].items():
                image = sitk.ReadImage(str(item['path'])); a = sitk.GetArrayViewFromImage(image)
                if not same_geometry(ct_geometry, geometry(image)) or not np.isfinite(a).all():
                    raise ValueError('Changed geometry or nonfinite voxels: '+name+'/'+kind)
                if kind == 'mask':
                    if not np.all((a == 0) | (a == 1)):
                        raise ValueError('Mask must be binary 0/1, no implicit label conversion: '+name)
                    mask = np.asarray(a, dtype=np.uint8).copy()
                else:
                    if not np.issubdtype(a.dtype, np.floating) or a.min() < 0 or a.max() > 1:
                        raise ValueError('Probability image must contain floating-point values in [0,1]: '+name)
                    probability = np.array(a, copy=True)
                    set_geometry(image, ct_geometry)
                    file = temporary/'segmentation'/f'{name}_probability.nrrd'
                    sitk.WriteImage(image, str(file), True)
                    outputs[file.relative_to(temporary).as_posix()] = sha(file)
                    row['probability'] = dict(file=file.name, dtype=str(a.dtype),
                        threshold=item['spec']['threshold'], mask_comparison='greater_or_equal')
                row['sources'][kind] = dict(file=item['spec']['file'], sha256=item['spec']['sha256'],
                                           geometry=item['input_geometry'])
                del a, image
            if selected == 'probability_threshold':
                begin = time.perf_counter()
                mask = np.asarray(probability >= sources[name]['probability']['spec']['threshold'], dtype=np.uint8)
                thresholds_seconds += time.perf_counter()-begin
            # The source mask is preserved separately when thresholding was explicitly chosen.
            if selected == 'probability_threshold' and 'mask' in sources[name]:
                original = sitk.ReadImage(str(sources[name]['mask']['path']))
                set_geometry(original, ct_geometry)
                file = temporary/'segmentation'/f'{name}_mask_provided.nrrd'
                sitk.WriteImage(original, str(file), True); outputs[file.relative_to(temporary).as_posix()] = sha(file)
            canonical = sitk.GetImageFromArray(mask); set_geometry(canonical, ct_geometry)
            file = temporary/'segmentation'/f'{name}_mask.nii.gz'
            sitk.WriteImage(canonical, str(file), True)
            outputs[file.relative_to(temporary).as_posix()] = sha(file)
            row['foreground_voxels'] = int(np.count_nonzero(mask)); rows[name] = row
            del canonical, mask, probability
        unchanged(bindings)
        report = dict(schema='kv260.external.segmentation.v1', status='completed', input_sha256=digest,
            backend='PS_external_image_validation', fresh_inference=False, clinical_accuracy_validated=False,
            identity_kind='producer_declared_CT_SHA256_and_exact_file_hashes', provenance=provenance,
            geometry=ct_geometry, images=rows, input_bindings=bindings, files=outputs,
            implicit_resampling=False, morphology_or_synthetic_bridges=False, probability_is_not_accuracy=True,
            threshold_seconds=thresholds_seconds, import_seconds=time.perf_counter()-start)
        write(temporary/'segmentation/report.json', report)
        write(temporary/'pipeline.json', dict(schema='kv260.ui.pipeline.v1', status='passed', input_sha256=digest,
            input=str(ct), mode='external-import', backend='external_producer_masks', fresh_inference=False,
            stages=[dict(stage='external_import', wall_seconds=report['import_seconds'])],
            total_wall_seconds=report['import_seconds'], new_reconstruction_or_navigation=False))
        write(temporary/'external_import.json', dict(schema=SCHEMA, status='completed', input_sha256=digest,
            segmentation_report_sha256=sha(temporary/'segmentation/report.json'),
            pipeline_sha256=sha(temporary/'pipeline.json'),
            input_manifest_sha256=bindings[str(manifest)], source_spec=spec,
            adapter_sha256=sha(Path(__file__)), implicit_resampling=False, clinical_ground_truth_validated=False))
        unchanged(bindings)
        temporary.rename(output)
        return report
    except BaseException:
        # Only our freshly-created, resolved temporary path is removable.
        if temporary.parent == output.parent and temporary.name.endswith('.import'):
            shutil.rmtree(temporary)
        raise


def validate_bundle(ct, folder):
    """Validate a saved bundle without depending on original external files."""
    ct, folder = Path(ct).resolve(), Path(folder).resolve()
    manifest = read(folder/'external_import.json'); report_path = folder/'segmentation/report.json'
    if (manifest.get('schema') != SCHEMA or manifest.get('status') != 'completed'
            or manifest.get('input_sha256') != sha(ct)
            or manifest.get('segmentation_report_sha256') != sha(report_path)
            or manifest.get('pipeline_sha256') != sha(folder/'pipeline.json')):
        raise ValueError('Imported bundle identity/report mismatch')
    report = read(report_path); _, g = header(ct)
    if report.get('input_sha256') != manifest['input_sha256'] or not same_geometry(report['geometry'], g):
        raise ValueError('Imported bundle CT/geometry mismatch')
    expected_masks = {f'segmentation/{n}_mask.nii.gz' for n in CLASSES}
    if not expected_masks.issubset(report.get('files', {})):
        raise ValueError('Imported bundle missing required masks')
    for name, digest in report['files'].items():
        path = inside(folder, name)
        if sha(path) != digest:
            raise ValueError('Imported image changed: '+name)
        _, image_g = header(path)
        if not same_geometry(g, image_g):
            raise ValueError('Imported image geometry changed: '+name)
    if set(report.get('images', {})) != set(CLASSES):
        raise ValueError('Imported image catalogue changed')
    for name, item in report['images'].items():
        probability = item.get('probability')
        if probability and (probability['file'] != f'{name}_probability.nrrd'
                or f'segmentation/{probability["file"]}' not in report['files']):
            raise ValueError('Invalid probability artifact path')
    return report


def load_probability(ct, folder, name='airway'):
    """Supply a preserved probability image to the independent surface producer."""
    if name not in CLASSES:
        raise ValueError('Unknown structure')
    folder = Path(folder).resolve(); report = validate_bundle(ct, folder)
    if 'probability' not in report['images'][name]:
        raise ValueError('No imported probability for '+name)
    path = folder/'segmentation'/report['images'][name]['probability']['file']
    image = sitk.ReadImage(str(path)); values = sitk.GetArrayViewFromImage(image)
    if not np.isfinite(values).all() or values.min() < 0 or values.max() > 1:
        raise ValueError('Invalid saved probability values')
    bindings = {str(Path(ct).resolve()):sha(ct), str(folder/'external_import.json'):sha(folder/'external_import.json'),
        str(folder/'segmentation/report.json'):sha(folder/'segmentation/report.json'), str(path):sha(path)}
    return image, dict(input_sha256=sha(ct), scalar_source='external_probability',
        model_sha256=report['provenance'].get('model_sha256'), producer=report['provenance']['origin'],
        inputs_sha256=bindings, probability_mask_gating_applied=False, accepted_mask_replaced=False,
        clinical_accuracy_validated=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ct', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = import_bundle(args.ct, args.manifest, args.output)
    print(json.dumps(dict(status=report['status'], output=str(args.output.resolve()),
        seconds=report['import_seconds'], foreground_voxels={k:v['foreground_voxels'] for k,v in report['images'].items()})))


if __name__ == '__main__':
    main()
