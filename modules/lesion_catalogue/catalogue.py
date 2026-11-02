"""26-connected candidate catalogue without relabeling navigation targets."""
import math
import numpy as np
from scipy import ndimage as ndi


def physical(zyx, image):
    q=np.asarray(zyx,dtype=np.float64)[...,::-1]*np.asarray(image.GetSpacing())
    return q @ np.asarray(image.GetDirection()).reshape(3,3).T + np.asarray(image.GetOrigin())


def catalogue(mask, image, minimum_volume_mm3=14.0, make_labels=False):
    minimum=float(minimum_volume_mm3)
    if not math.isfinite(minimum) or minimum<0:
        raise ValueError('Minimum volume must be finite and nonnegative')
    mask=np.asarray(mask)
    if image.GetDimension()!=3 or image.GetNumberOfComponentsPerPixel()!=1:
        raise ValueError('Catalogue requires one scalar 3D physical grid')
    if mask.shape!=tuple(reversed(image.GetSize())):
        raise ValueError('Mask and physical grid sizes differ')
    if mask.dtype.kind not in ('b','u','i') or mask.size==0 or mask.min()<0 or mask.max()>1:
        raise ValueError('Mask must be binary boolean/integer 0/1')
    spacing=np.asarray(image.GetSpacing(),float)
    origin=np.asarray(image.GetOrigin(),float)
    direction=np.asarray(image.GetDirection(),float).reshape(3,3)
    if not np.isfinite(np.r_[spacing,origin,direction.ravel()]).all() or np.any(spacing<=0) or abs(np.linalg.det(direction))<1e-9:
        raise ValueError('Invalid physical geometry')
    output=np.zeros(mask.shape,np.uint16) if make_labels else None
    report=dict(schema='kv260.lesion_catalogue.v1',connectivity=26,
        minimum_volume_mm3=minimum,raw_component_count=0,retained_component_count=0,
        excluded_component_count=0,rows=[],coordinates='LPS',units='mm',
        label_dtype='uint16',navigation_index_kind='original_full_mask_volume_rank_zero_based',
        exported_label_id_kind='retained_volume_rank_one_based',backend='PS_cropped_connected_components',
        candidate_status='model_candidate_not_confirmed_lesion',original_mask_changed=False)
    extent=[np.flatnonzero(np.any(mask,axis=tuple(j for j in range(3) if j!=i))) for i in range(3)]
    if any(len(v)==0 for v in extent):
        report['state']='provided_empty_mask'
        return report,output
    offset=np.asarray([a[0] for a in extent],int)
    end=np.asarray([a[-1]+1 for a in extent],int)
    slices=tuple(slice(a,b) for a,b in zip(offset,end))
    labels,count=ndi.label(mask[slices]!=0,np.ones((3,3,3),np.uint8))
    sizes=np.bincount(labels.ravel());boxes=ndi.find_objects(labels)
    lookup=np.zeros(count+1,np.uint16);voxel_volume=float(np.prod(spacing))
    rows=[]
    for source_index,label in enumerate(sorted(range(1,count+1),key=lambda i:(-sizes[i],i))):
        volume=float(sizes[label]*voxel_volume)
        if volume<minimum:
            continue
        if len(rows)>=np.iinfo(np.uint16).max:
            raise ValueError('Retained catalogue exceeds uint16 label capacity')
        box=boxes[label-1];component=labels[box]==label
        lower=offset+np.asarray([s.start for s in box],int)
        upper=offset+np.asarray([s.stop-1 for s in box],int)
        centroid=physical(np.asarray(ndi.center_of_mass(component))+lower,image)
        bounds=np.asarray([physical([z,y,x],image) for z in (lower[0],upper[0])
                           for y in (lower[1],upper[1]) for x in (lower[2],upper[2])])
        new_id=len(rows)+1;lookup[label]=new_id
        rows.append(dict(index=source_index,id=new_id,source_component_label=int(label),
            voxel_count=int(sizes[label]),volume_mm3=volume,
            equivalent_sphere_diameter_mm=float((6*volume/np.pi)**(1/3)),
            centroid_lps_mm=centroid.tolist(),centroid_xyz_mm=centroid.tolist(),
            bbox_xyz_size=[*lower[::-1].tolist(),*(upper-lower+1)[::-1].tolist()],
            bounds_min=bounds.min(axis=0).tolist(),bounds_max=bounds.max(axis=0).tolist(),
            label_status='model_candidate_not_confirmed_lesion'))
    if make_labels:
        output[slices]=lookup[labels]
    report.update(state='retained_candidates' if rows else 'all_candidates_filtered',
        raw_component_count=int(count),retained_component_count=len(rows),
        excluded_component_count=int(count)-len(rows),rows=rows,
        connected_component_ROI_size_zyx=(end-offset).tolist())
    return report,output
