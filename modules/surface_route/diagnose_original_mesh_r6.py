"""Separate raw PL topology failures from quantized zero-endpoint collapse."""
from pathlib import Path
import json
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from modules.surface_route.original_surface_mesh_r6 import SHA, write
from modules.surface_route.audit import MeshRegion
from modules.reconstruction.fpga.mc_host import to_mesh
from modules.surface_route.guidance_r5 import ScalarField


def edges(faces):
    f = np.asarray(faces, np.int64)
    e = np.concatenate((f[:, [0,1]], f[:, [1,2]], f[:, [2,0]]))
    unique, inverse, count = np.unique(np.sort(e, axis=1), axis=0, return_inverse=True, return_counts=True)
    balance = np.bincount(inverse, weights=np.where(e[:,0] < e[:,1], 1, -1))
    bad = np.flatnonzero((count > 2) | ((count == 2) & (balance != 0)))
    stats = dict(triangles=len(f), boundary_edges=int((count == 1).sum()),
        nonmanifold_edges=int((count > 2).sum()), inconsistent_two_face_edges=int(((count == 2) & (balance != 0)).sum()),
        maximum_edge_incidence=int(count.max()), bad_edges_with_nonzero_orientation_balance=int((balance[bad] != 0).sum()))
    return stats, unique[bad], count[bad]


def main():
    folder = HERE/'results/original_surface_mesh_ARM_r6'
    proof = json.loads((folder/'acceptance.json').read_text())
    records, closure = [], {folder/'acceptance.json':SHA(folder/'acceptance.json')}
    for case in proof['cases']:
        path = folder/case['name']
        for name, digest in case['files_sha256'].items():
            assert SHA(path/name) == digest
            closure[path/name] = digest
        scalar = np.load(path/'renderer_field.npy', allow_pickle=False)
        field = ScalarField(scalar, case['geometry'], case['bits'])
        with np.load(path/'mesh.npz', allow_pickle=False) as a:
            points, faces = a['points'], a['faces']
        raw = np.fromfile(path/'vertices_0.u64', '<u8')
        p, f = to_mesh(raw, case['geometry']['spacing_xyz'], case['geometry']['origin_lps_mm'],
                       case['geometry']['direction'], case['crop_offset_zyx'])
        raw_stats, _, _ = edges(f)
        try:
            region = MeshRegion(p, f, case['geometry'])
            raw_region = dict(status='passed', **region.report)
        except ValueError as exc:
            raw_region = dict(status='refused', reason=str(exc))
        scalar_stats, bad, count = edges(faces)
        examples = []
        for ids, incidence in zip(bad[:16], count[:16]):
            endpoint = points[ids]
            examples.append(dict(edge_lps_mm=endpoint.tolist(), incident_faces=int(incidence),
                scalar_samples_mm=field.sample(endpoint).tolist()))
        record = dict(name=case['name'], raw_PL_binary_topology=raw_stats,
            raw_PL_binary_region=raw_region, scalar_relocated_topology=scalar_stats,
            original_zero_area_triangles_removed=case['scalar_mesh']['zero_area_triangles_removed'],
            bad_scalar_edge_examples=examples, existing_route_gate_preserved=True,
            mesh_repaired_or_accepted_here=False)
        records.append(record)
        print(case['name'], 'raw', raw_stats, 'scalar', scalar_stats, flush=True)
    target = HERE/'results/original_mesh_diagnosis_r6.json'
    write(target, dict(status='raw_PL_and_scalar_relocated_topology_failures_separated', cases=records,
        input_sha256={p.relative_to(ROOT).as_posix():h for p,h in closure.items()},
        source_sha256={n:SHA(ROOT/n) for n in (
            'modules/surface_route/diagnose_original_mesh_r6.py', 'modules/surface_route/audit.py',
            'modules/reconstruction/fpga/mc_host.py', 'modules/surface_route/guidance_r5.py')},
        PL_access=False, production_promoted=False, geometry_or_route_changed=False))


if __name__ == '__main__':
    main()
