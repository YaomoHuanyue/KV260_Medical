"""Partial-image semantics, immutable bundles and geometry/identity boundaries."""
import copy
import json
from pathlib import Path
import unittest
import numpy as np
import SimpleITK as sitk
from . import test_full_contract as fixtures
from .importer import import_bundle, validate_bundle, load_probability, sha


class PartialTests(unittest.TestCase):
    setUp = fixtures.ImportTests.setUp
    tearDown = fixtures.ImportTests.tearDown
    run_spec = fixtures.ImportTests.run_spec
    probability = fixtures.ImportTests.probability

    def select(self, names):
        self.spec['images'] = {n: self.spec['images'][n] for n in names}

    def test_each_single_structure_preserves_voxels_and_marks_others_unavailable(self):
        original = copy.deepcopy(self.spec)
        for name in ('lung', 'airway', 'nodule'):
            self.spec = copy.deepcopy(original)
            self.select((name,))
            destination, report = self.run_spec(output='single_' + name)
            self.assertEqual(report['declared_structures'], [name])
            self.assertEqual(set(report['files']), {'segmentation/' + name + '_mask.nii.gz'})
            actual = sitk.ReadImage(str(destination / 'segmentation' / (name + '_mask.nii.gz')))
            np.testing.assert_array_equal(sitk.GetArrayFromImage(actual), self.mask)
            np.testing.assert_allclose(actual.TransformIndexToPhysicalPoint((3, 4, 5)),
                                       self.image.TransformIndexToPhysicalPoint((3, 4, 5)),
                                       atol=2e-6, rtol=0)
            validate_bundle(self.ct, destination)
            for other in set(original['images']) - {name}:
                self.assertEqual(report['structure_availability'][other], 'not_provided')
                self.assertFalse((destination / 'segmentation' / (other + '_mask.nii.gz')).exists())

    def test_airway_candidate_pair_has_no_invented_lung_mask(self):
        self.select(('airway', 'nodule'))
        destination, report = self.run_spec()
        self.assertEqual(report['declared_structures'], ['airway', 'nodule'])
        self.assertEqual(report['unavailable_structures'], ['lung'])
        self.assertFalse((destination / 'segmentation/lung_mask.nii.gz').exists())
        self.assertFalse(report['fresh_inference'])
        self.assertFalse(report['clinical_accuracy_validated'])
        pipeline = json.loads((destination / 'pipeline.json').read_text(encoding='utf-8'))
        self.assertEqual(pipeline['available_structures'], ['airway', 'nodule'])
        validate_bundle(self.ct, destination)

    def test_probability_only_preserves_float64_threshold_edges_and_omissions(self):
        self.select(('airway',))
        values = np.full(self.array.shape, .1, np.float64)
        values[1, 2, 3:6] = [np.nextafter(.5, 0.), .5, np.nextafter(.5, 1.)]
        self.probability(values)
        self.spec['images']['airway']['selection'] = 'probability_threshold'
        del self.spec['images']['airway']['mask']
        destination, report = self.run_spec()
        probability, identity = load_probability(self.ct, destination)
        actual_probability = sitk.GetArrayFromImage(probability)
        self.assertEqual(actual_probability.dtype, np.float64)
        np.testing.assert_array_equal(actual_probability, values)
        actual = sitk.GetArrayFromImage(sitk.ReadImage(str(destination / 'segmentation/airway_mask.nii.gz')))
        np.testing.assert_array_equal(actual, values >= .5)
        self.assertEqual(actual[1, 2, 3:6].tolist(), [0, 1, 1])
        self.assertFalse((destination / 'segmentation/airway_mask_provided.nrrd').exists())
        self.assertEqual(report['unavailable_structures'], ['lung', 'nodule'])
        self.assertFalse(identity['clinical_accuracy_validated'])

    def test_missing_probability_structure_raises_clear_value_error(self):
        self.select(('lung',))
        destination, _ = self.run_spec()
        with self.assertRaisesRegex(ValueError, 'No imported probability for airway'):
            load_probability(self.ct, destination, 'airway')

    def test_empty_unknown_and_non_mapping_declarations_rejected_before_output(self):
        for number, images in enumerate(({}, {'unknown': {}}, [], None)):
            spec = copy.deepcopy(self.spec)
            spec['images'] = images
            with self.assertRaisesRegex(ValueError, 'known structures'):
                self.run_spec(spec, 'bad_' + str(number))
            self.assertFalse((self.folder / ('bad_' + str(number))).exists())

    def test_saved_catalogue_cannot_change_available_structure_identity(self):
        self.select(('airway',))
        destination, _ = self.run_spec()
        report_path = destination / 'segmentation/report.json'
        report = json.loads(report_path.read_text(encoding='utf-8'))
        report['declared_structures'] = ['lung', 'airway']
        report_path.write_text(json.dumps(report), encoding='utf-8')
        manifest_path = destination / 'external_import.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['segmentation_report_sha256'] = sha(report_path)
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'availability changed'):
            validate_bundle(self.ct, destination)

    def test_saved_bundle_independent_of_original_external_files(self):
        self.select(('nodule',))
        destination, _ = self.run_spec()
        self.manifest.unlink()
        (self.inputs / 'nodule.nii.gz').unlink()
        report = validate_bundle(self.ct, destination)
        self.assertEqual(report['declared_structures'], ['nodule'])


if __name__ == '__main__':
    unittest.main()
