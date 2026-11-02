"""Original binary/probability regressions plus independent legacy positive-label parity."""
from pathlib import Path
import importlib.util,json,os,sys,unittest
from unittest.mock import patch
import numpy as np
import SimpleITK as sitk

HERE=Path(__file__).resolve().parent
ROOT=Path(os.environ.get('KV260_TEST_SYSTEM_ROOT',str(HERE.parents[2])))
sys.path.insert(0,str(ROOT))
from modules.image_import.partial_r1 import test_full_contract as full
from modules.image_import.partial_r1 import test_partial_contract as partial
from modules.image_import.partial_r1 import importer as released

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

candidate=load('positive_label_candidate',HERE/'importer.py')
legacy=load('frozen_original_read_mask',HERE/'reference/read_mask.py')

def setup(self):
    full.ImportTests.setUp(self)
    for module in (full,partial):
        for name in ('import_bundle','validate_bundle','load_probability'):
            guard=patch.object(module,name,getattr(candidate,name));guard.start();self.addCleanup(guard.stop)

class FullCompatibility(full.ImportTests):
    setUp=setup

class PartialCompatibility(partial.PartialTests):
    setUp=setup

class PositiveLabels(unittest.TestCase):
    setUp=setup
    tearDown=full.ImportTests.tearDown
    run_spec=full.ImportTests.run_spec
    probability=full.ImportTests.probability

    def labels(self,values,selection='positive_mask'):
        path=self.inputs/'labels.nrrd'
        image=sitk.GetImageFromArray(values);image.CopyInformation(self.image)
        sitk.WriteImage(image,str(path),True)
        self.spec['images']={'airway':dict(selection=selection,mask=dict(file=path.name,sha256=candidate.sha(path)))}
        return path

    def actual(self,folder):
        return sitk.ReadImage(str(folder/'segmentation/airway_mask.nii.gz'))

    def test_all_supported_numeric_types_match_actual_original_read_mask(self):
        patterns={
            np.dtype('int16'):[-32768,-1,0,1,2,32767],
            np.dtype('uint16'):[0,1,2,255,65535],
            np.dtype('int64'):[-2**63,-2**53-1,-1,0,1,2**53+1,2**63-1],
            np.dtype('uint64'):[0,1,2**53+1,2**64-1],
            np.dtype('float32'):[-np.finfo(np.float32).max,-.2,-0.,0.,np.nextafter(np.float32(0),np.float32(1)),.2,1.,np.finfo(np.float32).max],
            np.dtype('float64'):[-np.finfo(np.float64).max,-.2,-0.,0.,np.nextafter(0.,1.),np.nextafter(0.,-1.),.2,1.,np.finfo(np.float64).max]}
        for dtype,pattern in patterns.items():
            with self.subTest(dtype=str(dtype)):
                values=np.resize(np.asarray(pattern,dtype=dtype),self.array.shape)
                source=self.labels(values);before=candidate.sha(source)
                original_image,expected=legacy.read_mask(source)
                folder,report=self.run_spec(output='typed_'+dtype.name)
                actual_image=self.actual(folder);actual=sitk.GetArrayFromImage(actual_image)
                np.testing.assert_array_equal(actual,expected)
                self.assertEqual(actual.dtype,np.uint8)
                self.assertEqual(candidate.sha(source),before)
                np.testing.assert_allclose(actual_image.TransformIndexToPhysicalPoint((3,4,5)),original_image.TransformIndexToPhysicalPoint((3,4,5)),atol=2e-6,rtol=0)
                row=report['images']['airway'];self.assertEqual(row['foreground_voxels'],int(expected.sum()))
                self.assertEqual(row['mask_conversion'],dict(rule='greater_than_zero',explicitly_selected=True,source_dtype=str(dtype),negative_values='background'))
                self.assertEqual(report['unavailable_structures'],['lung','nodule'])
                self.assertFalse(report['fresh_inference']);self.assertFalse(report['morphology_or_synthetic_bridges'])
                candidate.validate_bundle(self.ct,folder)
                # The existing downstream binary bundle validator accepts the canonical output.
                released.validate_bundle(self.ct,folder)

    def test_default_binary_selection_still_rejects_label_two(self):
        self.labels(np.full(self.array.shape,2,np.uint16),selection='mask')
        with self.assertRaisesRegex(ValueError,'binary'):self.run_spec()
        self.assertFalse((self.folder/'bundle').exists())
        self.assertFalse(list(self.folder.glob('.*.import')))

    def test_empty_and_negative_labels_do_not_invent_foreground(self):
        for i,value in enumerate((0,-1,-32768)):
            self.labels(np.full(self.array.shape,value,np.int16))
            folder,report=self.run_spec(output='empty_'+str(i))
            self.assertEqual(report['images']['airway']['foreground_voxels'],0)
            self.assertFalse(np.any(sitk.GetArrayFromImage(self.actual(folder))))

    def test_nonfinite_positive_label_input_is_rejected_atomically(self):
        for i,value in enumerate((np.nan,np.inf,-np.inf)):
            values=np.zeros(self.array.shape,np.float64);values[1,2,3]=value;self.labels(values)
            with self.assertRaisesRegex(ValueError,'nonfinite'):self.run_spec(output='nonfinite_'+str(i))
            self.assertFalse((self.folder/('nonfinite_'+str(i))).exists())
            self.assertFalse(list(self.folder.glob('.*.import')))

    def test_positive_selection_does_not_override_provided_probability(self):
        labels=np.zeros(self.array.shape,np.uint16);labels[2:5,3:6,3:6]=255
        self.labels(labels);probability=np.full(self.array.shape,.75,np.float64)
        self.probability(probability,threshold=.5)
        folder,report=self.run_spec()
        np.testing.assert_array_equal(sitk.GetArrayFromImage(self.actual(folder)),labels>0)
        saved,_=candidate.load_probability(self.ct,folder)
        np.testing.assert_array_equal(sitk.GetArrayFromImage(saved),probability)
        self.assertEqual(report['images']['airway']['selection'],'positive_mask')

    def test_conversion_metadata_tampering_is_refused(self):
        self.labels(np.ones(self.array.shape,np.uint16));folder,_=self.run_spec()
        report_path=folder/'segmentation/report.json';report=candidate.read(report_path)
        report['images']['airway']['mask_conversion']['rule']='nonzero'
        candidate.write(report_path,report)
        manifest_path=folder/'external_import.json';manifest=candidate.read(manifest_path)
        manifest['segmentation_report_sha256']=candidate.sha(report_path);candidate.write(manifest_path,manifest)
        with self.assertRaisesRegex(ValueError,'conversion declaration'):candidate.validate_bundle(self.ct,folder)

    def test_positive_selection_without_mask_is_refused_before_output(self):
        self.spec['images']={'airway':dict(selection='positive_mask')}
        with self.assertRaisesRegex(ValueError,'Invalid image selection'):self.run_spec()
        self.assertFalse((self.folder/'bundle').exists())

if __name__=='__main__':unittest.main()
