"""Cross-check independent Windows and ARM replans on actual PL C1 meshes."""
from pathlib import Path
import hashlib
import json
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SHA = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def verify_meshes():
    proofs = {}
    for platform in ('Windows', 'ARM'):
        folder = HERE/f'results/original_mesh_indexing_{platform}_r7'
        proof = json.loads((folder/'acceptance.json').read_text())
        assert proof['all_four_passed'] and len(proof['cases']) == 4
        for name, digest in {**proof['source_sha256'], **proof['input_sha256']}.items():
            assert SHA(ROOT/name) == digest, name
        for case in proof['cases']:
            assert case['retained_ordered_triangles_byte_exact'] and case['original_scalar_unchanged']
            assert case['scalar_mesh']['scalar_zero_indexing']['all_retained_vertex_links_cycles_or_open_fans']
            for name, digest in case['files_sha256'].items():
                assert SHA(folder/case['name']/name) == digest, name
        unit_path = HERE/f'results/original_mesh_indexing_unit_{platform}_r7.json'
        unit = json.loads(unit_path.read_text())
        assert len(unit['tests']) == 6 and unit['status'] == 'six_coincident_fan_vertex_link_and_negative_indexing_tests_passed'
        for name, digest in unit['source_sha256'].items():
            assert SHA(ROOT/name) == digest, name
        proofs[platform] = proof
    for a, b in zip(proofs['Windows']['cases'], proofs['ARM']['cases']):
        assert a['name'] == b['name'] and a['renderer_scalar_sha256'] == b['renderer_scalar_sha256']
        x = np.load(HERE/'results/original_mesh_indexing_Windows_r7'/a['name']/'mesh.npz', allow_pickle=False)
        y = np.load(HERE/'results/original_mesh_indexing_ARM_r7'/a['name']/'mesh.npz', allow_pickle=False)
        for key in ('points', 'faces'):
            np.testing.assert_array_equal(x[key], y[key])
        assert a['scalar_mesh']['scalar_zero_indexing'] == b['scalar_mesh']['scalar_zero_indexing']
    return dict(all_four_scalar_mesh_points_and_indices_byte_exact=True, six_unit_tests_each_platform=True,
                original_field_and_ordered_PL_triangles_unchanged=True,
                evidence_sha256={k:SHA(HERE/f'results/original_mesh_indexing_{k}_r7/acceptance.json') for k in proofs})


def main():
    mesh_proof = verify_meshes()
    folders = dict(Windows=HERE/'results/original_surface_replan_Windows_r7', ARM=HERE/'results/original_surface_replan_ARM_r7b')
    proofs = {k:json.loads((p/'acceptance.json').read_text()) for k,p in folders.items()}
    for platform, proof in proofs.items():
        for rel, digest in {**proof['input_sha256'], **proof['source_sha256']}.items():
            assert SHA(ROOT/rel) == digest, rel
        for case in proof['cases']:
            for name, digest in case.get('files_sha256', {}).items():
                assert SHA(folders[platform]/name) == digest, name
    assert len(proofs['Windows']['cases']) == len(proofs['ARM']['cases'])
    checked = []
    for a, b in zip(proofs['Windows']['cases'], proofs['ARM']['cases']):
        assert a['name'] == b['name'] and a['status'] == b['status']
        if a['status'] == 'mesh_review_refused_preserved':
            assert a['reason'] == b['reason']
            checked.append(dict(name=a['name'], same_mesh_refusal_retained=True))
            continue
        for key in ('label', 'scalar_sha256', 'minimum_bend_radius_mm',
                    'original_graph_nonpositive_points', 'route_status', 'route_reason',
                    'selected_endpoint_id', 'point_count', 'guidance_events', 'available_events'):
            assert a[key] == b[key], (a['name'], key)
        for suffix in ('route', 'camera', 'targets'):
            x = dict(np.load(folders['Windows']/(a['label']+'_'+suffix+'.npz'), allow_pickle=False))
            y = dict(np.load(folders['ARM']/(b['label']+'_'+suffix+'.npz'), allow_pickle=False))
            assert x.keys() == y.keys()
            for key in x:
                if x[key].dtype.kind in 'biu':
                    np.testing.assert_array_equal(x[key], y[key])
                else:
                    np.testing.assert_allclose(x[key], y[key], rtol=0, atol=1e-10)
        guides = [json.loads((folders[k]/(a['label']+'_guidance.json')).read_text()) for k in folders]
        assert len(guides[0]['events']) == len(guides[1]['events'])
        for e, f in zip(guides[0]['events'], guides[1]['events']):
            for key in ('id', 'available', 'junction_point_ids', 'selected_branch_id', 'selected_exit_point_id'):
                assert e[key] == f[key]
            if not e['available']:
                assert e['reason'] == f['reason']
                continue
            assert e['target_voxels'] == f['target_voxels']
            for key in ('junction_arc_mm', 'exit_arc_mm', 'marker_arc_mm', 'marker_lps_mm', 'show_from_mm', 'hide_after_mm'):
                np.testing.assert_allclose(e[key], f[key], rtol=0, atol=1e-9)
        checked.append(dict(label=a['label'], all_route_audit_and_camera_arrays_match=True,
                            all_scalar_target_labels_exact=True, selected_branches_and_refusals_match=True))
    target = HERE/'results/original_surface_cross_platform_r7b.json'
    assert not target.exists()
    receipt = dict(status='original_PL_surfaces_independent_Windows_ARM_routes_cameras_and_guidance_match',
        cases=checked, mesh_indexing=mesh_proof, evidence_sha256={k:SHA(p/'acceptance.json') for k,p in folders.items()},
        source_sha256=SHA(Path(__file__)), PL_access=False, production_promoted=False)
    target.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(receipt['status'])


if __name__ == '__main__':
    main()
