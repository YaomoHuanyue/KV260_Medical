"""Atomic standalone export of the active, content-bound C1/C9 scene.

Serialization runs on PS. Mesh topology and the accepted scene packets retain
their PL provenance. Original-grid comparisons are reference reports only;
they are never substituted for the new scalar field's route or clearance.
"""
from pathlib import Path
import csv
import json
import math
import os
import shutil
import sys
import tempfile
from time import perf_counter
import xml.etree.ElementTree as ET
import numpy as np
import SimpleITK as sitk

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.surface_route.bundle_r8 import arrays, sha, write_json
from modules.surface_route.bundle_reader_r9 import verify_bundle
from modules.surface_route.ui_bridge_r9 import asset_path
from modules.airway_detail.active_scene_r20 import verify_active_scene
from modules.airway_detail.export_review_r20 import append_export
def verify_prepared(path,root=ROOT):
    if Path(root).resolve()!=ROOT:raise ValueError('Current project root required')
    return verify_active_scene(path)
from modules.surface_export.export import generation_rgb, load_mesh
from modules.surface_export.vtp import write_vtp


def compact_surface(bundle, attribute_path):
    """Index by original vertex ID, preserving split fans and triangle order."""
    bundle = Path(bundle)
    mesh = arrays(bundle/'mesh.npz')
    stream = np.fromfile(bundle/'airway.vertices', '<f4').reshape(-1, 6)
    values = np.fromfile(attribute_path, '<f4').reshape(-1, 4)
    face_ids = mesh['faces'].reshape(-1)
    if stream.shape != (len(face_ids), 6) or values.shape != (len(face_ids), 4):
        raise ValueError('Surface/attribute stream cardinality differs')
    if not np.isfinite(stream).all() or not np.isfinite(values).all():
        raise ValueError('Non-finite active surface')
    if not np.array_equal(stream[:, :3], mesh['points'][face_ids].astype('<f4')):
        raise ValueError('Displayed triangle coordinates differ from C1 mesh')
    used, first, inverse = np.unique(face_ids, return_index=True, return_inverse=True)
    if (not np.array_equal(stream[:, 3:], stream[first[inverse], 3:])
            or not np.array_equal(values, values[first[inverse]])):
        raise ValueError('Split normal/attribute values require distinct mesh IDs')
    points = mesh['points'][used]
    faces = inverse.astype(np.int64).reshape(-1, 3)
    v = values[first]
    if np.any(v[:, 0] != np.floor(v[:, 0])) or np.any(~np.isin(v[:, 3], [0, 1])):
        raise ValueError('Invalid connected/generation attributes')
    attributes = dict(Normals=stream[first, 3:], generation=v[:, 0].astype(np.int16),
        radius_mm=v[:, 1], network_probability=v[:, 2],
        probability_available=(v[:, 2] >= 0).astype(np.uint8),
        connected_to_root=v[:, 3].astype(np.uint8), RGB=generation_rgb(v[:, 0], v[:, 3]))
    return points, faces, attributes


def write_stl(path, points, faces):
    dtype = np.dtype([('normal', '<f4', (3,)), ('vertex', '<f4', (3, 3)), ('attribute', '<u2')])
    with Path(path).open('xb') as target:
        target.write(b'KV260 active PL C1 surface; LPS millimeters'.ljust(80, b'\0'))
        target.write(np.asarray(len(faces), '<u4').tobytes())
        for start in range(0, len(faces), 16384):
            triangles = points[faces[start:start+16384]]
            normal = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
            normal /= np.maximum(np.linalg.norm(normal, axis=1)[:, None], 1e-20)
            rows = np.zeros(len(triangles), dtype)
            rows['normal'], rows['vertex'] = normal, triangles
            target.write(rows.tobytes())


