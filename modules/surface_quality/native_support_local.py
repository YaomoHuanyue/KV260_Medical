"""Native occupied-cell surface with the validated exact bounded finisher.

The immutable native_support.py remains the numeric oracle. Grid construction,
nearest sampling and physical Gaussian rules are identical; only finishing work
is reduced. This is a binary surface rule, not network probability or new anatomy.
"""
from dataclasses import replace
from time import perf_counter
import numpy as np
import SimpleITK as sitk
from .field import Quality, Prepared, prepare, signed_maurer, signed_from_distance
from .fast_field_local import finish_local, verify_baseline


def build_native_local(image, quality=None, distance_backend=None):
    verify_baseline()
    quality = quality or replace(Quality(), keep_largest_component=False,
        smoothing_sigma_mm=.2, axial_smoothing_sigma_mm=.2,
        surface_smoothing_sigma_mm=.2, surface_smoothing_strength=.35)
    quality.validate()
    if quality.keep_largest_component or quality.axial_smoothing_sigma_mm != quality.smoothing_sigma_mm:
        raise ValueError('Native support requires all components and equal physical Gaussian axes')
    values = sitk.GetArrayViewFromImage(image)
    if np.any((values != 0) & (values != 1)):
        raise ValueError('Native binary source required; probability is a separate algorithm')
    start = perf_counter()
    grid = prepare(image, replace(quality, keep_largest_component=False,
        smoothing_sigma_mm=0, axial_smoothing_sigma_mm=0))
    nearest = sitk.Resample(image, grid.image, sitk.Transform(), sitk.sitkNearestNeighbor, 0, sitk.sitkFloat32)
    probability = sitk.GetArrayFromImage(nearest)
    if quality.smoothing_sigma_mm:
        probability = sitk.GetArrayFromImage(sitk.SmoothingRecursiveGaussian(nearest, quality.smoothing_sigma_mm))
    mask = probability >= quality.threshold
    if not mask.any():
        raise ValueError('Empty resampled native support')
    prepared = Prepared(probability, mask, nearest, grid.source_geometry, grid.crop_lo_zyx, quality,
        dict(native_grid_validation_nearest_resample_and_physical_gaussian=perf_counter()-start))
    del grid
    if distance_backend is None:
        sdf, stats = signed_maurer(prepared)
    else:
        sdf, stats = signed_from_distance(prepared, distance_backend)
    field = finish_local(prepared, sdf, stats)
    field.report.update(source_rule='native_binary_occupied_cells_nearest_resample_then_physical_gaussian',
        original_linear_probability_equivalence=False, fabricated_bridges=False, centreline_painting=False,
        producer='exact_local_gradient_and_same_14_float32_volume_decisions')
    return field
