from pathlib import Path
import hashlib
import tempfile
import unittest
import numpy as np
import SimpleITK as sitk
from .catalogue import catalogue
from .export import export_catalogue,sha,ROOT
from .oracle import component_report

SCRATCH=ROOT/'modules/lesion_catalogue/build/test_scratch'


def fixture():
    a=np.zeros((18,21,23),np.uint8)
    a[2:6,3:7,4:8]=1
    a[9:11,12:14,15:17]=1
    a[14,3,2]=a[15,4,3]=1  # 26-connectivity must merge these.
    a[2,15,3]=a[2,15,4]=1  # Equal-size components test stable tie ordering.
    im=sitk.GetImageFromArray(a);im.SetSpacing((.7,1.1,2.5))
    im.SetOrigin((-160.1,20.25,12.3));im.SetDirection((0.,-1.,0.,1.,0.,0.,0.,0.,1.))
    return a,im


class CatalogueTests(unittest.TestCase):
    def compare(self,a,im,minimum):
        expected,legacy=component_report(a,im,minimum)
        report,actual=catalogue(a,im,minimum,make_labels=True)
        np.testing.assert_array_equal(actual,expected)
        self.assertEqual(actual.dtype,np.dtype('uint16'))
        self.assertEqual(len(report['rows']),len(legacy))
        for row,old in zip(report['rows'],legacy):
            self.assertEqual(row['id'],old['id'])
            self.assertEqual(row['bbox_xyz_size'],old['bbox_xyz_size'])
            self.assertAlmostEqual(row['volume_mm3'],old['volume_mm3'],places=10)
            self.assertAlmostEqual(row['equivalent_sphere_diameter_mm'],old['equivalent_sphere_diameter_mm'],places=10)
            np.testing.assert_allclose(row['centroid_xyz_mm'],old['centroid_xyz_mm'],rtol=0,atol=1e-10)
        return report,actual

    def test_anisotropic_rotated_grid_and_26_connectivity(self):
        a,im=fixture();before=a.copy()
        report,_=self.compare(a,im,0)
        self.assertEqual(report['raw_component_count'],4)
        np.testing.assert_array_equal(a,before)
        self.assertEqual([r['index'] for r in report['rows']],[0,1,2,3])

    def test_inclusive_filter_and_preserved_original_rank(self):
        a,im=fixture();_,all_rows=component_report(a,im,0)
        for minimum in (14.,all_rows[1]['volume_mm3'],all_rows[0]['volume_mm3']+1):
            self.compare(a,im,minimum)
        report,_=catalogue(a,im,14.,make_labels=False)
        self.assertEqual(report['rows'][0]['index'],0)
        self.assertEqual(report['retained_component_count'],2)

    def test_empty_provided_mask_is_not_missing_structure(self):
        a,im=fixture();a.fill(0)
        report,labels=self.compare(a,im,14)
        self.assertEqual(report['state'],'provided_empty_mask')
        self.assertFalse(np.any(labels))

    def test_invalid_masks_geometry_and_thresholds(self):
        a,im=fixture()
        for value in (-1.,float('inf'),float('nan')):
            with self.assertRaises(ValueError):catalogue(a,im,value)
        for bad in (a[:-1],a.astype(float),a.astype(str)):
            with self.assertRaises(ValueError):catalogue(bad,im)
        bad=a.copy();bad[0,0,0]=2
        with self.assertRaises(ValueError):catalogue(bad,im)

    def test_original_grid_labeled_NIfTI_NRRD_and_binary_roundtrip(self):
        SCRATCH.mkdir(parents=True,exist_ok=True);assert SCRATCH.resolve().is_relative_to(ROOT)
        with tempfile.TemporaryDirectory(dir=SCRATCH) as name:
            folder=Path(name).resolve();assert folder.is_relative_to(SCRATCH.resolve())
            a,im=fixture();source=folder/'mask.nii.gz';sitk.WriteImage(im,str(source),True)
            before=sha(source);result=export_catalogue(source,folder/'export',14,im)
            _,expected=catalogue(a,im,14,True)
            for file in ('lesion_labels.nii.gz','lesion_labels.nrrd'):
                loaded=sitk.ReadImage(str(folder/'export'/file))
                np.testing.assert_array_equal(sitk.GetArrayFromImage(loaded),expected)
                self.assertEqual(loaded.GetSize(),im.GetSize())
                self.assertEqual(loaded.GetPixelID(),sitk.sitkUInt16)
                for x,y in ((loaded.GetSpacing(),im.GetSpacing()),(loaded.GetOrigin(),im.GetOrigin()),(loaded.GetDirection(),im.GetDirection())):
                    np.testing.assert_allclose(x,y,rtol=0,atol=1e-5)
            binary=sitk.GetArrayFromImage(sitk.ReadImage(str(folder/'export/lesion_filtered_mask.nii.gz')))
            np.testing.assert_array_equal(binary,expected>0)
            self.assertEqual(sha(source),before)
            self.assertFalse(result['PL_used_for_catalogue'])
            with self.assertRaises(FileExistsError):export_catalogue(source,folder/'export',14,im)

    def test_CT_geometry_mismatch_rejected_before_destination_write(self):
        SCRATCH.mkdir(parents=True,exist_ok=True);assert SCRATCH.resolve().is_relative_to(ROOT)
        with tempfile.TemporaryDirectory(dir=SCRATCH) as name:
            folder=Path(name).resolve();assert folder.is_relative_to(SCRATCH.resolve())
            a,im=fixture();source=folder/'mask.nii.gz';sitk.WriteImage(im,str(source),True)
            reference=sitk.Image(im);reference.SetOrigin((0.,0.,0.))
            with self.assertRaises(ValueError):export_catalogue(source,folder/'export',14,reference)
            self.assertFalse((folder/'export').exists())
