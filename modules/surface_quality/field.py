"""The supplied isotropic surface rules, with explicit phases and geometry.

This produces a scalar field, not a mesh or a CPU renderer. Accepted masks,
meshes, routes and the currently deployed C6 packet are never modified.
"""
from dataclasses import asdict, dataclass
from time import perf_counter
import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi


@dataclass(frozen=True)
class Quality:
    margin_mm: float = 14.0
    max_distance_mm: float = 32.0
    isotropic_spacing_mm: float = 0.75
    threshold: float = 0.5
    smoothing_sigma_mm: float = 0.35
    quantization_mm: float = 1.0 / 32.0
    gradient_sigma_mm: float = 0.55
    keep_largest_component: bool = True
    surface_smoothing_sigma_mm: float = 0.35
    surface_smoothing_strength: float = 0.55
    axial_smoothing_sigma_mm: float = 0.80

    def validate(self):
        numbers = [v for v in asdict(self).values() if not isinstance(v, bool)]
        if not np.isfinite(numbers).all():
            raise ValueError('Nonfinite surface configuration')
        if (self.margin_mm < 0 or self.max_distance_mm <= 0 or
                self.isotropic_spacing_mm <= 0 or not 0 < self.threshold < 1 or
                self.quantization_mm <= 0 or min(self.smoothing_sigma_mm,
                self.gradient_sigma_mm, self.surface_smoothing_sigma_mm,
                self.axial_smoothing_sigma_mm) < 0 or
                not 0 <= self.surface_smoothing_strength <= 1 or
                not isinstance(self.keep_largest_component, bool)):
            raise ValueError('Invalid physical surface configuration')


@dataclass
class Prepared:
    probability: np.ndarray
    mask: np.ndarray
    image: sitk.Image
    source_geometry: dict
    crop_lo_zyx: list
    quality: Quality
    timings: dict


@dataclass
class Field:
    sdf_q_zyx: np.ndarray
    spacing_xyz: np.ndarray
    origin_xyz: np.ndarray
    direction: np.ndarray
    bounds_lo: np.ndarray
    bounds_hi: np.ndarray
    scale_mm: float
    gradient_sigma_mm: float
    report: dict


def geometry(image):
    return dict(size_xyz=list(image.GetSize()), spacing_xyz_mm=list(image.GetSpacing()),
                origin_lps_mm=list(image.GetOrigin()), direction=list(image.GetDirection()))


def prepare(image, quality=Quality()):
    quality.validate()
    if image.GetDimension() != 3 or image.GetNumberOfComponentsPerPixel() != 1:
        raise ValueError('Require scalar 3D surface input')
    spacing = np.asarray(image.GetSpacing(), float)
    direction = np.asarray(image.GetDirection(), float).reshape(3, 3)
    if (not np.isfinite(np.r_[spacing, direction.ravel(), image.GetOrigin()]).all() or
            np.any(spacing <= 0) or not np.allclose(direction.T @ direction, np.eye(3), atol=1e-6, rtol=0)):
        raise ValueError('Require physical spacing and orthonormal direction')
    start = perf_counter()
    scalar = sitk.GetArrayViewFromImage(image)
    if not np.isfinite(scalar).all() or np.any(scalar < 0) or np.any(scalar > 1):
        raise ValueError('Require finite probability/binary input in [0, 1]')
    coordinates = np.argwhere(scalar >= quality.threshold)
    if not len(coordinates):
        raise ValueError('Empty thresholded input')
    margin = np.ceil(quality.margin_mm / spacing[::-1]).astype(int)
    low = np.maximum(coordinates.min(0) - margin, 0)
    high = np.minimum(coordinates.max(0) + margin + 1, scalar.shape)
    cropped = sitk.Cast(sitk.RegionOfInterest(image,
        [int(v) for v in (high - low)[::-1]], [int(v) for v in low[::-1]]), sitk.sitkFloat32)
    target_spacing = np.repeat(quality.isotropic_spacing_mm, 3)
    size = np.maximum(np.ceil((np.asarray(cropped.GetSize(), float) - 1) *
        np.asarray(cropped.GetSpacing()) / target_spacing).astype(int) + 1, 2)
    # Fail before allocating an unexpectedly huge isotropic grid.
    if np.prod(size, dtype=np.int64) > 80000000 or max(size) > 1024:
        raise ValueError('Isotropic grid exceeds the bounded 80M-voxel/1024-axis preparation budget')
    resampled = sitk.Resample(cropped, [int(v) for v in size], sitk.Transform(),
        sitk.sitkLinear, cropped.GetOrigin(), list(target_spacing), cropped.GetDirection(),
        0.0, sitk.sitkFloat32)
    timings = {'crop_and_linear_resample': perf_counter() - start}
    start = perf_counter()
    if quality.smoothing_sigma_mm > 0:
        if min(size) < 4:
            raise ValueError('Recursive Gaussian requires at least four samples per axis')
        resampled = sitk.SmoothingRecursiveGaussian(resampled, quality.smoothing_sigma_mm)
    probability = sitk.GetArrayFromImage(resampled).astype(np.float32, copy=False)
    if quality.axial_smoothing_sigma_mm > quality.smoothing_sigma_mm:
        extra = np.sqrt(quality.axial_smoothing_sigma_mm ** 2 - quality.smoothing_sigma_mm ** 2) / target_spacing[2]
        probability = ndi.gaussian_filter(probability, sigma=(extra, 0, 0), mode='nearest').astype(np.float32, copy=False)
    timings['probability_gaussian_and_axial'] = perf_counter() - start
    start = perf_counter()
    mask = probability >= quality.threshold
    if quality.keep_largest_component:
        labels, count = ndi.label(mask, structure=ndi.generate_binary_structure(3, 3))
        if count:
            sizes = np.bincount(labels.ravel()); sizes[0] = 0
            mask = labels == int(np.argmax(sizes))
            probability[~ndi.binary_dilation(mask, iterations=2)] = 0
    if not mask.any():
        raise ValueError('Surface smoothing removed all thresholded support')
    timings['threshold_and_largest_component'] = perf_counter() - start
    return Prepared(probability, mask, resampled, geometry(image), low.tolist(), quality, timings)


