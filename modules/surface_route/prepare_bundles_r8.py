"""Close original CT proof chains and create portable complete R8 scenes."""
from pathlib import Path
import argparse
import json
import sys
from time import perf_counter
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.surface_route.bundle_r8 import build_bundle, arrays, sha, write_json, mesh_digest
from modules.surface_route.original_surface_mesh_r6 import load_bound, EXPECTED


def load_case(name, threshold, platform):
    label = name.removesuffix('_ported')+'_bend_'+str(float(threshold)).replace('.', 'p')
    suffix = 'ARM_r7b' if platform == 'ARM' else 'Windows_r7'
    replan_root = ROOT/f'modules/surface_route/results/original_surface_replan_{suffix}'
    mesh_root = ROOT/f'modules/surface_route/results/original_mesh_indexing_{platform}_r7'
    proof_path = replan_root/'acceptance.json'
    proof = json.loads(proof_path.read_text(encoding='utf-8'))
    if proof['status'] != 'original_fields_PL_mesh_geometry_filtered_routes_and_guidance_preparation_completed':
        raise ValueError('Completed route/guidance preparation required')
    matched = [c for c in proof['cases'] if c['label'] == label]
    if len(matched) != 1:
        raise ValueError('Exactly one verified route case required')
    binding = {proof_path.relative_to(ROOT).as_posix(): sha(proof_path)}
    for relative, wanted in {**proof['source_sha256'], **proof['input_sha256']}.items():
        if sha(ROOT/relative) != wanted:
            raise ValueError('Preparation source/input changed: '+relative)
        binding[relative] = wanted
    for filename, wanted in matched[0]['files_sha256'].items():
        path = replan_root/filename
        if sha(path) != wanted:
            raise ValueError('Route preparation changed: '+filename)
        binding[path.relative_to(ROOT).as_posix()] = wanted
    scalar, binary, offset, info, inputs = load_bound(name)
    del binary, offset
    binding.update({p.relative_to(ROOT).as_posix(): h for p, h in inputs.items()})
    mesh_report = json.loads((mesh_root/name/'report.json').read_text(encoding='utf-8'))
    mesh = arrays(mesh_root/name/'mesh.npz')
    if mesh_report['renderer_scalar_sha256'] != info['renderer_scalar_sha256']:
        raise ValueError('C1 mesh and original renderer scalar differ')
    mesh_proof = dict(mesh_report['scalar_mesh'],
                      renderer_scalar_sha256=mesh_report['renderer_scalar_sha256'],
                      points_faces_sha256=mesh_digest(mesh['points'], mesh['faces']))
    route, camera = [arrays(replan_root/(label+'_'+suffix+'.npz')) for suffix in ('route', 'camera')]
    reports = [json.loads((replan_root/(label+'_'+suffix+'.json')).read_text(encoding='utf-8'))
               for suffix in ('report', 'guidance')]
    targets = arrays(replan_root/(label+'_targets.npz'))
    provenance = dict(input_case=name, input_platform=platform, input_sha256=binding,
                      extraction_backend='retained_actual_PL_C1_words',
                      original_field_sha256=info['original_field_sha256'],
                      topology_words_sha256=mesh_report['source_PL_words_sha256'],
                      current_turn_PL_access=False)
    return dict(scalar=scalar, geometry=info['geometry'], bits=info['bits'],
                points=mesh['points'], faces=mesh['faces'], mesh_proof=mesh_proof,
                route=route, report=reports[0], camera=camera, guidance=reports[1],
                targets={int(k.removeprefix('event_')): v for k, v in targets.items()}, provenance=provenance)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--platform', choices=['Windows', 'ARM'], required=True)
    p.add_argument('--case', choices=list(EXPECTED), action='append')
    p.add_argument('--include-root-only', action='store_true')
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    records = []
    for name in args.case or EXPECTED:
        for threshold in [1.]+([10.] if args.include_root_only else []):
            start = perf_counter()
            data = load_case(name, threshold, args.platform)
            label = name+'_bend_'+str(threshold).replace('.', 'p')
            meta = build_bundle(args.output/label, **data)
            records.append(dict(name=name, label=label, revision=meta['revision'],
                                route_id=meta['route_id'], points=len(data['route']['arc_mm']),
                                scenes=len(meta['scenes']), total_seconds=perf_counter()-start,
                                payload_bytes=sum(x.stat().st_size for x in (args.output/label).iterdir())))
            print(label, 'complete', records[-1]['points'], 'points', flush=True)
            del data
    write_json(args.output/'acceptance.json', dict(
        status='original_scalar_PL_mesh_new_route_camera_guidance_complete_bundles_verified',
        cases=records, platform=args.platform,
        source_sha256={n: sha(ROOT/n) for n in [
            'modules/surface_route/bundle_r8.py', 'modules/surface_route/prepare_bundles_r8.py']},
        new_bitstream=False, PL_access=False, PS_Marching_Cubes_used=False,
        full_UI_activation_and_same_input_C9_board_comparison_pending=True, production_promoted=False))


if __name__ == '__main__':
    main()
