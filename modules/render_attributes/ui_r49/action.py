"""Explicit, immutable display-attribute action; geometry and routing stay fixed."""
from pathlib import Path
import argparse, fcntl, hashlib, json, os, sys, time
import numpy as np
import SimpleITK as sitk

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ui.features.analysis import surface_attributes
from modules.render_attributes.neighbourhood_r48.sampler import NeighbourhoodSampler


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with Path(path).open('x', encoding='utf8') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)


def asset(folder, name):
    if not isinstance(name, str) or not name:
        raise ValueError('Named project asset required')
    path = (Path(folder) / name).resolve(strict=True)
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError('Attribute input outside project')
    return path


def prepare(scene_path, output, emit=lambda *a, **k: None):
    begin = time.perf_counter()
    scene_path = asset(ROOT, str(Path(scene_path).resolve()))
    scene = read(scene_path)
    output = Path(output).resolve()
    if output.exists() or not output.is_relative_to(ROOT / 'ui/cache'):
        raise ValueError('Fresh attribute output inside UI cache required')
    if scene.get('schema') != 'kv260.ui.scene.v1':
        raise ValueError('Prepared medical scene required')
    ct = asset(scene_path.parent, scene['input'])
    if sha(ct) != scene['input_sha256']:
        raise ValueError('Attribute scene declares a different CT')
    result = Path(scene['result']).resolve(strict=True)
    if not result.is_relative_to(ROOT):
        raise ValueError('Source result outside project')
    item = scene.get('meshes', {}).get('airway', {})
    if not item.get('attributes'):
        raise ValueError('Airway mesh and identified attributes required')
    mesh = asset(scene_path.parent, item['file'])
    nearest_input = asset(scene_path.parent, item['attributes']['file'])
    n = item['vertices']
    if type(n) is not int or n < 1 or mesh.stat().st_size != n * 24 or nearest_input.stat().st_size != n * 16:
        raise ValueError('Truncated displayed attribute or triangle stream')
    image = sitk.ReadImage(str(result / 'segmentation/airway_mask.nii.gz'))
    header = sitk.ImageFileReader()
    header.SetFileName(str(ct))
    header.ReadImageInformation()
    if header.GetSize() != image.GetSize() or any(not np.allclose(a, b, atol=1e-6, rtol=0)
        for a, b in [(header.GetSpacing(), image.GetSpacing()), (header.GetOrigin(), image.GetOrigin()),
                     (header.GetDirection(), image.GetDirection())]):
        raise ValueError('Airway attribute mask belongs to another CT geometry')
    geometry = scene['geometry']
    if list(image.GetSize()) != geometry['size_xyz'] or any(
        not np.allclose(a, b, atol=1e-6, rtol=0) for a, b in [
            (image.GetSpacing(), geometry['spacing_xyz']), (image.GetOrigin(), geometry['origin_lps_mm']),
            (image.GetDirection(), geometry['direction'])]):
        raise ValueError('Attribute mask and displayed CT geometry differ')
    names = ['segmentation/airway_mask.nii.gz', 'navigation/centerline.npz',
        'navigation/centerline.json', 'navigation/branches.json', 'navigation/anatomical_generations.npz',
        'navigation/anatomical_generations.json', 'segmentation/airway_logits.json', 'segmentation/airway_logits.npy']
    sources = {str(p): sha(p) for p in [scene_path, ct, mesh, nearest_input]}
    for name in names:
        if (result / name).is_file():
            sources[str(result / name)] = sha(result / name)
    output.mkdir(parents=True, exist_ok=False)
    emit('progress', text='正在校验当前气道属性；模型和导航保持不变')
    meta = surface_attributes(result, image, mesh, output / 'nearest.attributes', scene['input_sha256'])
    if not meta:
        raise ValueError('Identified airway attributes unavailable')
    nearest = np.memmap(output / 'nearest.attributes', '<f4', 'r', shape=(n, 4))
    shown = np.memmap(nearest_input, '<f4', 'r', shape=(n, 4))
    for start in range(0, n, 16384):
        if not np.array_equal(nearest[start:start+16384], shown[start:start+16384]):
            raise ValueError('Displayed attributes differ from the bound source result')
    with np.load(result / 'navigation/centerline.npz', allow_pickle=False) as data:
        points, radii = data['points_lps_mm'], data['radii_mm']
    if meta['anatomical_generation'] is not None:
        with np.load(result / 'navigation/anatomical_generations.npz', allow_pickle=False) as data:
            active, generation = data['active'], data['generation']
    else:
        generation = np.full(len(points), -1, np.int16)
        for branch in sorted(meta['branches'], key=lambda b: b.get('generation') if b.get('generation') is not None else 10**9, reverse=True):
            if branch.get('generation') is not None:
                generation[np.asarray(branch['point_ids'], np.int64)] = branch['generation']
        active = generation >= 0
    if not np.any(active) or np.any(generation[active] > 255):
        raise ValueError('Original neighbourhood mode requires available uint8 generation labels')
    options = {}
    if meta['confidence_available']:
        lm = read(result / 'segmentation/airway_logits.json')
        options = dict(logits=np.load(result / 'segmentation' / lm['file'], mmap_mode='r', allow_pickle=False),
                       logit_scale=lm['scale'], logit_zero=lm['zero'])
    sampler = NeighbourhoodSampler(sitk.GetArrayViewFromImage(image), image.GetSpacing(), image.GetOrigin(),
        image.GetDirection(), points, radii, points[active], generation[active], **options)
    stream = np.memmap(mesh, '<f4', 'r', shape=(n, 6))
    emit('progress', text='正在按批生成原版27邻域着色；可达性继续使用保守半径')
    with (output / 'legacy27.attributes').open('xb') as f:
        for start, g, r, c in sampler.iter_samples(stream[:, :3], batch_size=4096):
            np.column_stack((g, r, c, nearest[start:start+len(g), 3])).astype('<f4').tofile(f)
    for name, digest in sources.items():
        if sha(name) != digest:
            raise ValueError('Source changed during attribute preparation: ' + name)
    receipt = dict(schema='kv260.attribute_sampling.r49', status='completed', scene=str(scene_path),
        scene_sha256=sources[str(scene_path)], input_sha256=scene['input_sha256'], result=str(result),
        mesh=str(mesh), mesh_sha256=sources[str(mesh)], vertices=n,
        files={name: sha(output / name) for name in ['nearest.attributes', 'legacy27.attributes']},
        source_files_sha256=sources, confidence_available=meta['confidence_available'],
        confidence_note=meta['confidence_note'], missing_confidence_legacy_numeric_default=1.,
        generation_kind=meta['generation_kind'], sampler=sampler.last_stats,
        display_sampling='original_radius_winner_clipped_27', reachability_sampling='unchanged_nearest_conservative',
        navigation_geometry_or_constraints_changed=False, PL_geometry_changed=False,
        backend='explicit_PS_bounded_attribute_preparation', PL_accessed=False,
        source_sha256={str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__),
            ROOT / 'ui/features/analysis.py', ROOT / 'modules/render_attributes/neighbourhood_r48/sampler.py']},
        elapsed_seconds=time.perf_counter()-begin)
    write(output / 'binding.json', receipt)
    verify(output / 'binding.json', scene_path)
    return output / 'binding.json'