def contour_seed(mask):
    """ITK Maurer uses the 26-neighbour object contour, ignoring image exterior.

    Do not substitute distance(inside)-distance(outside). The latter is positive
    at object boundary voxel centres whereas Maurer is zero there.
    """
    mask = np.asarray(mask, bool)
    contour = mask & ~ndi.minimum_filter(mask, size=3, mode='nearest')
    if not contour.any():
        raise ValueError('No finite in-image contour; all-foreground fields are unsupported')
    return contour


def signed_maurer(prepared):
    start = perf_counter()
    image = sitk.GetImageFromArray(prepared.mask.astype(np.uint8)); image.CopyInformation(prepared.image)
    sdf = sitk.GetArrayFromImage(sitk.SignedMaurerDistanceMap(image,
        insideIsPositive=True, squaredDistance=False, useImageSpacing=True))
    return sdf, dict(backend='PS_SimpleITK_SignedMaurer', total_seconds=perf_counter() - start)


def signed_from_distance(prepared, distance):
    """Inject a tested EDT backend; include seed preparation and sign cost."""
    start = perf_counter()
    # Only distances up to max_distance_mm survive the original clipping.
    # Any voxel outside this domain is farther than that from every seed;
    # its clipped distance is exactly -max_distance_mm. This is a distance
    # computation ROI, not a change to the full probability/SDF geometry.
    low, high = distance_domain(prepared)
    slices = tuple(slice(int(lo), int(hi)) for lo, hi in zip(low, high))
    mask = prepared.mask[slices]
    contour = contour_seed(mask)
    seeds_seconds = perf_counter() - start
    field, stats = distance(~contour, np.asarray(prepared.image.GetSpacing())[::-1])
    if field.shape != mask.shape or field.dtype != np.float32 or not np.isfinite(field).all():
        raise ValueError('Invalid distance backend result')
    field[~mask] *= -1
    result = np.full(prepared.mask.shape, -prepared.quality.max_distance_mm, np.float32)
    result[slices] = np.clip(field, -prepared.quality.max_distance_mm, prepared.quality.max_distance_mm)
    return result, dict(backend=stats['backend'], total_seconds=perf_counter() - start,
        contour_preparation_seconds=seeds_seconds, distance=stats, boundary='26_neighbour_object_contour',
        clipped_distance_ROI_lo_zyx=low.tolist(), clipped_distance_ROI_hi_zyx=high.tolist(),
        distance_ROI_shape_zyx=list(mask.shape), full_SDF_geometry_preserved=True)


def distance_domain(prepared):
    coordinates = np.argwhere(prepared.mask)
    margin = np.ceil(prepared.quality.max_distance_mm / np.asarray(prepared.image.GetSpacing())[::-1]).astype(int)
    low = np.maximum(coordinates.min(0) - margin, 0)
    high = np.minimum(coordinates.max(0) + margin + 1, prepared.mask.shape)
    return low, high


def finish(prepared, sdf, distance_stats):
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
    start = perf_counter()
    if quality.surface_smoothing_sigma_mm > 0 and quality.surface_smoothing_strength > 0:
        sigma = quality.surface_smoothing_sigma_mm / spacing[::-1]
        regularized = ndi.gaussian_filter(sdf, sigma=tuple(sigma), mode='nearest')
        strength = quality.surface_smoothing_strength
        regularized = (1 - strength) * sdf + strength * regularized
        low, high = -2 * quality.surface_smoothing_sigma_mm, 2 * quality.surface_smoothing_sigma_mm
        for _ in range(14):
            offset = (low + high) * 0.5
            if int(np.count_nonzero(regularized > offset)) > target:
                low = offset
            else:
                high = offset
        offset = (low + high) * 0.5
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
    return Field(q, spacing, origin, direction, corners.min(0), corners.max(0),
                 quality.quantization_mm, quality.gradient_sigma_mm, stats)


def build(image, quality=Quality(), distance_backend=None):
    prepared = prepare(image, quality)
    sdf, stats = signed_maurer(prepared) if distance_backend is None else signed_from_distance(prepared, distance_backend)
    return finish(prepared, sdf, stats)


def c6_capacity(field):
    """Inspect immutable accepted C6 limits without clipping or resampling."""
    # C6 accepts Q5 only. An ultra Q6 field must never be silently interpreted as Q5.
    saturated = np.clip(np.rint(field.sdf_q_zyx.astype(np.float32) * field.scale_mm * 32), -128, 32767).astype(np.int16)
    pad = tuple((0, (-n) % 4) for n in saturated.shape)
    values = np.pad(saturated, pad, constant_values=-128)
    z, y, x = np.asarray(values.shape) // 4
    count = int((values != -128).reshape(z, 4, y, 4, x, 4).any((1, 3, 5)).sum())
    size = np.asarray(field.sdf_q_zyx.shape)[::-1]
    return dict(shape_xyz=size.tolist(), maximum_shape_xyz=[256, 192, 128],
        active_4_cubed_bricks=count, maximum_bricks=4096,
        Q5_scale_compatible=field.scale_mm == 1/32,
        fits_current_C6=bool(np.all(size <= [256, 192, 128]) and count <= 4096 and field.scale_mm == 1/32),
        geometry_changed_for_capacity=False)
