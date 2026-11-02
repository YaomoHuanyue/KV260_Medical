"""Separate binary-support candidate; never substitute for network probability.

Nearest-neighbour resampling retains native occupied voxel cells before gentle
physical smoothing. This is an explicit different surface rule, not a claim of
extra anatomy or equivalence to the original linear probability algorithm.
"""
from dataclasses import replace
from time import perf_counter
import numpy as np
import SimpleITK as sitk
from .field import Quality,Prepared,prepare,finish,signed_maurer


def build_native_support(image,quality=None,distance_backend=None):
    quality=quality or replace(Quality(),keep_largest_component=False,
        smoothing_sigma_mm=.2,axial_smoothing_sigma_mm=.2,
        surface_smoothing_sigma_mm=.2,surface_smoothing_strength=.35)
    quality.validate()
    if quality.keep_largest_component or quality.axial_smoothing_sigma_mm!=quality.smoothing_sigma_mm:
        raise ValueError('Native support candidate requires all components and equal physical Gaussian axes')
    values=sitk.GetArrayViewFromImage(image)
    if np.any((values!=0)&(values!=1)):raise ValueError('Native binary source required; probability is a separate algorithm')
    start=perf_counter()
    # Reuse the validated crop/grid calculation; do not modify its original
    # implementation or accepted source-bound evidence.
    grid=prepare(image,replace(quality,keep_largest_component=False,
        smoothing_sigma_mm=0,axial_smoothing_sigma_mm=0))
    nearest=sitk.Resample(image,grid.image,sitk.Transform(),sitk.sitkNearestNeighbor,0,sitk.sitkFloat32)
    probability=sitk.GetArrayFromImage(nearest)
    if quality.smoothing_sigma_mm:
        probability=sitk.GetArrayFromImage(sitk.SmoothingRecursiveGaussian(nearest,quality.smoothing_sigma_mm))
    mask=probability>=quality.threshold
    if not mask.any():raise ValueError('Empty resampled native support')
    prepared=Prepared(probability,mask,nearest,grid.source_geometry,grid.crop_lo_zyx,quality,
        dict(native_grid_validation_nearest_resample_and_physical_gaussian=perf_counter()-start))
    del grid
    if distance_backend is None:sdf,stats=signed_maurer(prepared)
    else:
        from .field import signed_from_distance
        sdf,stats=signed_from_distance(prepared,distance_backend)
    field=finish(prepared,sdf,stats)
    field.report['source_rule']='native_binary_occupied_cells_nearest_resample_then_physical_gaussian'
    field.report['original_linear_probability_equivalence']=False
    field.report['fabricated_bridges']=False
    field.report['centreline_painting']=False
    return field