def verify(binding_path, expected_scene):
    path = asset(ROOT, str(Path(binding_path).resolve()))
    value = read(path)
    if (value.get('schema') != 'kv260.attribute_sampling.r49' or value.get('status') != 'completed'
            or Path(value['scene']) != Path(expected_scene).resolve()
            or value['navigation_geometry_or_constraints_changed'] is not False
            or value['PL_geometry_changed'] is not False):
        raise ValueError('Attribute binding belongs to another displayed scene')
    scene = read(expected_scene)
    mesh = asset(Path(expected_scene).parent, scene['meshes']['airway']['file'])
    if (value['scene_sha256'] != value['source_files_sha256'].get(str(Path(expected_scene).resolve()))
            or value['mesh_sha256'] != value['source_files_sha256'].get(str(mesh))
            or value['mesh'] != str(mesh) or value['vertices'] != scene['meshes']['airway']['vertices']
            or type(value['vertices']) is not int or value['input_sha256'] != scene['input_sha256']
            or Path(value['result']) != Path(scene['result']).resolve()
            or type(value['confidence_available']) is not bool
            or value['confidence_available'] != scene['meshes']['airway']['attributes']['confidence_available']
            or value['display_sampling'] != 'original_radius_winner_clipped_27'
            or value['reachability_sampling'] != 'unchanged_nearest_conservative'):
        raise ValueError('Inconsistent displayed attribute identity or policy')
    for name, digest in value['source_files_sha256'].items():
        if sha(asset(ROOT, name)) != digest:
            raise ValueError('Changed attribute source: ' + name)
    for name, digest in value['source_sha256'].items():
        if sha(asset(ROOT, name)) != digest:
            raise ValueError('Changed attribute producer: ' + name)
    if set(value['files']) != {'nearest.attributes', 'legacy27.attributes'}:
        raise ValueError('Unexpected attribute outputs')
    for name, digest in value['files'].items():
        p = asset(path.parent, name)
        if p.parent != path.parent or sha(p) != digest or p.stat().st_size != value['vertices'] * 16:
            raise ValueError('Changed/truncated attribute output')
    return value


def emit(event, **kwargs):
    print(json.dumps(dict(event=event, **kwargs), ensure_ascii=False, allow_nan=False), flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--scene', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    args = p.parse_args()
    os.environ.setdefault('ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS', '2')
    with (ROOT / 'ui/runs/.runner.lock').open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = prepare(args.scene, args.destination, emit)
        emit('attributes_ready', binding=str(path), binding_sha256=sha(path), **read(path))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        emit('error', text=str(error))
        sys.exit(1)
