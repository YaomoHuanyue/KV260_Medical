"""Portable R8 reader: preserve exact camera positions, tolerate normalized-axis roundoff.

Derived from the sealed R8 validation functions. No builder or wall gate change.
"""
from pathlib import Path
import json
import numpy as np
from modules.surface_route.bundle_r8 import (ScalarField, MeshRegion, poses, digest, canonical,
    sha, arrays, validate_stored_audit, hud_from_pl, route_digest, normal_matrix,
    unpack_scene, SCHEMA, guidance_route_id, mesh_digest)


def validate_geometry(field, points, faces, mesh_proof, route, report, camera, guidance):
    if (mesh_proof.get('topology_backend') != 'PL_C1_binary_Marching_Cubes'
            or mesh_proof.get('PS_Marching_Cubes_used') is not False
            or mesh_proof.get('renderer_scalar_sha256') != field.sha256
            or mesh_proof.get('points_faces_sha256') != mesh_digest(points, faces)):
        raise ValueError('Verified PL C1 mesh provenance required')
    p, f = np.asarray(points), np.asarray(faces)
    if (p.ndim != 2 or p.shape[1:] != (3,) or f.ndim != 2 or f.shape[1:] != (3,)
            or f.dtype.kind not in 'iu' or not len(f) or not np.isfinite(p).all()
            or f.min() < 0 or f.max() >= len(p)):
        raise ValueError('Finite indexed triangle mesh required')
    region = MeshRegion(p, f, field.geometry)  # Unchanged real wall/crop gate.
    validate_stored_audit(route, report)
    rp, arc = np.asarray(route['points_lps_mm']), np.asarray(route['arc_mm'])
    if (rp.ndim != 2 or rp.shape[1:] != (3,) or not len(rp)
            or arc.shape != (len(rp),) or not np.isfinite(rp).all()
            or not np.isfinite(arc).all() or arc[0] != 0
            or np.any(np.diff(arc) <= 0)
            or not np.allclose(arc, np.r_[0., np.cumsum(np.linalg.norm(np.diff(rp, axis=0), axis=1))],
                               rtol=0, atol=1e-9)
            or report['point_count'] != len(rp)
            or abs(report['length_mm']-arc[-1]) > 1e-9
            or np.any(field.sample(rp) <= 0)):
        raise ValueError('Exact physical route within the same scalar required')
    if len(rp) > 1 and not report.get('curve_audit', {}).get('whole_curve_accepted'):
        raise ValueError('Whole-curve actual-wall/crop/source-mask review required')
    wanted_camera = poses(rp, arc)
    if set(camera) != set(wanted_camera):
        raise ValueError('Complete camera columns required')
    for key, wanted in wanted_camera.items():
        if not (np.array_equal(camera[key], wanted) if key == 'position_lps_mm' else np.allclose(camera[key], wanted, rtol=0, atol=1e-12)):
            raise ValueError('Camera belongs to a different route: '+key)
    if (guidance.get('schema') != 'kv260.surface_route.guidance.v1'
            or guidance.get('scalar_sha256') != field.sha256
            or guidance.get('route_id') != guidance_route_id(route)):
        raise ValueError('Guidance belongs to a different scalar or route')
    events = guidance['events']
    if len(rp) == 1 and (events or any(len(v) for v in camera.values())):
        raise ValueError('Root-only route cannot provide camera motion or exit cues')
    ids = [e['id'] for e in events]
    if any(type(i) is not int or i < 0 for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('Unique nonnegative branch IDs required')
    for event in events:
        if event['available']:
            lo, hi = event['show_from_mm'], event['hide_after_mm']
            if (not np.isfinite([lo, hi]).all() or lo < 0 or lo > hi or hi > arc[-1]+1e-9
                    or event['aperture']['scalar_sha256'] != field.sha256):
                raise ValueError('Invalid exit interval or cross-scalar aperture')
    return region.report



def verify_bundle(folder, expected_revision=None):
    """Validate one complete snapshot before taking the PL lock or changing UI."""
    folder = Path(folder).resolve()
    meta = json.loads((folder/'scene.json').read_text(encoding='utf-8'))
    identity = meta['identity']
    if (meta.get('schema') != SCHEMA or meta.get('complete') is not True
            or meta['revision'] != digest(canonical(identity))
            or (expected_revision is not None and meta['revision'] != expected_revision)
            or meta['geometry'] != identity['geometry'] or meta['bits'] != identity['bits']
            or meta['renderer_scalar_sha256'] != identity['scalar_sha256']
            or meta['route_id'] != identity['guidance_route_id']):
        raise ValueError('Incomplete or mixed scene revision')
    files = identity['files_sha256']
    if set(p.name for p in folder.iterdir()) != set(files)|{'scene.json'}:
        raise ValueError('Unexpected or missing bundle payload')
    for name, wanted in files.items():
        path = folder/name
        if path.name != name or path.is_symlink() or not path.is_file() or sha(path) != wanted:
            raise ValueError('Changed or unsafe scene payload: '+name)
    route, camera, mesh = arrays(folder/'route.npz'), arrays(folder/'camera.npz'), arrays(folder/'mesh.npz')
    report = json.loads((folder/'route.json').read_text(encoding='utf-8'))
    guidance = json.loads((folder/'guidance.json').read_text(encoding='utf-8'))
    neutral = (folder/'scene_-1.bin').read_bytes()
    scalar, labels = unpack_scene(neutral)
    if labels.any():
        raise ValueError('Neutral scene contains a branch annotation')
    field = ScalarField(scalar, meta['geometry'], meta['bits'])
    if field.sha256 != meta['renderer_scalar_sha256'] or route_digest(route) != identity['route_digest']:
        raise ValueError('Scene geometry identity mismatch')
    validate_geometry(field, mesh['points'], mesh['faces'], identity['mesh_proof'],
                      route, report, camera, guidance)
    if json.loads((folder/'hud.json').read_text(encoding='utf-8')) != hud_from_pl(route, report):
        raise ValueError('HUD does not match stored route audit')
    events = {str(e['id']): e for e in guidance['events'] if e['available']}
    if set(meta['scenes']) != set(events)|{'-1'}:
        raise ValueError('Scene set does not match available exit events')
    for event_id, info in meta['scenes'].items():
        filename = f'scene_{event_id}.bin'
        if info['file'] != filename or filename not in files:
            raise ValueError('Unexpected branch scene file')
        blob = (folder/filename).read_bytes()
        header = np.frombuffer(blob[:64], '<i4')
        if ((int(header[15]) >> 8) & 255) != meta['bits'] or not np.array_equal(
                header[6:15], normal_matrix(meta['geometry'], meta['bits']).ravel()):
            raise ValueError('Packet normal geometry or quantization mismatch')
        got, target = unpack_scene(blob)
        if (not np.array_equal(got, scalar) or digest(target.tobytes()) != info['target_sha256']
                or int(target.sum()) != info['target_voxels']
                or (event_id != '-1' and info['target_voxels'] != events[event_id]['target_voxels'])):
            raise ValueError('Branch packet belongs to a different scalar/target')
    stream = np.fromfile(folder/'airway.vertices', '<f4')
    if stream.size != len(mesh['faces'])*18 or meta['mesh']['vertices'] != len(mesh['faces'])*3:
        raise ValueError('Overview vertex stream size mismatch')
    if not np.array_equal(stream.reshape(-1, 6)[:, :3], mesh['points'][mesh['faces']].reshape(-1, 3)):
        raise ValueError('Overview and C1 mesh triangle coordinates differ')
    return meta

