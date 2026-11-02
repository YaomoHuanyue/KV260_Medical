"""Meaningful geometry/identity/value/transaction tests for external inputs."""
from pathlib import Path
import copy
import json
import tempfile
import unittest
import numpy as np
import SimpleITK as sitk
from .importer import import_bundle, validate_bundle, load_probability, sha, SCHEMA


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name); self.inputs = self.folder/'inputs'; self.inputs.mkdir()
        self.ct = self.folder/'ct.nrrd'
        self.array = np.zeros((7, 8, 9), np.int16)
        self.image = sitk.GetImageFromArray(self.array)
        self.image.SetSpacing((.7, .9, 2.5)); self.image.SetOrigin((110., -70., 35.))
        self.image.SetDirection((0., -1., 0., 1., 0., 0., 0., 0., 1.))
        sitk.WriteImage(self.image, str(self.ct), True)
        self.mask = np.zeros(self.array.shape, np.uint8); self.mask[2:5, 3:6, 3:6] = 1
        self.spec = dict(schema=SCHEMA, ct_sha256=sha(self.ct),
            provenance=dict(origin='synthetic-test-only'), images={})
        for name in ('lung', 'airway', 'nodule'):
            m = self.inputs/(name+'.nii.gz'); im=sitk.GetImageFromArray(self.mask);im.CopyInformation(self.image)
            sitk.WriteImage(im, str(m), True)
            self.spec['images'][name] = dict(selection='mask', mask=dict(file=m.name, sha256=sha(m)))
        self.manifest=self.inputs/'images.json'

    def tearDown(self):
        self.temp.cleanup()

    def run_spec(self, spec=None, output='bundle'):
        self.manifest.write_text(json.dumps(spec or self.spec))
        destination = self.folder/output
        return destination, import_bundle(self.ct, self.manifest, destination)

    def probability(self, values, threshold=.5):
        path=self.inputs/'airway_probability.nrrd';im=sitk.GetImageFromArray(values);im.CopyInformation(self.image)
        sitk.WriteImage(im, str(path), True)
        self.spec['images']['airway']['probability']=dict(file=path.name,sha256=sha(path),threshold=threshold)

    def test_binary_roundtrip_rotated_anisotropic_and_independent_bundle(self):
        folder, report=self.run_spec()
        self.assertFalse(report['fresh_inference']); self.assertFalse(report['implicit_resampling'])
        self.assertEqual(validate_bundle(self.ct, folder)['input_sha256'], sha(self.ct))
        for name in self.spec['images']:
            im=sitk.ReadImage(str(folder/'segmentation'/f'{name}_mask.nii.gz'))
            np.testing.assert_array_equal(sitk.GetArrayFromImage(im), self.mask)
            np.testing.assert_allclose(im.TransformIndexToPhysicalPoint((3,4,5)),
                self.image.TransformIndexToPhysicalPoint((3,4,5)), rtol=0, atol=2e-6)
        # Validation does not rely on the external source remaining available.
        self.manifest.unlink()
        validate_bundle(self.ct, folder)
        self.manifest.write_text(json.dumps(self.spec))
        with self.assertRaises(FileExistsError):
            import_bundle(self.ct, self.manifest, folder)

    def test_probability_selection_preserves_float64_and_exact_threshold(self):
        values=np.full(self.array.shape, .1, np.float64)
        values[1,2,3]=np.nextafter(.5, 0.); values[1,2,4]=.5; values[1,2,5]=np.nextafter(.5,1.)
        self.probability(values);self.spec['images']['airway']['selection']='probability_threshold'
        folder, _=self.run_spec()
        probability, identity=load_probability(self.ct, folder)
        np.testing.assert_array_equal(sitk.GetArrayFromImage(probability),values)
        actual=sitk.GetArrayFromImage(sitk.ReadImage(str(folder/'segmentation/airway_mask.nii.gz')))
        np.testing.assert_array_equal(actual,values>=.5)
        self.assertEqual(actual[1,2,3:6].tolist(),[0,1,1])
        np.testing.assert_array_equal(sitk.GetArrayFromImage(sitk.ReadImage(str(folder/'segmentation/airway_mask_provided.nrrd'))),self.mask)
        self.assertIsNone(identity['model_sha256']);self.assertFalse(identity['clinical_accuracy_validated'])

    def test_provided_mask_does_not_silently_threshold_probability(self):
        values=np.ones(self.array.shape,np.float32);self.probability(values)
        folder,_=self.run_spec()
        actual=sitk.GetArrayFromImage(sitk.ReadImage(str(folder/'segmentation/airway_mask.nii.gz')))
        np.testing.assert_array_equal(actual,self.mask)
        np.testing.assert_array_equal(sitk.GetArrayFromImage(load_probability(self.ct,folder)[0]),values)

    def test_wrong_CT_SHA_file_SHA_and_geometry_are_rejected(self):
        cases=[];d=copy.deepcopy(self.spec);d['ct_sha256']='0'*64;cases.append(d)
        d=copy.deepcopy(self.spec);d['images']['airway']['mask']['sha256']='0'*64;cases.append(d)
        for i,d in enumerate(cases):
            with self.assertRaises(ValueError):self.run_spec(d,'bad'+str(i))
        p=self.inputs/'airway.nii.gz';im=sitk.ReadImage(str(p));im.SetOrigin((111.,-70.,35.))
        sitk.WriteImage(im,str(p),True);self.spec['images']['airway']['mask']['sha256']=sha(p)
        with self.assertRaisesRegex(ValueError,'geometry'):self.run_spec(output='wrong_geometry')
        self.assertFalse((self.folder/'wrong_geometry').exists())

    def test_nonbinary_nonfinite_probability_range_and_missing_threshold(self):
        p=self.inputs/'nodule.nii.gz';bad=np.zeros(self.array.shape,np.uint8);bad[0,0,0]=2
        im=sitk.GetImageFromArray(bad);im.CopyInformation(self.image);sitk.WriteImage(im,str(p),True)
        self.spec['images']['nodule']['mask']['sha256']=sha(p)
        with self.assertRaisesRegex(ValueError,'binary'):self.run_spec(output='bad_binary')
        # A mid-import failure leaves no result and no temporary directory.
        self.assertFalse((self.folder/'bad_binary').exists())
        self.assertFalse(list(self.folder.glob('.*.import')))
        im=sitk.GetImageFromArray(self.mask);im.CopyInformation(self.image);sitk.WriteImage(im,str(p),True)
        self.spec['images']['nodule']['mask']['sha256']=sha(p)
        for number,bad_value in enumerate((float('nan'), -.1, 1.1)):
            values=np.zeros(self.array.shape,np.float32);values[0,0,0]=bad_value;self.probability(values)
            with self.assertRaises(ValueError):self.run_spec(output='bad_probability'+str(number))
        self.probability(np.zeros(self.array.shape,np.float32))
        del self.spec['images']['airway']['probability']['threshold']
        with self.assertRaisesRegex(ValueError,'threshold'):self.run_spec(output='missing_threshold')

    def test_path_escape_detached_images_and_saved_tamper_are_rejected(self):
        for file in ('../ct.nrrd','/ct.nrrd','C:/ct.nrrd','sub\\ct.nrrd'):
            d=copy.deepcopy(self.spec);d['images']['airway']['mask']['file']=file
            with self.assertRaises(ValueError):self.run_spec(d,'path_bad')
        folder,_=self.run_spec()
        p=folder/'segmentation/airway_mask.nii.gz';p.write_bytes(p.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):validate_bundle(self.ct,folder)
        p=self.inputs/'detached.nrrd'
        p.write_bytes(b'NRRD0005\ntype: uint8\ndimension: 3\nsizes: 9 8 7\nencoding: raw\ndata file: payload.raw\n\n')
        d=copy.deepcopy(self.spec);d['images']['airway']['mask']={'file':p.name,'sha256':sha(p)}
        with self.assertRaisesRegex(ValueError,'Detached'):self.run_spec(d,'detached_bad')


if __name__ == '__main__':
    unittest.main()
