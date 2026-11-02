"""Independent triangle/attribute/route readback, including root-only scenes."""
from pathlib import Path
import argparse
import csv
import json
import sys
import tempfile
import xml.etree.ElementTree as ET
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.surface_route.bundle_r8 import arrays, sha, write_json
from modules.surface_route.bundle_reader_r9 import verify_bundle
from modules.surface_route.export_scene_r10 import compact_surface, write_stl, write_route, export_scene
from modules.surface_export.readback import readback
from modules.surface_export.vtp import write_vtp


def check_surface(folder, bundle, attributes, vtk=False):
    mesh = arrays(bundle/'mesh.npz')
    displayed = np.fromfile(bundle/'airway.vertices', '<f4').reshape(-1, 6)
    displayed_attributes = np.fromfile(attributes, '<f4').reshape(-1, 4)
    data = readback(folder/'surfaces/airway.vtp')
    indices = data['connectivity']
    np.testing.assert_array_equal(data['Points'][indices], mesh['points'][mesh['faces'].ravel()])
    np.testing.assert_array_equal(data['Normals'][indices], displayed[:, 3:])
    for i, name in enumerate(('generation', 'radius_mm', 'network_probability', 'connected_to_root')):
        np.testing.assert_array_equal(data[name][indices], displayed_attributes[:, i])
    np.testing.assert_array_equal(data['probability_available'][indices], displayed_attributes[:, 2] >= 0)
    raw = (folder/'airway.stl').read_bytes()
    count = int(np.frombuffer(raw[80:84], '<u4')[0])
    assert count == len(mesh['faces']) and len(raw) == 84+50*count
    rows = np.frombuffer(raw[84:], np.dtype([('normal', '<f4', (3,)), ('vertex', '<f4', (3, 3)), ('attribute', '<u2')]))
    np.testing.assert_array_equal(rows['vertex'], mesh['points'][mesh['faces']].astype('<f4'))
    assert np.isfinite(rows['normal']).all() and not rows['attribute'].any()
    # Third-party VTK is an additional reader, independent from our decoder.
    if vtk:
        from vtkmodules.vtkIOXML import vtkXMLPolyDataReader
        from vtkmodules.util.numpy_support import vtk_to_numpy
        reader = vtkXMLPolyDataReader()
        reader.SetFileName(str(folder/'surfaces/airway.vtp'))
        reader.Update()
        poly = reader.GetOutput()
        assert poly.GetNumberOfPolys() == len(mesh['faces'])
        np.testing.assert_array_equal(vtk_to_numpy(poly.GetPoints().GetData()), data['Points'])
        for name in ('Normals', 'generation', 'radius_mm', 'network_probability', 'RGB'):
            np.testing.assert_array_equal(vtk_to_numpy(poly.GetPointData().GetArray(name)), data[name])
    route = arrays(bundle/'route.npz')
    with (folder/'navigation_route.csv').open(encoding='utf-8', newline='') as source:
        records = list(csv.DictReader(source))
    np.testing.assert_array_equal([[float(row[k]) for k in ('x_lps_mm','y_lps_mm','z_lps_mm')]
                                  for row in records], route['points_lps_mm'])
    np.testing.assert_array_equal([float(row['radius_mm']) for row in records], route['radius_mm'])
    np.testing.assert_array_equal([float(row['arc_mm']) for row in records], route['arc_mm'])
    root = ET.parse(folder/'route.vtp').getroot()
    piece = root.find('PolyData/Piece')
    assert int(piece.attrib['NumberOfLines']) == int(len(records) > 1)
    for key in ('radius_mm', 'arc_mm'):
        text = piece.find("PointData/DataArray[@Name='"+key+"']").text or ''
        np.testing.assert_array_equal(np.fromstring(text, sep=' '), route[key])
    coordinates = piece.find('Points/DataArray').text
    np.testing.assert_array_equal(np.fromstring(coordinates, sep=' ').reshape(-1,3), route['points_lps_mm'])
    assert json.loads((folder/'navigation_route.json').read_text()) == json.loads((bundle/'route.json').read_text())
    return dict(triangles=count, displayed_vertices=len(displayed), compact_points=len(data['Points']),
                route_points=len(records), independent_VTK_reader=vtk, every_triangle_normal_attribute_and_route_exact=True)


