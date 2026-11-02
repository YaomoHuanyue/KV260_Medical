"""Extract original reproduced probability/SDF fields using the accepted PL C1.

No field rebuilding, graph-node positivity gate, mesh repair or PS MC fallback.
Far-negative C9 saturation must leave every zero-crossing edge unchanged.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys
from time import perf_counter
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from modules.surface_route.own_ct_trial import bound_input
from modules.surface_route.audit import MeshRegion
from modules.surface_quality.scalar_mesh import from_pl_words
from modules.reconstruction.fpga.mc_host import crop_mask
from dfx.surface_quality.prepare import pack_scene, unpack_scene

FIELDS = ROOT/'modules/surface_quality/results/own_CT_board_r2'
EXPECTED = {
    'accepted_binary_high_ported': '15b0b5e8bdb45847d67abc4e2d597a195579c9ab8c0eb2a68cd9d80af0f076f0',
    'accepted_binary_ultra_ported': '2a30c57203945fba4bbbb22317d880ba28831fa37244ccdba5a5b59aa4d0fe93',
    'network_probability_high_ported': '14949d26d8d297ed9dd35ffa964b6e90f81a4aef73a58475eabbd29a18c26040',
    'network_probability_ultra_ported': '7c1bc1f9acd0cbadd5d91e4d47249a3430c590a2079906cbb5427aaa50ca828d',
}
SHA = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
SOURCES = [
    'modules/surface_route/original_surface_mesh_r6.py',
    'modules/surface_route/own_ct_trial.py', 'modules/surface_route/audit.py',
    'modules/surface_quality/scalar_mesh.py', 'modules/reconstruction/fpga/mc_host.py',
    'dfx/surface_quality/prepare.py', 'dfx/surface/prepare.py',
    'dfx/medical/runtime_extended.py', 'dfx/medical/host_extended/runtime.hpp',
    'dfx/medical/host_extended/reconstruction_bridge.cpp',
    'dfx/edt_volume/volume_runtime.py',
]


def write(path, value):
    assert not path.exists(), str(path)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')


def load_bound(name):
    archive, report_path = FIELDS/name/'field.npz', FIELDS/name/'report.json'
    report = json.loads(report_path.read_text())
    assert SHA(archive) == EXPECTED[name] == report['files']['field.npz']
    proof_path = FIELDS/'acceptance.json'
    proof = json.loads(proof_path.read_text())
    source, quality = name.removesuffix('_ported').rsplit('_', 1)
    matches = [c for c in proof['cases'] if (c['scalar_source'], c['quality']) == (source, quality)]
    assert len(matches) == 1 and matches[0]['same_original_fields']['INT16_exact']
    assert matches[0]['same_original_fields']['geometry_exact']
    binding = {archive: SHA(archive), report_path: SHA(report_path), proof_path: SHA(proof_path)}
    for relative, digest in proof['source_sha256'].items():
        path = ROOT/relative
        assert SHA(path) == digest, relative
        binding[path] = digest
    for absolute, digest in report['identity']['inputs_sha256'].items():
        path = bound_input(absolute)
        assert SHA(path) == digest, absolute
        binding[path] = digest
    with np.load(archive, allow_pickle=False) as data:
        q = data['sdf_q_zyx']
        assert q.dtype == np.dtype('<i2') and list(q.shape) == report['shape_zyx']
        bits = 5 if quality == 'high' else 6
        assert float(data['scale_mm']) == report['configuration']['quantization_mm'] == 1/(1 << bits)
        geometry = dict(size_xyz=list(q.shape[::-1]), spacing_xyz=data['spacing_xyz'].tolist(),
                        origin_lps_mm=data['origin_xyz'].tolist(), direction=data['direction'].ravel().tolist())
    assert geometry['size_xyz'] == report['output_geometry']['size_xyz']
    assert geometry['spacing_xyz'] == report['output_geometry']['spacing_xyz_mm']
    assert geometry['origin_lps_mm'] == report['output_geometry']['origin_lps_mm']
    assert geometry['direction'] == report['output_geometry']['direction']
    positive = q > 0
    assert int(positive.sum()) == report['positive_voxels_after_quantization']
    floor = -(4 << bits)
    # A C9 far-negative compression must not move any scalar edge used by MC.
    crossing_edges = 0
    for axis in range(3):
        left, right = [slice(None)]*3, [slice(None)]*3
        left[axis], right[axis] = slice(None, -1), slice(1, None)
        a, b = q[tuple(left)], q[tuple(right)]
        changed = positive[tuple(left)] != positive[tuple(right)]
        crossing_edges += int(changed.sum())
        assert np.all(a[changed] >= floor) and np.all(b[changed] >= floor), 'Saturation would move original zero edges'
    scalar = np.ascontiguousarray(np.maximum(q, floor), dtype='<i2')
    np.testing.assert_array_equal(scalar > 0, positive)
    binary, offset = crop_mask(positive)
    metadata = dict(name=name, bits=bits, geometry=geometry, scalar_source=source,
        original_field_sha256=SHA(archive), renderer_scalar_sha256=hashlib.sha256(scalar.tobytes()).hexdigest(),
        original_reference_INT16_and_geometry_exact=True, far_negative_floor_q=floor,
        far_negative_saturation_preserves_all_crossing_edges=True, crossing_edges=crossing_edges,
        positive_voxels=int(positive.sum()), crop_shape_zyx=list(binary.shape), crop_offset_zyx=offset.tolist(),
        source_report=report_path.relative_to(ROOT).as_posix(),
        source_report_sha256=SHA(report_path), source_geometry=report['source_geometry'],
        original_configuration=report['configuration'])
    return scalar, binary, offset, metadata, binding


def preflight():
    closure, cases = {}, []
    for name in EXPECTED:
        scalar, binary, offset, info, binding = load_bound(name)
        blob, stats = pack_scene(scalar, np.zeros(scalar.shape, bool), 6100+info['bits'],
                                 info['geometry'], bits=info['bits'])
        q, selected = unpack_scene(blob)
        np.testing.assert_array_equal(q, scalar)
        assert not selected.any()
        info['C9_scene_capacity'] = stats
        cases.append(info)
        closure.update(binding)
        print(name, 'preflight', binary.shape, 'crossing edges', info['crossing_edges'], flush=True)
        del scalar, binary, q, selected, blob
    return cases, closure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    cases, closure = preflight()
    if args.preflight_only:
        print('Four original field/crop/zero-edge/C9 capacity bindings passed; no PL access', flush=True)
        return
    assert sys.platform == 'linux' and os.geteuid() == 0
    output = HERE/'results/original_surface_mesh_ARM_r6'
    assert not output.exists()
    output.mkdir()
    sys.path.insert(0, str(ROOT/'dfx/medical'))
    sys.path.insert(0, str(ROOT/'dfx/edt_volume'))
    from runtime_extended import Session
    from volume_runtime import VolumeSession
    # Accepted C6 lifecycle closes under isolation before the C1 legacy host
    # takes the lock. Never force its active-RM identity check or reload static.
    with VolumeSession(experimental=False) as session:
        session.return_to_scope()
    records = []
    before = Path.cwd()
    try:
        with Session() as session:
            for expected in cases:
                begin = perf_counter()
                name = expected['name']
                scalar, binary, offset, info, binding = load_bound(name)
                assert all(info[k] == expected[k] for k in info)
                folder = output/name
                folder.mkdir()
                np.save(folder/'renderer_field.npy', scalar, allow_pickle=False)
                binary.tofile(folder/'mask.u8')
                (folder/'dimensions.txt').write_text(' '.join(map(str, binary.shape[::-1]))+'\n')
                trials = []
                for repeat in range(2):
                    raw = folder/f'vertices_{repeat}.u64'
                    trial = session.run('mc', folder, raw, folder/f'mc_{repeat}.json')
                    assert trial['backend'] == 'dfx_pl'
                    assert raw.stat().st_size == trial['triangles']*24
                    if repeat:
                        assert SHA(raw) == SHA(folder/'vertices_0.u64'), 'Repeated PL topology differs'
                    trials.append(trial)
                session.echo()
                session.report(folder/'session.json')
                words = np.fromfile(folder/'vertices_0.u64', '<u8')
                points, faces, mesh = from_pl_words(words, scalar, offset, info['geometry']['spacing_xyz'],
                    info['geometry']['origin_lps_mm'], info['geometry']['direction'])
                np.savez_compressed(folder/'mesh.npz', points=points, faces=faces)
                # Preserve a failed mesh review as evidence; do not repair or
                # hide nonmanifold/interior holes to make navigation usable.
                try:
                    region = MeshRegion(points, faces, info['geometry'])
                    region_review = dict(status='oriented_manifold_with_only_crop_openings', **region.report)
                except ValueError as exc:
                    region_review = dict(status='refused_for_navigation', reason=str(exc))
                for path, digest in binding.items():
                    assert SHA(path) == digest, str(path)
                record = dict(**info, scalar_mesh=mesh, region_review=region_review,
                    PL_topology_repeats_byte_exact=True, MC_trials=trials,
                    full_case_seconds=perf_counter()-begin,
                    default_UI_or_source_route_changed=False, PS_Marching_Cubes_used=False)
                write(folder/'report.json', record)
                record['files_sha256'] = {p.name: SHA(p) for p in folder.iterdir() if p.is_file()}
                records.append(record)
                print(name, 'triangles', len(faces), region_review['status'], flush=True)
                del scalar, binary, words, points, faces
    finally:
        os.chdir(before)
    for path, digest in closure.items():
        assert SHA(path) == digest, str(path)
    result = dict(status='four_original_fields_actual_PL_mesh_extraction_completed_candidate_not_promoted',
        cases=records, input_sha256={p.relative_to(ROOT).as_posix():h for p,h in closure.items()},
        source_sha256={n:SHA(ROOT/n) for n in SOURCES},
        all_mesh_regions_passed=all(c['region_review']['status'] != 'refused_for_navigation' for c in records),
        new_bitstream=False, PS_Marching_Cubes_used=False, production_promoted=False,
        performance_scope='Actual C1 extraction and full preparation; no new PS/PL speed claim',
        geometry_filtered_replan_and_full_UI_pending=True)
    write(output/'acceptance.json', result)
    print(result['status'], 'all regions passed', result['all_mesh_regions_passed'], flush=True)


if __name__ == '__main__':
    main()
