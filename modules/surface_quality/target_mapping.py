"""Map the accepted branch coverage onto a new physical field grid.

The source annotation is gated by the original binary airway before explicit
nearest-neighbour resampling; the destination is gated by positive field values.
This changes neither route decisions nor the original mask.
"""
import base64,gzip
import numpy as np
import SimpleITK as sitk


def map_target(lumen,source_image,field_geometry,positive):
    positive=np.asarray(positive)
    spacing=np.asarray(field_geometry['spacing_xyz'],float)
    direction=np.asarray(field_geometry['direction'],float).reshape(3,3)
    origin=np.asarray(field_geometry['origin_lps_mm'],float)
    size=np.asarray(field_geometry['size_xyz'],int)
    if (positive.ndim!=3 or positive.dtype!=np.dtype(bool) or tuple(size[::-1])!=positive.shape or
            np.any(size<2) or not np.isfinite(np.r_[spacing,direction.ravel(),origin]).all() or
            np.any(spacing<=0) or not np.allclose(direction.T@direction,np.eye(3),rtol=0,atol=1e-6)):
        raise ValueError('Positive field and valid physical destination geometry required')
    if source_image.GetDimension()!=3 or source_image.GetNumberOfComponentsPerPixel()!=1:
        raise ValueError('Scalar original binary airway image required')
    original=sitk.GetArrayViewFromImage(source_image)
    if np.any((original!=0)&(original!=1)):raise ValueError('Original binary airway required')
    source_direction=np.asarray(source_image.GetDirection(),float).reshape(3,3)
    if not np.allclose(source_direction.T@source_direction,np.eye(3),rtol=0,atol=1e-6):raise ValueError('Original direction must be orthonormal')
    if lumen is None:return np.zeros_like(positive),dict(source='no_branch_event',target_voxels=0)
    if lumen.get('encoding')!='coverage_u8':raise ValueError('Unsupported branch coverage encoding')
    shape=np.asarray(lumen['shape_xyz'],int)
    if shape.shape!=(3,) or np.any(shape<=0) or np.prod(shape,dtype=np.int64)>80000000:raise ValueError('Branch coverage bounds')
    raw=gzip.decompress(base64.b64decode(lumen['mask_gzip'],validate=True))
    if len(raw)!=int(np.prod(shape)):raise ValueError('Branch coverage payload size')
    coverage=np.frombuffer(raw,np.uint8).reshape(tuple(shape[::-1]))
    continuous=np.asarray(source_image.TransformPhysicalPointToContinuousIndex(lumen['origin_lps_mm']))
    if not np.allclose(continuous,np.rint(continuous),rtol=0,atol=1e-4):raise ValueError('Branch origin not on original voxel grid')
    low=np.rint(continuous).astype(int);high=low+shape
    if np.any(low<0) or np.any(high>np.asarray(source_image.GetSize())):raise ValueError('Branch coverage outside original airway')
    roi=original[tuple(slice(int(a),int(b)) for a,b in zip(low[::-1],high[::-1]))]
    annotated=(coverage>165)&(roi!=0)
    source=sitk.GetImageFromArray(annotated.astype(np.uint8));source.SetSpacing(source_image.GetSpacing())
    source.SetDirection(source_image.GetDirection());source.SetOrigin(source_image.TransformIndexToPhysicalPoint(tuple(map(int,low))))
    destination=sitk.Image(list(map(int,size)),sitk.sitkUInt8);destination.SetSpacing(tuple(spacing))
    destination.SetDirection(tuple(direction.ravel()));destination.SetOrigin(tuple(origin))
    sampled=sitk.GetArrayFromImage(sitk.Resample(source,destination,sitk.Transform(),sitk.sitkNearestNeighbor,0,sitk.sitkUInt8))!=0
    selected=sampled&positive
    return selected,dict(source='accepted_branch_coverage_gated_by_original_binary_airway',
        threshold_greater_than=165,resampling='explicit_nearest_neighbour_in_physical_LPS',
        source_annotation_voxels=int(np.count_nonzero(coverage>165)),source_inside_airway_voxels=int(annotated.sum()),
        resampled_voxels=int(sampled.sum()),clipped_outside_positive_field_voxels=int(np.count_nonzero(sampled&~positive)),
        target_voxels=int(selected.sum()),source_mask_changed=False,route_changed=False)
