"""Independent exact-offset producer; immutable original field.py stays the oracle.

The only finishing algorithm change is replacement of fourteen volume scans
by one exact band sort and fourteen binary queries. Geometry, correction,
Gaussian blend, final offset and quantization retain the original rules.
"""
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
import hashlib
import numpy as np
from scipy import ndimage as ndi
from .field import Field,Quality,geometry,prepare,signed_maurer,signed_from_distance
from .volume_offset import preserving_offset

BASELINE_SHA256 = 'e00ac0f76e60ce27cb2ed564ab7ef571ddb1fb3f10b5a896d79aff64c9e48414'


def verify_baseline():
    if hashlib.sha256(Path(__file__).with_name('field.py').read_bytes()).hexdigest()!=BASELINE_SHA256:
        raise RuntimeError('Original field helpers changed; validate a new producer before use')


def finish_fast(prepared, sdf, distance_stats):
    start = perf_counter()
    quality = prepared.quality
    if (sdf.shape != prepared.mask.shape or sdf.dtype != np.float32 or
            not np.isfinite(sdf).all()):
        raise ValueError('Invalid signed physical distance')
    sdf = np.clip(sdf, -quality.max_distance_mm, quality.max_distance_mm).astype(np.float32, copy=False)
    probability = prepared.probability
    spacing = np.asarray(prepared.image.GetSpacing())
    gz, gy, gx = np.gradient(probability, *spacing[::-1], edge_order=1)
    magnitude = np.sqrt(gx * gx + gy * gy + gz * gz)
    local_distance = (probability - quality.threshold) / np.maximum(magnitude, 1e-4)
    band = (np.abs(sdf) <= 2 * quality.isotropic_spacing_mm) & (magnitude >= 0.02)
    sdf[band] = np.clip(local_distance[band], -2 * quality.isotropic_spacing_mm, 2 * quality.isotropic_spacing_mm)
    band_voxels = int(band.sum())
    del gx, gy, gz, magnitude, local_distance, band
    timings = dict(prepared.timings)
    timings['signed_distance'] = distance_stats['total_seconds']
    timings['probability_zero_crossing_correction'] = perf_counter() - start
    target = int(prepared.mask.sum())
    offset = 0.0
    offset_profile = None
    start = perf_counter()
    if quality.surface_smoothing_sigma_mm > 0 and quality.surface_smoothing_strength > 0:
        sigma = quality.surface_smoothing_sigma_mm / spacing[::-1]
        regularized = ndi.gaussian_filter(sdf, sigma=tuple(sigma), mode='nearest')
        strength = quality.surface_smoothing_strength
        regularized = (1 - strength) * sdf + strength * regularized
        offset, offset_profile = preserving_offset(regularized, target,
                                                   quality.surface_smoothing_sigma_mm)
        sdf = (regularized - offset).astype(np.float32, copy=False)
    timings['SDF_gaussian_blend_and_volume_offset'] = perf_counter() - start
    volume_before_quantization = int(np.count_nonzero(sdf > 0))
    start = perf_counter()
    foreground = np.argwhere(prepared.mask)
    low, high = foreground.min(0)[::-1].astype(float), foreground.max(0)[::-1].astype(float)
    direction = np.asarray(prepared.image.GetDirection()).reshape(3, 3)
    origin = np.asarray(prepared.image.GetOrigin())
    corners = np.asarray([origin + direction @ (np.array([x, y, z]) * spacing)
        for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])])
    q = np.clip(np.rint(sdf / quality.quantization_mm), -32767, 32767).astype('<i2')
    timings['physical_bounds_and_INT16_quantization'] = perf_counter() - start
    stats = dict(schema='kv260.surface_quality.field.v1', status='prepared_not_promoted',
        configuration=asdict(quality), source_geometry=prepared.source_geometry,
        crop_lo_zyx=prepared.crop_lo_zyx, output_geometry=geometry(prepared.image),
        shape_zyx=list(q.shape), distance=distance_stats, phases_seconds=timings,
        algorithm_seconds=sum(timings.values()), probability_correction_voxels=band_voxels,
        target_mask_voxels=target, positive_voxels_before_quantization=volume_before_quantization,
        positive_voxels_after_quantization=int(np.count_nonzero(q > 0)),
        volume_offset_mm=offset, volume_error_voxels=volume_before_quantization-target,
        volume_preservation_scope='14-step offset restores global thresholded voxel count before INT16 quantization; not a topology or local-radius guarantee',
        accepted_masks_meshes_navigation_replaced=False, PS_Marching_Cubes_used=False)
    stats['offset_implementation'] = 'one_band_sort_same_14_float32_decisions'
    stats['offset_profile'] = offset_profile
    stats['original_reference_field_sha256'] = BASELINE_SHA256
    return Field(q, spacing, origin, direction, corners.min(0), corners.max(0),
                 quality.quantization_mm, quality.gradient_sigma_mm, stats)


def build_fast(image, quality=Quality(), distance_backend=None):
    verify_baseline()
    prepared = prepare(image, quality)
    sdf, stats = signed_maurer(prepared) if distance_backend is None else signed_from_distance(prepared, distance_backend)
    return finish_fast(prepared, sdf, stats)
