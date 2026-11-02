"""Atomic, self-contained scalar/PL-mesh/route/camera/guidance scene bundle.

Preparation is PS work. Scene packets target the unchanged accepted C9 core;
topology must already be extracted by C1. This module never invokes PS MC.
"""
from pathlib import Path
import hashlib
import json
import os
import tempfile
import numpy as np

from modules.surface_route.audit import MeshRegion
from modules.surface_route.guidance_r5 import ScalarField
from modules.navigation.navigation.camera import poses
from modules.navigation.navigation.guidance import guidance_route_id
from dfx.route_audit_speed.protocol import validate_stored_audit, hud_from_pl, route_digest
from dfx.surface_quality.prepare import pack_scene, unpack_scene, normal_matrix

SCHEMA = 'kv260.surface_route.complete_scene.v1'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def arrays(path):
    with np.load(path, allow_pickle=False) as archive:
        return {k: archive[k] for k in archive.files}


def vertex_normals(points, faces):
    # Same area-weighted definition as reconstruction/airway/mesh_reconstruction.py.
    # Overview normal preparation is PS; C9 computes its own scalar gradient in PL.
    p = np.asarray(points, dtype=np.float32)
    normals = np.zeros_like(p)
    tri = p[faces]
    cross = np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0])
    for axis in range(3):
        normals[:, axis] = np.bincount(faces.ravel(), weights=np.repeat(cross[:, axis], 3),
                                       minlength=len(points))
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-20)
    return normals


def mesh_digest(points, faces):
    return digest(canonical([list(np.shape(points)), list(np.shape(faces))])
                  +np.ascontiguousarray(points, dtype='<f4').tobytes()
                  +np.ascontiguousarray(faces, dtype='<i8').tobytes())


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
        if not np.array_equal(camera[key], wanted):
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


def build_bundle(output, *, scalar, geometry, bits, points, faces, mesh_proof,
                 route, report, camera, guidance, targets, provenance):
    """Publish a complete new directory once; never reuse partial outputs.

    The caller verifies extraction and planning evidence before supplying it.
    A future completed-CT producer can use this API without any own-CT names.
    """
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    field = ScalarField(scalar, geometry, bits)
    review = validate_geometry(field, points, faces, mesh_proof, route, report, camera, guidance)
    available = {e['id']: e for e in guidance['events'] if e['available']}
    if set(targets) != set(available):
        raise ValueError('Targets must exactly cover available branch events')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.'+output.name+'.staging-', dir=output.parent))
    try:
        np.savez_compressed(stage/'mesh.npz', points=points, faces=faces)
        np.savez_compressed(stage/'route.npz', **route)
        np.savez_compressed(stage/'camera.npz', **camera)
        write_json(stage/'route.json', report)
        write_json(stage/'guidance.json', guidance)
        write_json(stage/'hud.json', hud_from_pl(route, report))
        normals = vertex_normals(points, faces)
        stream = np.empty((len(faces)*3, 6), '<f4')
        stream[:, :3] = np.asarray(points)[faces].reshape(-1, 3)
        stream[:, 3:] = normals[faces].reshape(-1, 3)
        stream.tofile(stage/'airway.vertices')
        scenes = {}
        for event_id in [-1]+sorted(available):
            selected = np.zeros(scalar.shape, bool) if event_id == -1 else targets[event_id]
            if (selected.dtype != np.dtype(bool) or selected.shape != scalar.shape
                    or np.any(selected & (scalar <= 0))):
                raise ValueError('Branch targets must be inside the same positive scalar')
            if event_id != -1 and int(selected.sum()) != available[event_id]['target_voxels']:
                raise ValueError('Branch target count disagrees with guidance')
            blob, stats = pack_scene(scalar, selected, 8100+event_id+1, geometry, bits=bits)
            got, labels = unpack_scene(blob)
            if not np.array_equal(got, scalar) or not np.array_equal(labels, selected):
                raise ValueError('C9 packet roundtrip changed scalar or branch labels')
            name = f'scene_{event_id}.bin'
            (stage/name).write_bytes(blob)
            scenes[str(event_id)] = dict(file=name, target_sha256=digest(selected.tobytes()),
                                         target_voxels=int(selected.sum()), **stats)
        payloads = {p.name: sha(p) for p in sorted(stage.iterdir())}
        identity = dict(geometry=geometry, bits=bits, scalar_sha256=field.sha256,
                        route_digest=route_digest(route), guidance_route_id=guidance['route_id'],
                        files_sha256=payloads, provenance=provenance, mesh_proof=mesh_proof)
        meta = dict(schema=SCHEMA, complete=True, identity=identity, revision=digest(canonical(identity)),
                    geometry=geometry, bits=bits, renderer_scalar_sha256=field.sha256,
                    route_id=guidance['route_id'], scenes=scenes, region_review=review,
                    mesh=dict(file='airway.vertices', vertices=len(stream), topology='PL_C1',
                              overview_normals='PS_area_weighted', scalar_sha256=field.sha256),
                    route_file='route.npz', camera_file='camera.npz', guidance_file='guidance.json',
                    report_file='route.json', hud_file='hud.json',
                    preparation_backend='PS', navigation_normal_backend='PL_C9',
                    automatic_quality_changes=False, atomic_scene_activation_required=True,
                    PS_Marching_Cubes_used=False, new_bitstream=False, production_promoted=False)
        write_json(stage/'scene.json', meta)
        verify_bundle(stage)
        # os.rename cannot replace a nonempty directory. No in-place publication.
        os.rename(stage, output)
        return meta
    except BaseException:
        # Only this invocation's exclusive staging directory is cleaned.
        for path in stage.iterdir():
            if path.is_file():
                path.unlink()
        stage.rmdir()
        raise


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