def write_route(bundle, destination):
    route = arrays(Path(bundle)/'route.npz')
    p, r, arc = [route[k] for k in ('points_lps_mm', 'radius_mm', 'arc_mm')]
    with (destination/'navigation_route.csv').open('x', encoding='utf-8', newline='') as output:
        writer = csv.writer(output)
        writer.writerow(['index', 'x_lps_mm', 'y_lps_mm', 'z_lps_mm', 'arc_mm', 'radius_mm'])
        for i in range(len(p)):
            writer.writerow([i, *[format(float(v), '.17g') for v in p[i]],
                             format(float(arc[i]), '.17g'), format(float(r[i]), '.17g')])
    vtk = ET.Element('VTKFile', type='PolyData', version='0.1', byte_order='LittleEndian')
    piece = ET.SubElement(ET.SubElement(vtk, 'PolyData'), 'Piece',
        NumberOfPoints=str(len(p)), NumberOfLines=str(int(len(p) > 1)))
    def column(parent, name, value, kind, components=1):
        node = ET.SubElement(parent, 'DataArray', type=kind, Name=name,
                             NumberOfComponents=str(components), format='ascii')
        node.text = ' '.join(format(float(v), '.17g') if kind == 'Float64' else str(int(v))
                             for v in np.asarray(value).ravel())
    data = ET.SubElement(piece, 'PointData', Scalars='radius_mm')
    column(data, 'radius_mm', r, 'Float64')
    column(data, 'arc_mm', arc, 'Float64')
    column(ET.SubElement(piece, 'Points'), 'Points', p, 'Float64', 3)
    lines = ET.SubElement(piece, 'Lines')
    column(lines, 'connectivity', np.arange(len(p)) if len(p) > 1 else [], 'Int32')
    column(lines, 'offsets', [len(p)] if len(p) > 1 else [], 'Int32')
    with (destination/'route.vtp').open('xb') as output:
        output.write(b'<?xml version="1.0"?>\n'+ET.tostring(vtk, encoding='utf-8')+b'\n')
    shutil.copyfile(Path(bundle)/'route.json', destination/'navigation_route.json')