def kernels(platform):
    bundles = ROOT/f'modules/surface_route/results/complete_bundles_{platform}_r8'
    prepared = ROOT/'modules/surface_route/results/native_scene_ARM_r9'
    rows = []
    output = ROOT/f'modules/surface_route/results/export_kernels_{platform}_r10.json'
    assert not output.exists()
    for bundle in sorted(p for p in bundles.iterdir() if p.is_dir()):
        meta = verify_bundle(bundle)
        attributes = prepared/bundle.name/'airway.attributes'
        with tempfile.TemporaryDirectory(prefix='.export_readback_', dir=output.parent) as name:
            folder = Path(name)
            assert folder.resolve().is_relative_to(output.parent.resolve()) and folder.resolve() != output.parent.resolve()
            p, f, a = compact_surface(bundle, attributes)
            (folder/'surfaces').mkdir()
            write_stl(folder/'airway.stl', p, f)
            write_vtp(folder/'surfaces/airway.vtp', p, f, a)
            write_route(bundle, folder)
            row = check_surface(folder, bundle, attributes, vtk=platform == 'Windows')
            bad = folder/'truncated.attributes'
            bad.write_bytes(attributes.read_bytes()[:-16])
            try:
                compact_surface(bundle, bad)
            except ValueError:
                pass
            else:
                raise AssertionError('Truncated attributes accepted')
            rows.append(dict(label=bundle.name, revision=meta['revision'], **row,
                             truncated_attributes_rejected=True))
    assert len(rows) == 8
    write_json(output, dict(status='eight_active_surface_STL_VTP_CSV_exact_readbacks_passed',
        cases=rows, source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in (
            Path(__file__), Path(__file__).with_name('export_scene_r10.py'))}, PL_access=False))
    print('eight export readback cases passed', flush=True)


def full(scene, destination):
    import SimpleITK as sitk
    original = json.loads(scene.read_text())
    bundle = Path(original['complete_surface']['bundle'])
    attributes = Path(original['meshes']['airway']['attributes']['file'])
    report = export_scene(scene, destination, original['input_sha256'])
    row = check_surface(destination, bundle, attributes)
    copied = verify_bundle(destination/'active_scene/bundle', report['active_revision'])
    assert copied['revision'] == original['complete_surface']['revision']
    # Nested report.json files are part of the manifest too.
    actual = {p.relative_to(destination).as_posix():sha(p) for p in destination.rglob('*')
              if p.is_file() and p != destination/'report.json'}
    assert actual == report['files']
    assert report['complete_reports_scope'] == 'original_segmentation_grid_reference_only'
    assert report['active_surface_comparisons_recomputed'] is False
    assert not any((destination/name).exists() for name in (
        'navigation_branches.json','navigation_instrument_profiles.json','navigation_alternative_routes.json'))
    for name, info in report['masks'].items():
        assert sha(destination/info['nifti']) == info['source_sha256']
        a = sitk.ReadImage(str(destination/info['nifti']))
        b = sitk.ReadImage(str(destination/info['nrrd']))
        assert a.GetSize() == b.GetSize()
        for x,y in ((a.GetSpacing(),b.GetSpacing()),(a.GetOrigin(),b.GetOrigin()),(a.GetDirection(),b.GetDirection())):
            np.testing.assert_allclose(x,y,rtol=0,atol=1e-12)
        np.testing.assert_array_equal(sitk.GetArrayViewFromImage(a),sitk.GetArrayViewFromImage(b))
    for digest, target in ((original['input_sha256'], destination), ('0'*64, destination.with_name(destination.name+'_wrong_CT'))):
        try:
            export_scene(scene, target, digest)
        except ValueError:
            pass
        else:
            raise AssertionError('Existing export/wrong CT accepted')
    assert not destination.with_name(destination.name+'_wrong_CT').exists()
    write_json(destination.parent/(destination.name+'_acceptance.json'), dict(
        status='active_complete_scene_export_exact_and_self_contained_passed',
        export=str(destination), report_sha256=sha(destination/'report.json'), active_revision=report['active_revision'],
        file_count=len(report['files']), elapsed_seconds=report['elapsed_seconds'], **row,
        wrong_CT_rejected_before_output=True, existing_export_preserved=True, masks_exact=True,
        original_analysis_explicitly_reference_only=True, PL_access=False))
    print('full active scene export verified', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--platform', choices=['Windows','ARM'])
    p.add_argument('--scene', type=Path)
    p.add_argument('--destination', type=Path)
    a = p.parse_args()
    if a.platform:
        kernels(a.platform)
    else:
        assert a.scene and a.destination
        full(a.scene, a.destination)
