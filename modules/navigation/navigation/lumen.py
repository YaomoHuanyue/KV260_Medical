"""Route-selected 3D lumen regions, used before the first visible wall hit."""
import base64
import gzip
import numpy as np
from scipy import ndimage as ndi


def lumen_owners(c, point_tree):
    voxels = np.argwhere(c.mask)
    _, owners = point_tree.query(c.geometry.to_lps(voxels + c.offset_zyx))
    return voxels, owners


def selected_lumen(c, branch_id, branches, voxels, owners, anchor):
    """Include the chosen daughter and its descendants, never its siblings.

    The region is sampled along the visible ray, not intersected with a plane.
    A ray behind a foreground wall never reaches it. Crop padding prevents the
    GPU's clamped texture boundary from extending a label outside the region.
    """
    descendants = {branch_id}
    while True:
        more = {b['id'] for b in branches.values() if b['parent_branch'] in descendants}
        if more <= descendants:
            break
        descendants |= more
    points = set()
    for bid in descendants:
        points.update(branches[bid]['point_ids'])
    points.discard(branches[branch_id]['start'])
    # Do not color the wide shared fork cavity. Reach the selected daughter's
    # narrower throat first, then include its full 3D continuation. Unlike a
    # plane cut, this remains attached to the curved lumen as the camera turns.
    chain=branches[branch_id]['point_ids']
    xyz=c.points_lps_mm[chain]
    arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(xyz,axis=0),axis=1))]
    anchor_center=np.asarray(anchor['center_lps_mm']) if anchor else xyz[1]
    start=int(np.argmin(np.linalg.norm(xyz-anchor_center,axis=1)))
    kept=[pid for pid,s in zip(chain,arc) if s>=arc[start]*.9 and pid!=chain[0]]
    points.difference_update(chain[:-1])
    points.update(kept)
    selected = voxels[np.isin(owners, list(points))]
    if not len(selected):
        return None
    low = np.maximum(0, selected.min(axis=0)-2)
    high = np.minimum(c.mask.shape, selected.max(axis=0)+3)
    mask = np.zeros(tuple(high-low), np.uint8)
    mask[tuple((selected-low).T)] = 1
    # Smooth only the annotation ownership, never the source airway geometry.
    sigma=min(c.geometry.spacing_xyz)*.55/np.asarray(c.geometry.spacing_xyz[::-1])
    coverage=np.rint(ndi.gaussian_filter(mask.astype(np.float32),sigma=sigma,
                                      mode='constant',cval=0)*255).astype(np.uint8)
    # The arrow can target an actually visible point inside this same region.
    # Preserve cross-section interior samples, then add daughter centerline
    # points so a curved channel does not depend on a single plane being seen.
    samples = anchor['sample_points_lps_mm'][:] if anchor else []
    samples += c.points_lps_mm[kept].tolist()
    return dict(origin_lps_mm=c.geometry.to_lps(low+c.offset_zyx).tolist(),
                shape_xyz=list(mask.shape[::-1]),
                mask_gzip=base64.b64encode(gzip.compress(coverage.tobytes(),mtime=0)).decode(),
                encoding='coverage_u8',
                branch_ids=sorted(descendants),lumen_voxels=int(mask.sum()),
                throat_advance_mm=float(arc[start]),
                sample_points_lps_mm=samples,
                policy='selected_daughter_and_descendants_before_first_wall')