def export_scene(scene_path, destination, input_sha, minimum_volume_mm3=14., root=ROOT):
    from ui.features.export import export_result
    from modules.lesion_catalogue.export import export_catalogue
    from modules.report_export.reports import validate, write_reports

    start = perf_counter()
    root = Path(root).resolve()
    scene_path, destination = Path(scene_path).resolve(), Path(destination).resolve()
    if (not scene_path.is_relative_to(root) or not destination.is_relative_to(root)
            or destination == root or destination.exists()):
        raise ValueError('New export destination and prepared scene inside project required')
    if not math.isfinite(float(minimum_volume_mm3)) or minimum_volume_mm3 < 0:
        raise ValueError('Minimum candidate volume must be finite and nonnegative')
    scene = verify_prepared(scene_path, root)
    if scene['input_sha256'] != input_sha:
        raise ValueError('Active scene belongs to a different selected CT')
    active = scene['complete_surface']
    bundle, source = Path(active['bundle']).resolve(), Path(scene['result']).resolve()
    for original in (source, bundle, scene_path.parent):
        if destination == original or destination.is_relative_to(original) or original.is_relative_to(destination):
            raise ValueError('Export must be separate from all source assets')
    meta = verify_bundle(bundle, active['revision'])
    original_reports = validate(source, input_sha)
    # Bind every leaf input used by the inherited complete mask/STL/recovery exporter.
    source_files = {p.relative_to(source).as_posix():sha(p) for p in source.rglob('*') if p.is_file()}
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.'+destination.name+'.pending_', dir=destination.parent))
    payload = stage/'payload'
    try:
        inherited = export_result(source, payload, input_sha)
        # These flat files refer to the original grid. Full, independently
        # validated copies belong only to original_analysis below.
        for name in ('report.json', 'airway.stl', 'route.vtp', 'navigation_route.csv',
                     'navigation_route.json', 'navigation_branches.json',
                     'navigation_instrument_profiles.json', 'navigation_alternative_routes.json'):
            path = payload/name
            if path.is_file():
                path.unlink()  # Exact file created in this private, unpublished stage.
        surface_start = perf_counter()
        surfaces = payload/'surfaces'
        surfaces.mkdir()
        attribute_path = asset_path(scene_path.parent, scene['meshes']['airway']['attributes']['file'], root)
        points, faces, attributes = compact_surface(bundle, attribute_path)
        write_stl(payload/'airway.stl', points, faces)
        write_vtp(surfaces/'airway.vtp', points, faces, attributes)
        structures = dict(airway=dict(file='airway.vtp', points=len(points), triangles=len(faces),
            point_arrays=list(attributes), geometry_producer='PL_C1_binary_Marching_Cubes',
            source_revision=active['revision'], preview_decimation_used=False,
            triangle_order_and_positions_exact=True, overview_normal_source='prepared_UI_stream'))
        for name in ('lung', 'nodule'):
            path = source/'reconstruction'/(name+'.npz')
            if not path.is_file():
                continue
            p, f, n = load_mesh(path)
            color = [148, 209, 250] if name == 'lung' else [255, 138, 59]
            write_vtp(surfaces/(name+'.vtp'), p, f, dict(Normals=n,
                RGB=np.broadcast_to(np.asarray(color, np.uint8), (len(p), 3))))
            structures[name] = dict(file=name+'.vtp', points=len(p), triangles=len(f),
                source_mesh_sha256=sha(path), geometry_recomputed=False, preview_decimation_used=False)
        surface_seconds = perf_counter()-surface_start
        write_json(surfaces/'report.json', dict(schema='kv260.surface_export.active.v2', status='completed',
            active_revision=active['revision'], input_sha256=input_sha, structures=structures,
            coordinates='LPS', units='mm', active_color='RGB', probability_is_not_accuracy=True,
            files={p.name:sha(p) for p in surfaces.iterdir() if p.is_file()}))
        write_route(bundle, payload)
        copied = payload/'active_scene'/'bundle'
        shutil.copytree(bundle, copied)
        verify_bundle(copied, active['revision'])
        shutil.copyfile(attribute_path, copied.parent/'airway.attributes')
        write_json(copied.parent/'binding.json', dict(schema='kv260.export.active_scene.v1',
            revision=active['revision'], route_id=active['route_id'], scalar_sha256=active['scalar_sha256'],
            input_sha256=input_sha, bundle='bundle/scene.json', attributes='airway.attributes',
            attributes_sha256=sha(copied.parent/'airway.attributes')))
        recovery_export=append_export(scene,payload)
        reference_start = perf_counter()
        reports = write_reports(original_reports, payload/'original_analysis')
        # Scope annotation is outside the sealed copied raw reports.
        write_json(payload/'original_analysis'/'scope.json', dict(
            applies_to='original_segmentation_grid_reference_only',
            active_surface_clearance_or_Pareto_recomputed=False,
            current_route='../navigation_route.json', original_result=str(source)))
        reference_seconds = perf_counter()-reference_start
        image = sitk.ReadImage(str(asset_path(scene_path.parent, scene['input'], root)))
        catalogue = export_catalogue(source/'segmentation/nodule_mask.nii.gz', payload/'lesions',
                                     minimum_volume_mm3, image)
        if verify_prepared(scene_path, root) != scene:
            raise ValueError('Prepared scene changed during export')
        if source_files != {p.relative_to(source).as_posix():sha(p) for p in source.rglob('*') if p.is_file()}:
            raise ValueError('Original result changed during export')
        report = dict(schema='kv260.export.v6', status='completed', input_sha256=input_sha,
            coordinates='LPS', units='mm', source_result=str(source), source_scene_sha256=sha(scene_path),
            active_revision=active['revision'], active_route_id=active['route_id'],
            renderer_scalar_sha256=active['scalar_sha256'], bundle_identity=meta['identity'],
            masks=inherited['masks'], original_source_files_sha256=source_files,recovery_review=recovery_export,
            surface_export_seconds=surface_seconds, complete_report_seconds=reference_seconds,
            complete_reports='original_analysis/index.json',
            complete_reports_scope='original_segmentation_grid_reference_only',
            active_surface_comparisons_recomputed=False, minimum_candidate_volume_mm3=minimum_volume_mm3,
            lesion_catalogue_state=catalogue['state'], original_report_profile_count=reports['profile_query_count'],
            computation=dict(surface_topology='PL_C1', serialization='PS',
                             attributes='accepted_UI_PS_attributes', additional_PL_resources=0),
            source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in (
                Path(__file__), ROOT/'modules/surface_export/vtp.py', ROOT/'ui/features/export.py',
                ROOT/'modules/surface_route/ui_bridge_r9.py')},
            files={p.relative_to(payload).as_posix():sha(p) for p in payload.rglob('*') if p.is_file()},
            elapsed_seconds=perf_counter()-start, production_promoted=False)
        write_json(payload/'report.json', report)
        os.rename(payload, destination)
        stage.rmdir()
        return report
    except BaseException:
        write_json(stage/'FAILED.json', dict(status='failed_unpublished_export_original_sources_preserved'))
        raise


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--scene', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    p.add_argument('--input-sha', required=True)
    p.add_argument('--minimum-candidate-volume', type=float, default=14.)
    a = p.parse_args()
    report = export_scene(a.scene, a.destination, a.input_sha, a.minimum_candidate_volume)
    print(json.dumps(dict(event='exported', path=str(a.destination.resolve()), **report)))


if __name__ == '__main__':
    main()
