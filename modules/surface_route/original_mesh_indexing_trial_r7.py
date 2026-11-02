"""Check index-only scalar-zero handling against retained actual PL outputs."""
from pathlib import Path
import argparse
import json
import sys
from time import perf_counter
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from modules.surface_route.original_surface_mesh_r6 import SHA, write
from modules.surface_route.audit import MeshRegion
from modules.surface_quality.scalar_mesh_r7 import from_pl_words


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert not output.exists()
    output.mkdir(parents=True)
    old = HERE/'results/original_surface_mesh_ARM_r6'
    proof_path = old/'acceptance.json'
    proof = json.loads(proof_path.read_text())
    closure = {proof_path:SHA(proof_path)}
    for name, digest in {**proof['source_sha256'], **proof['input_sha256']}.items():
        assert SHA(ROOT/name) == digest, name
        closure[ROOT/name] = digest
    records = []
    for case in proof['cases']:
        begin = perf_counter()
        source = old/case['name']
        for name, digest in case['files_sha256'].items():
            assert SHA(source/name) == digest, name
            closure[source/name] = digest
        folder = output/case['name']
        folder.mkdir()
        scalar = np.load(source/'renderer_field.npy', allow_pickle=False)
        raw = np.fromfile(source/'vertices_0.u64', '<u8')
        with np.load(source/'mesh.npz', allow_pickle=False) as a:
            old_triangles = a['points'][a['faces']]
        geometry = case['geometry']
        try:
            points, faces, audit = from_pl_words(raw, scalar, np.asarray(case['crop_offset_zyx']),
                geometry['spacing_xyz'], geometry['origin_lps_mm'], geometry['direction'])
            np.testing.assert_array_equal(points[faces], old_triangles)
            assert audit['triangles'] == case['scalar_mesh']['triangles']
            assert audit['zero_area_triangles_removed'] == case['scalar_mesh']['zero_area_triangles_removed']
            region = MeshRegion(points, faces, geometry)
            np.savez_compressed(folder/'mesh.npz', points=points, faces=faces)
            record = dict(name=case['name'], status='passed_exact_original_geometry_and_unchanged_region_gate',
                bits=case['bits'], geometry=geometry, renderer_scalar_sha256=case['renderer_scalar_sha256'],
                scalar_mesh=audit, region_review=region.report,
                retained_ordered_triangles_byte_exact=True, original_scalar_unchanged=True,
                source_PL_words_sha256=SHA(source/'vertices_0.u64'),
                topology_only_backend='retained_actual_PL_C1_words_no_reextraction',
                PL_access=False, PS_Marching_Cubes_used=False, seconds=perf_counter()-begin)
        except ValueError as exc:
            record = dict(name=case['name'], status='refused_without_geometry_or_gate_change', reason=str(exc))
        write(folder/'report.json', record)
        record['files_sha256'] = {p.name:SHA(p) for p in folder.iterdir() if p.is_file()}
        records.append(record)
        print(case['name'], record['status'], record.get('reason', ''), flush=True)
    for path, digest in closure.items():
        assert SHA(path) == digest, str(path)
    result = dict(status='four_original_PL_scalar_surfaces_indexing_trial_completed',
        cases=records, platform=sys.platform,
        all_four_passed=all(c['status'] == 'passed_exact_original_geometry_and_unchanged_region_gate' for c in records),
        source_sha256={n:SHA(ROOT/n) for n in (
            'modules/surface_route/original_mesh_indexing_trial_r7.py',
            'modules/surface_route/audit.py', 'modules/surface_quality/scalar_mesh_r7.py',
            'modules/surface_quality/scalar_mesh_indexing_r7.py', 'modules/surface_quality/scalar_mesh_derivation_r7.json')},
        input_sha256={p.relative_to(ROOT).as_posix():h for p,h in closure.items()},
        PL_access=False, new_bitstream=False, production_promoted=False,
        original_field_route_and_default_UI_changed=False, geometry_filtered_replan_pending=True)
    write(output/'acceptance.json', result)
    print('All four passed:', result['all_four_passed'], flush=True)


if __name__ == '__main__':
    main()
