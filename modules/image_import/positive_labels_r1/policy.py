"""Explicit product policy for airway probabilities; preserve the original probability image."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import time
import uuid
import numpy as np
import SimpleITK as sitk
from modules.image_import.positive_labels_r1 import importer as original
from modules.segmentation.airway.ct_geometry import largest_airway_component

ORIGINAL_IMPORT = original.import_bundle
POLICY = 'probability_threshold_then_largest_26_connected_airway'


def array_sha(value):
    return hashlib.sha256(memoryview(np.ascontiguousarray(value)).cast('B')).hexdigest()


def import_bundle(ct, manifest, output):
    """Use the full-inference airway component policy for explicitly thresholded probabilities.

    Producer masks and probabilities for other classes retain their original semantics.
    Only fresh owned output is transformed, before it becomes a selectable result.
    """
    ct, manifest, output = (Path(p).resolve() for p in (ct, manifest, output))
    spec = original.read(manifest)
    if not isinstance(spec, dict):
        raise ValueError('Manifest must be a JSON object declaring known structures')
    declared = spec.get('images')
    airway = declared.get('airway', {}) if isinstance(declared, dict) else {}
    if not isinstance(airway, dict) or airway.get('selection') != 'probability_threshold':
        return ORIGINAL_IMPORT(ct, manifest, output)
    if output.exists():
        raise FileExistsError('Choose a new output folder; imported results are immutable')
    if output == manifest.parent or manifest.parent in output.parents:
        raise ValueError('Output must be outside the input manifest directory')
    started = time.perf_counter()
    owned = output.with_name('.' + output.name + '.airway_policy_' + uuid.uuid4().hex)
    assert owned.parent == output.parent and not owned.exists()
    try:
        report = ORIGINAL_IMPORT(ct, manifest, owned)
        path = owned / 'segmentation/airway_mask.nii.gz'
        image = sitk.ReadImage(str(path))
        raw = sitk.GetArrayFromImage(image)
        tick = time.perf_counter()
        filtered, statistics = largest_airway_component(raw)
        seconds = time.perf_counter() - tick
        if filtered.shape != raw.shape or np.any(filtered.astype(bool) & ~raw.astype(bool)):
            raise ValueError('Airway component filtering must not add or resample voxels')
        probability = owned / 'segmentation/airway_probability.nrrd'
        probability_hash = original.sha(probability)
        policy = dict(policy=POLICY, computation='PS_existing_full_inference_component_policy',
                      connectivity=26, input_threshold=float(airway['probability']['threshold']),
                      raw_threshold_voxels=int(np.count_nonzero(raw)),
                      raw_threshold_uint8_array_SHA256=array_sha(raw),
                      kept_voxels=int(np.count_nonzero(filtered)),
                      removed_voxels=int(np.count_nonzero(raw)) - int(np.count_nonzero(filtered)),
                      input_components=statistics.get('components', 0),
                      filtered_uint8_array_SHA256=array_sha(filtered),
                      probability_file_SHA256=probability_hash,
                      raw_probability_bits_preserved=True, no_added_voxels_or_bridges=True,
                      geometry_unchanged=True, seconds=seconds,
                      independent_clinical_accuracy_not_inferred=True)
        cleaned = sitk.GetImageFromArray(filtered)
        cleaned.CopyInformation(image)
        temporary = path.with_name('.airway_filtered_' + uuid.uuid4().hex + '.nii.gz')
        sitk.WriteImage(cleaned, str(temporary), True)
        os.replace(temporary, path)
        row = report['images']['airway']
        row.update(foreground_voxels=policy['kept_voxels'], postprocessing=policy)
        report['files']['segmentation/airway_mask.nii.gz'] = original.sha(path)
        report.update(backend='PS_external_validation_and_airway_component_policy',
                      postprocessing={'airway': policy}, import_seconds=time.perf_counter() - started)
        original.write(owned / 'segmentation/report.json', report)
        pipeline = original.read(owned / 'pipeline.json')
        pipeline.update(total_wall_seconds=report['import_seconds'], postprocessing={'airway': policy})
        pipeline['stages'][0]['wall_seconds'] = report['import_seconds']
        original.write(owned / 'pipeline.json', pipeline)
        external = original.read(owned / 'external_import.json')
        external.update(segmentation_report_sha256=original.sha(owned / 'segmentation/report.json'),
                        pipeline_sha256=original.sha(owned / 'pipeline.json'),
                        adapter_sha256=original.sha(Path(__file__)),
                        original_importer_SHA256=original.sha(Path(original.__file__)),
                        postprocessing={'airway': policy})
        original.write(owned / 'external_import.json', external)
        original.unchanged(report['input_bindings'])
        assert original.sha(probability) == probability_hash
        original.validate_bundle(ct, owned)
        assert not output.exists()
        owned.rename(output)
        return report
    except BaseException:
        if owned.is_dir() and owned.parent == output.parent and '.airway_policy_' in owned.name:
            shutil.rmtree(owned)
        raise
