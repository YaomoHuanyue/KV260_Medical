"""Airway cross-section masks for depth-tested branch entrance annotations."""
import base64
import gzip
import numpy as np
from scipy import ndimage as ndi


def aperture(centerline, center, tangent, branch_point_ids, point_tree):
    c = centerline
    center = np.asarray(center, dtype=float)
    normal = np.asarray(tangent, dtype=float)
    length = np.linalg.norm(normal)
    if length < 1e-8:
        return None
    normal /= length
    axis = np.eye(3)[np.argmin(np.abs(normal))]
    u = np.cross(normal, axis); u /= np.linalg.norm(u)
    v = np.cross(normal, u)
    radius = float(c.sample_radius(center[None])[0])
    half = max(radius*2.2, min(c.geometry.spacing_xyz)*3)
    size = min(129, max(33, int(np.ceil(half*2/(min(c.geometry.spacing_xyz)*.4))) | 1))
    step = half*2/(size-1)
    coordinates = np.linspace(-half, half, size)
    x, y = np.meshgrid(coordinates, coordinates)
    world = center+x[...,None]*u+y[...,None]*v
    zyx = c.geometry.to_zyx(world.reshape(-1,3))-c.offset_zyx
    inside = ndi.map_coordinates(c.mask, zyx.T, order=1, output=np.float32,
                                mode='constant', cval=0, prefilter=False).reshape(size,size) > .5
    # A cut through a crowded junction can intersect several exits. Keep the
    # selected branch's Voronoi territory, then only the connected lumen around
    # the selected centerline point. Shared start nodes do not own another exit.
    _, owners = point_tree.query(world.reshape(-1,3))
    owned = np.isin(owners, branch_point_ids).reshape(size,size)
    labels, _ = ndi.label(inside & owned, structure=np.ones((3,3)))
    label = labels[size//2,size//2]
    if not label:
        return None
    mask = labels == label
    interior = ndi.binary_erosion(mask)
    # Representative points locate the visible part of the entrance for the
    # large screen arrow. The full mask, not these points, defines the outline.
    stride = max(1,size//10)
    seeds = [(size//2,size//2)]
    seeds += [(a,b) for a in range(stride//2,size,stride) for b in range(stride//2,size,stride)
              if interior[a,b]]
    seeds = seeds[:1]+seeds[1:][::max(1,int(np.ceil((len(seeds)-1)/32)))]
    visible_points = [world[a,b].tolist() for a,b in seeds]
    return dict(center_lps_mm=center.tolist(), normal_lps=normal.tolist(),
                u_lps=u.tolist(), v_lps=v.tolist(), size=size, step_mm=step,
                mask_gzip=base64.b64encode(gzip.compress(mask.astype(np.uint8).tobytes(),mtime=0)).decode(),
                sample_points_lps_mm=visible_points, lumen_pixels=int(mask.sum()),
                area_mm2=float(mask.sum()*step*step))


def visible_samples(centerline, eye, gate):
    """Use the same trilinear mask threshold as the viewer, without a volume copy."""
    c=centerline;eye=np.asarray(eye);count=0
    for point in gate['sample_points_lps_mm']:
        delta=np.asarray(point)-eye
        steps=max(2,int(np.ceil(np.linalg.norm(delta)/(min(c.geometry.spacing_xyz)*.35))))
        world=eye+np.linspace(0,1,steps+1)[:,None]*delta
        coords=c.geometry.to_zyx(world)-c.offset_zyx
        values=ndi.map_coordinates(c.mask,coords.T,order=1,output=np.float32,
                                  mode='constant',cval=0,prefilter=False)
        count+=int(np.all(values>.5))
    return count
