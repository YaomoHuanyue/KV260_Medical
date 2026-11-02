"""Prepare one complete native Qt scene, with no PL access or automatic swaps.

CT/lung/candidates remain the selected completed case. The C1 airway, its
analysis attributes, new route, actual camera path, HUD and C9 exit packets
share the same immutable bundle revision. Old-route comparisons are omitted.
"""
from pathlib import Path
import argparse
import copy
import json
import os
import shutil
import sys
import tempfile
from time import perf_counter
import numpy as np
import SimpleITK as sitk

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.surface_route.bundle_r8 import arrays,write_json
from modules.surface_route.verification_session_r15 import sha,verify_bundle
from ui.features.analysis import surface_attributes


def asset_path(folder, value, root=ROOT):
    if not isinstance(value, str) or not value:
        raise ValueError('Named scene asset required')
    path = Path(value)
    if not path.is_absolute():
        path = Path(folder)/path
    path = path.resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Missing/outside project scene asset: '+str(path))
    return path


def case_binding(base_path, base, bundle, root=ROOT):
    """Validate selected CT/result, rather than matching only a case name."""
    if base.get('schema') != 'kv260.ui.scene.v1':
        raise ValueError('Native source scene required')
    bound = bundle['identity']['provenance']['input_sha256']
    image = asset_path(base_path.parent, base['input'], root)
    result = Path(base['result']).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError('Source result outside project')
    relative = image.relative_to(root).as_posix()
    if bound.get(relative) != base['input_sha256'] or sha(image) != base['input_sha256']:
        raise ValueError('Complete scene belongs to another CT')
    bindings = {}
    required = ['segmentation/report.json', 'segmentation/airway_mask.nii.gz',
                'segmentation/nodule_mask.nii.gz', 'navigation/centerline.json', 'navigation/centerline.npz']
    if bundle['identity']['provenance']['input_case'].startswith('network_probability_'):
        required += ['segmentation/airway_logits.json', 'segmentation/airway_logits.npy',
                     'segmentation/airway_mask_network.nii.gz']
    for name in required:
        file = result/name
        relative = file.relative_to(root).as_posix()
        if not file.is_file() or bound.get(relative) != sha(file):
            raise ValueError('Complete scene belongs to another/changed result: '+name)
        bindings[relative] = bound[relative]
    pipeline = json.loads((result/'pipeline.json').read_text(encoding='utf-8'))
    if pipeline.get('status') != 'passed' or pipeline.get('input_sha256') != base['input_sha256']:
        raise ValueError('Completed source result of this CT required')
    bindings[(result/'pipeline.json').relative_to(root).as_posix()] = sha(result/'pipeline.json')
    bindings[image.relative_to(root).as_posix()] = sha(image)
    return image, result, bindings


