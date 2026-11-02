import unittest
from dataclasses import replace
import numpy as np
import SimpleITK as sitk
from .field import Quality
from .native_support import build_native_support
from .native_support_local import build_native_local


class ExactNativeLocal(unittest.TestCase):
    def test_rotated_thin_branches_Q5_Q6(self):
        a = np.zeros((14, 20, 22), np.uint8)
        a[2:12, 8:13, 8:13] = 1; a[7, 10, 12:20] = 1; a[4:6, 3:5, 3:5] = 1
        image = sitk.GetImageFromArray(a); image.SetSpacing([.8, .8, 2.5])
        image.SetOrigin([15, -23, 50]); image.SetDirection([0, -1, 0, 1, 0, 0, 0, 0, 1])
        for bits in (5, 6):
            with self.subTest(bits=bits):
                config = replace(Quality(), keep_largest_component=False, smoothing_sigma_mm=.2,
                    axial_smoothing_sigma_mm=.2, surface_smoothing_sigma_mm=.2,
                    surface_smoothing_strength=.35, quantization_mm=1/(1 << bits))
                old = build_native_support(image, config); new = build_native_local(image, config)
                for name in ('sdf_q_zyx', 'spacing_xyz', 'origin_xyz', 'direction', 'bounds_lo', 'bounds_hi'):
                    np.testing.assert_array_equal(getattr(old, name), getattr(new, name))
                for name in ('volume_offset_mm', 'probability_correction_voxels', 'target_mask_voxels',
                             'positive_voxels_before_quantization', 'positive_voxels_after_quantization'):
                    self.assertEqual(old.report[name], new.report[name])
                np.testing.assert_array_equal(sitk.GetArrayFromImage(image), a)

    def test_reject_probability(self):
        a = np.zeros((8, 8, 8), np.float32); a[3:5, 3:5, 3:5] = .9
        with self.assertRaisesRegex(ValueError, 'Native binary source required'):
            build_native_local(sitk.GetImageFromArray(a))


if __name__ == '__main__': unittest.main()
