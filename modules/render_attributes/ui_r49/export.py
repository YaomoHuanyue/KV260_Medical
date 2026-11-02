"""Export a selected sampling policy without changing accepted route geometry."""
from pathlib import Path
import argparse, json, os, sys, time, uuid
import numpy as np
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from modules.render_attributes.ui_r49.action import asset, read, sha, verify, write
from modules.surface_export.readback import readback
from modules.surface_export.vtp import write_vtp
from modules.surface_export.export import generation_rgb


def corresponding_values(binding_path, output_points):
    binding = read(binding_path)
    stream = np.memmap(binding['mesh'], '<f4', 'r', shape=(binding['vertices'], 6))
    xyz, first = np.unique(np.asarray(stream[:, :3]), axis=0, return_index=True)
    dtype = np.dtype([('x', '<f4'), ('y', '<f4'), ('z', '<f4')])
    ordered = np.ascontiguousarray(xyz, dtype='<f4').view(dtype).reshape(-1)
    query = np.ascontiguousarray(output_points, dtype='<f4').view(dtype).reshape(-1)
    ids = np.searchsorted(ordered, query)
    if np.any(ids >= len(xyz)) or not np.array_equal(ordered[ids], query):
        raise ValueError('Exported point absent from the displayed PL mesh')
    selected = first[ids]
    old = np.memmap(Path(binding_path).parent/'nearest.attributes', '<f4', 'r', shape=(binding['vertices'], 4))
    legacy = np.memmap(Path(binding_path).parent/'legacy27.attributes', '<f4', 'r', shape=old.shape)
    # Coincident points share display attributes; do not merge mesh IDs or normals.
    inverse = np.searchsorted(ordered, np.ascontiguousarray(stream[:, :3]).view(dtype).reshape(-1))
    for start in range(0, len(stream), 16384):
        for a in [old, legacy]:
            if not np.array_equal(a[start:start+16384], a[first[inverse[start:start+16384]]]):
                raise ValueError('Coincident displayed vertices carry distinct attribute values')
    return np.asarray(old[selected]), np.asarray(legacy[selected])


def refresh_reports(folder, additions):
    """Rebind existing acyclic report hashes after changing our unpublished VTP."""
    reports = {}
    for p in folder.rglob('*.json'):
        value = read(p)
        if isinstance(value, dict) and isinstance(value.get('files'), dict):
            local = all((p.parent / name).is_file() for name in value['files'])
            # Copied segmentation reports name files relative to their original
            # result, not to this export directory. They remain sealed evidence.
            if not local:
                if str(value.get('schema', '')).startswith(('kv260.export.', 'kv260.surface_export.')):
                    raise ValueError('Missing local export-manifest member: '+str(p))
                continue
            reports[p] = value
    done, visiting = set(), set()

    def refresh(path):
        if path in done:
            return
        if path in visiting:
            raise ValueError('Cyclic export report hashes')
        visiting.add(path)
        value = reports[path]
        changed = False
        for name in value['files']:
            p = (path.parent/name).resolve(strict=True)
            if not p.is_relative_to(folder) or p == path:
                raise ValueError('Export report escapes its payload or hashes itself')
            if p in reports:
                refresh(p)
            digest = sha(p)
            changed = changed or value['files'][name] != digest
            value['files'][name] = digest
        for key in list(value):
            if not key.endswith('_report_sha256'):
                continue
            prefix = key.removesuffix('_sha256')
            named = value.get(prefix, prefix+'.json')
            if isinstance(named, str) and (path.parent/named).is_file():
                p = (path.parent/named).resolve()
                if not p.is_relative_to(folder):
                    raise ValueError('Export report hash outside payload')
                if p in reports:
                    refresh(p)
                digest = sha(p)
                changed = changed or value[key] != digest
                value[key] = digest
        if path.name == 'report.json' and path.parent == folder/'surfaces':
            value['attribute_sampling'] = additions
            value['attribute_backend'] = 'PS_bounded_original27_display_with_conservative_reference'
            if 'airway' in value.get('structures', {}):
                value['structures']['airway']['attribute_sampling'] = additions
                value['structures']['airway']['point_arrays'] = additions['point_arrays']
            changed = True
        if changed:
            value['sampling_update'] = dict(policy='explicit_original_27_neighbour_display',
                                            geometry_or_route_recomputed=False)
            temporary = path.with_name(path.name+'.r49')
            write(temporary, value)
            os.replace(temporary, path)
        visiting.remove(path)
        done.add(path)
    for path in reports:
        refresh(path)
    return reports