def prepare(base_path, bundle_path, output, expected_revision=None, root=ROOT,quality_path=None):
    begin = perf_counter()
    base_path, bundle_path, output = [Path(p).resolve() for p in (base_path, bundle_path, output)]
    if output.exists() or not output.is_relative_to(root.resolve()):
        raise ValueError('New output directory inside project required')
    bundle = verify_bundle(bundle_path, expected_revision)
    base = json.loads(base_path.read_text(encoding='utf-8'))
    image_path, result, bindings = case_binding(base_path, base, bundle, root)
    report = json.loads((bundle_path/'route.json').read_text(encoding='utf-8'))
    from modules.navigation.navigation.pipeline import load_prepared,choose_target
    c=load_prepared(result/'navigation')
    target=choose_target(c,lesion_path=result/'segmentation/nodule_mask.nii.gz',lesion_index=report['target']['index'])
    if target.metadata!=report['target']:raise ValueError('Changed actual target in complete route')
    from modules.surface_route.quality_validation_r16 import validate_base_assets
    validate_base_assets(base_path,base,image_path,result,root)
    quality_path=Path(quality_path).resolve()
    quality=json.loads(quality_path.read_text(encoding='utf-8'))
    quality_entry=dict(receipt=str(quality_path),receipt_sha256=sha(quality_path),source=quality['source'],tier=quality['tier'])
    for relative,digest in quality['case_files_sha256'].items():
        if sha(root/relative)!=digest:raise ValueError('Changed quality source: '+relative)
        bindings[relative]=digest
    image = sitk.ReadImage(str(image_path))
    geometry = base['geometry']
    if tuple(geometry['size_xyz']) != image.GetSize() or any(
            not np.allclose(a, b, rtol=0, atol=1e-6) for a, b in [
                (geometry['spacing_xyz'], image.GetSpacing()),
                (geometry['origin_lps_mm'], image.GetOrigin()), (geometry['direction'], image.GetDirection())]):
        raise ValueError('Base CT cache/image geometry differs')
    assets = {}
    scene = copy.deepcopy(base)
    for key, size in [('volume', int(np.prod(image.GetSize()))*4),
                      ('masks', int(np.prod(image.GetSize())))]:
        path = asset_path(base_path.parent, base[key], root)
        if path.stat().st_size != size:
            raise ValueError('Truncated CT/mask cache')
        scene[key] = str(path); assets[str(path)] = sha(path)
    for name, item in scene['meshes'].items():
        if name == 'airway':
            continue
        path = asset_path(base_path.parent, item['file'], root)
        if path.stat().st_size != item['vertices']*24:
            raise ValueError('Truncated overview mesh: '+name)
        item['file'] = str(path); assets[str(path)] = sha(path)
        if item.get('attributes'):
            attr = asset_path(base_path.parent, item['attributes']['file'], root)
            if attr.stat().st_size != item['vertices']*16:
                raise ValueError('Truncated overview attributes: '+name)
            item['attributes']['file'] = str(attr); assets[str(attr)] = sha(attr)
    route, camera, mesh = [arrays(bundle_path/f) for f in ('route.npz', 'camera.npz', 'mesh.npz')]
    guide = json.loads((bundle_path/'guidance.json').read_text(encoding='utf-8'))
    hud = json.loads((bundle_path/'hud.json').read_text(encoding='utf-8'))
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.'+output.name+'.', dir=output.parent))
    try:
        stream = bundle_path/'airway.vertices'
        attributes = surface_attributes(result, image, stream, stage/'airway.attributes', base['input_sha256'])
        if not attributes or attributes['vertices'] != bundle['mesh']['vertices']:
            raise ValueError('New mesh requires matching analysis attributes')
        attributes['file'] = str(output/'airway.attributes')
        points = mesh['points']
        scene['meshes']['airway'] = dict(file=str(stream), vertices=bundle['mesh']['vertices'],
            triangles=len(mesh['faces']), original_triangles=len(mesh['faces']), display_only=False,
            clustering_mm=0., source_sha256=bundle['identity']['files_sha256']['mesh.npz'],
            bounds_min=points.min(axis=0).tolist(), bounds_max=points.max(axis=0).tolist(),
            attributes=attributes, topology='PL_C1', scene_revision=bundle['revision'])
        report = copy.deepcopy(report)
        report['branch_guidance'] = guide
        report['complete_scene_revision'] = bundle['revision']
        # Geometry producer's original pending flag is preserved separately.
        # Creating Qt payload is not a physical/UI/PL acceptance claim.
        scene['navigation'] = dict(points=route['points_lps_mm'].tolist(), arc=route['arc_mm'].tolist(),
            radius=route['radius_mm'].tolist(), positions=camera['position_lps_mm'].tolist(),
            forward=camera['forward_lps'].tolist(), up=camera['up_lps'].tolist(), report=report, hud=hud)
        scene['input'] = str(image_path)
        scene['complete_surface'] = dict(schema='kv260.ui.complete_surface.v1',
            bundle=str(bundle_path), revision=bundle['revision'], route_id=bundle['route_id'],
            scalar_sha256=bundle['renderer_scalar_sha256'], source_result=str(result),
            navigation_module='surface_quality', atomic_activation=True, automatic_quality_changes=False,
            new_field_comparisons_available=False,
            pending_operations=['new_field_profile_and_Pareto_recomputation',
                                'native_export_dispatch_for_active_surface'])
        from modules.surface_route.capabilities_r14c import capabilities
        scene['available_structures'],scene['structure_foreground_voxels']=capabilities(np.fromfile(scene['masks'],np.uint8))
        scene['complete_surface']['quality']=quality_entry
        scene['complete_surface']['pending_operations']=['active_batch_video_recovery_dispatch']
        write_json(stage/'scene.json', scene)
        receipt = dict(schema='kv260.ui.complete_surface.prepared.v1',
            status='prepared_complete_native_scene_no_PL_access', base_scene=str(base_path),
            base_scene_sha256=sha(base_path), bundle=str(bundle_path), bundle_sha256=sha(bundle_path/'scene.json'),
            revision=bundle['revision'], input_sha256=base['input_sha256'], case_files_sha256=bindings,
            retained_assets_sha256=assets, airway_vertices_sha256=sha(stream),
            output_sha256={f.name:sha(f) for f in stage.iterdir()}, total_seconds=perf_counter()-begin,
            new_bitstream=False, PL_access=False, production_promoted=False,active_quality=quality_entry)
        write_json(stage/'prepared.json', receipt)
        os.rename(stage, output)
        return receipt
    finally:
        if stage.exists():
            if not stage.resolve().is_relative_to(output.parent.resolve()) or stage.resolve()==output.parent.resolve():
                raise RuntimeError('Private staging path escaped its parent')
            shutil.rmtree(stage)  # Private, verified staging child created above.


def verify_prepared(path, root=ROOT):
    path = Path(path).resolve()
    receipt = json.loads((path.parent/'prepared.json').read_text(encoding='utf-8'))
    for name, expected in receipt['output_sha256'].items():
        if name not in ('scene.json', 'airway.attributes') or sha(path.parent/name) != expected:
            raise ValueError('Changed prepared Qt payload')
    scene = json.loads(path.read_text(encoding='utf-8'))
    complete = scene['complete_surface']
    if (receipt['revision'] != complete['revision'] or receipt['input_sha256'] != scene['input_sha256']
            or sha(Path(complete['bundle'])/'scene.json') != receipt['bundle_sha256']
            or complete['source_result'] != scene['result']):
        raise ValueError('Mixed complete Qt scene')
    verify_bundle(complete['bundle'], complete['revision'])
    for file, expected in receipt['case_files_sha256'].items():
        if sha(root/file) != expected:
            raise ValueError('Changed original case: '+file)
    for file, expected in receipt['retained_assets_sha256'].items():
        if sha(asset_path(path.parent, file, root)) != expected:
            raise ValueError('Changed retained CT/overview asset')
    if sha(Path(complete['bundle'])/'airway.vertices') != receipt['airway_vertices_sha256']:
        raise ValueError('Changed complete airway stream')
    return scene


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--revision')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    if args.verify:
        scene = verify_prepared(args.verify)
        print(json.dumps(dict(event='verified', scene=str(args.verify),
                              revision=scene['complete_surface']['revision'], PL_access=False)))
    else:
        if not all((args.base, args.bundle, args.output)):
            parser.error('--base, --bundle and --output required')
        receipt = prepare(args.base, args.bundle, args.output, args.revision)
        print(json.dumps(dict(event='prepared', scene=str(args.output/'scene.json'), **receipt)))


if __name__ == '__main__':
    main()
