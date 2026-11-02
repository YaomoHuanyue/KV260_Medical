"""Quality contracts, zero-edge preservation, and ordinary cache case binding."""
from pathlib import Path
import json,tempfile,unittest
import numpy as np
import SimpleITK as sitk
from modules.surface_route.quality_action_r16 import configuration,renderer_field,context,ROOT
from modules.surface_route.quality_validation_r16 import validate_base_assets

class QualityContracts(unittest.TestCase):
    def test_tiers_preserve_sampling_but_change_quantization_and_smoothing(self):
        a,b=configuration('high'),configuration('ultra')
        self.assertEqual(a.isotropic_spacing_mm,b.isotropic_spacing_mm)
        self.assertEqual((a.quantization_mm,b.quantization_mm),(1/32,1/64))
        self.assertGreater(b.surface_smoothing_strength,a.surface_smoothing_strength)
        with self.assertRaises(ValueError):configuration('preview')

    def test_far_field_saturation_keeps_sign_and_every_used_edge_value(self):
        q=np.full((9,9,9),-1000,dtype='<i2');q[2:7,2:7,2:7]=-40;q[3:6,3:6,3:6]=20
        scalar,binary,offset,proof=renderer_field(q,5)
        np.testing.assert_array_equal(scalar>0,q>0)
        np.testing.assert_array_equal(binary,(q>0)[2:7,2:7,2:7])
        np.testing.assert_array_equal(offset,[2,2,2])
        self.assertTrue(proof['far_negative_saturation_preserves_all_crossing_edges'])
        self.assertEqual(int(scalar.min()),-128)

    def test_crossing_beyond_supported_band_is_refused_not_clamped(self):
        q=np.full((5,5,5),-1000,dtype='<i2');q[2,2,2]=1
        with self.assertRaisesRegex(ValueError,'zero-crossing'):renderer_field(q,5)

    def test_empty_bad_dtype_and_bad_bits_refused(self):
        for q,bits in [(np.zeros((4,4,4),'<i2'),5),(np.ones((4,4,4),'<f4'),5),(np.ones((4,4,4),'<i2'),7)]:
            with self.assertRaises(ValueError):renderer_field(q,bits)

class CaseCacheBinding(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'ui/cache',prefix='.quality-unit-')
        self.root=Path(self.tmp.name);self.result=self.root/'result';(self.result/'segmentation').mkdir(parents=True)
        a=np.arange(9*8*7,dtype=np.int16).reshape(9,8,7)
        self.image=sitk.GetImageFromArray(a);self.image.SetSpacing((.7,.9,1.2));self.image.SetOrigin((2.,-3.,4.))
        self.ct=self.root/'CT.nrrd';sitk.WriteImage(self.image,str(self.ct))
        a.astype('<f4').tofile(self.root/'ct.f32')
        self.packed=np.zeros(a.shape,np.uint8)
        for bit,name in ((1,'lung'),(2,'airway'),(4,'nodule')):
            m=np.zeros(a.shape,np.uint8);m[bit:bit+2,2:5,2:5]=1;self.packed|=m*bit
            im=sitk.GetImageFromArray(m);im.CopyInformation(self.image);sitk.WriteImage(im,str(self.result/f'segmentation/{name}_mask.nii.gz'))
        self.packed.tofile(self.root/'masks.u8')
        self.base=dict(volume='ct.f32',masks='masks.u8')
    def tearDown(self):self.tmp.cleanup()
    def verify(self):validate_base_assets(self.root/'scene.json',self.base,self.ct,self.result,self.root)
    def test_changed_case_path_same_shape_is_valid_when_contents_match(self):self.verify()
    def test_same_size_wrong_CT_cache_is_refused(self):
        values=np.fromfile(self.root/'ct.f32','<f4');values[100]+=1;values.tofile(self.root/'ct.f32')
        with self.assertRaisesRegex(ValueError,'CT contents'):self.verify()
    def test_same_size_wrong_mask_cache_is_refused(self):
        self.packed[3,3,3]^=2;self.packed.tofile(self.root/'masks.u8')
        with self.assertRaisesRegex(ValueError,'source mask'):self.verify()
    def test_mask_geometry_mismatch_is_refused(self):
        path=self.result/'segmentation/airway_mask.nii.gz';m=sitk.ReadImage(str(path));m.SetOrigin((3.,-3.,4.));sitk.WriteImage(m,str(path))
        with self.assertRaisesRegex(ValueError,'geometry'):self.verify()

if __name__=='__main__':unittest.main(verbosity=2)