def export_selected(scene_path, binding_path, destination, minimum_volume=14.):
    begin = time.perf_counter()
    scene_path, binding_path, destination = [Path(p).resolve() for p in [scene_path, binding_path, destination]]
    binding = verify(binding_path, scene_path)
    scene = read(scene_path)
    if (not destination.is_relative_to(ROOT/'ui/exports') or destination.exists()
            or scene['input_sha256'] != binding['input_sha256']):
        raise ValueError('Fresh export output and matching current CT required')
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = destination.parent/(destination.name+'.sampling_pending_'+uuid.uuid4().hex)
    source = Path(scene['result']).resolve()
    if scene.get('complete_surface'):
        from modules.surface_route.export_scene_r21 import export_scene
        report = export_scene(scene_path, stage, binding['input_sha256'], minimum_volume)
    else:
        from modules.report_export.bundle import export_bundle
        import SimpleITK as sitk
        report = export_bundle(source, stage, binding['input_sha256'], minimum_volume,
                               sitk.ReadImage(str(asset(scene_path.parent, scene['input']))))
    # The inherited exporter has finished inside our private unpublished stage.
    # Every unchanged medical output remains there; only display attributes change.
    file = stage/'surfaces/airway.vtp'
    arrays = readback(file)
    before = {k: np.asarray(arrays[k]).copy() for k in ['Points', 'connectivity', 'offsets', 'Normals']}
    nearest, legacy = corresponding_values(binding_path, arrays['Points'])
    point_data = {k: a for k, a in arrays.items() if k not in ['Points', 'connectivity', 'offsets']}
    point_data.update(generation=legacy[:, 0].astype(np.int16), radius_mm=legacy[:, 1],
        network_probability=legacy[:, 2],
        probability_available=np.full(len(legacy), binding['confidence_available'], np.uint8),
        connected_to_root=nearest[:, 3].astype(np.uint8), RGB=generation_rgb(legacy[:, 0], nearest[:, 3]),
        conservative_nearest_radius_mm=nearest[:, 1],
        conservative_nearest_generation=nearest[:, 0].astype(np.int16),
        conservative_nearest_probability=nearest[:, 2])
    temporary = file.with_name('airway.r49.vtp')
    write_vtp(temporary, arrays['Points'], arrays['connectivity'].reshape(-1, 3), point_data)
    checked = readback(temporary)
    for k, value in before.items():
        np.testing.assert_array_equal(checked[k], value)
    for k, value in point_data.items():
        np.testing.assert_array_equal(checked[k], value)
    old_vtp_sha = sha(file)
    os.replace(temporary, file)
    annotation = dict(schema='kv260.export.attribute_sampling.r49', policy='original_clipped_27_radius_winner',
        source_binding=str(binding_path), source_binding_sha256=sha(binding_path),
        confidence_available=binding['confidence_available'], probability_is_not_accuracy=True,
        unavailable_confidence_numeric_default=1., availability_array_authoritative=True,
        reachability_radius_array='conservative_nearest_radius_mm', navigation_geometry_or_constraints_changed=False,
        geometry_normals_triangle_order_unchanged=True, original_nearest_VTP_SHA256=old_vtp_sha,
        current_sampling_VTP_SHA256=sha(file), backend='PS_bounded_preprocessing_and_serialization')
    annotation['point_arrays'] = list(point_data)
    annotation['source_sha256'] = {p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),
        ROOT/'modules/render_attributes/ui_r49/action.py']}
    write(stage/'attribute_sampling.json', annotation)
    reports = refresh_reports(stage, annotation)
    top = read(stage/'report.json')
    top.update(schema='kv260.export.explicit_sampling.r49', attribute_sampling=annotation,
        inherited_export_schema=report['schema'], attribute_binding='attribute_sampling.json',
        attribute_binding_sha256=sha(stage/'attribute_sampling.json'),
        files={p.relative_to(stage).as_posix(): sha(p) for p in stage.rglob('*') if p.is_file() and p != stage/'report.json'},
        sampling_export_seconds=time.perf_counter()-begin,
        production_promoted=False)
    (stage/'report.json').write_text(json.dumps(top, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf8')
    # Reopen every current report reference before atomic publication.
    for p in reports:
        value = read(p)
        for name, digest in value['files'].items():
            if sha(p.parent/name) != digest:
                raise ValueError('Updated export report checksum mismatch')
    verify(binding_path, scene_path)
    os.rename(stage, destination)
    return top


def main():
    from modules.image_import.positive_labels_r1.backend import install_contracts
    install_contracts()
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['export'])
    p.add_argument('--scene', type=Path, required=True)
    p.add_argument('--attribute-binding', type=Path, required=True)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--result', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    p.add_argument('--minimum-candidate-volume', type=float, default=14.)
    args = p.parse_args()
    scene = read(args.scene)
    if Path(scene['input']).resolve() != args.input.resolve() or Path(scene['result']).resolve() != args.result.resolve():
        raise ValueError('Export selected CT/result differs from current scene')
    report = export_selected(args.scene, args.attribute_binding, args.destination, args.minimum_candidate_volume)
    print(json.dumps(dict(event='exported', path=str(args.destination.resolve()), files=len(report['files']),
        schema=report['schema'], minimum_candidate_volume_mm3=report['minimum_candidate_volume_mm3'],
        lesion_catalogue_state=report['lesion_catalogue_state'], complete_reports=report['complete_reports'],
        surface_export_seconds=report['surface_export_seconds'], attribute_sampling=report['attribute_sampling']), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps(dict(event='error', text=str(error)), ensure_ascii=False), flush=True)
        sys.exit(1)
