"""Review retained forest routes and exit guidance on the original PL surfaces.

Off-route nodes outside a revised field never reject the entire scene. Each
edge and the final curve must pass the existing actual-wall/crop/mask review.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
from time import perf_counter
import numpy as np
import SimpleITK as sitk

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from modules.surface_route.original_surface_mesh_r6 import load_bound, SHA, write, EXPECTED
from modules.surface_route.audit import MeshRegion
from modules.surface_route.own_replan_trial_r1 import AtThreads
from modules.surface_route.bend_replan_r3 import checked_replan, validate_stored_audit
from modules.surface_route.curve_guidance_r5 import GuidanceSurfaceBendPlanner
from modules.surface_route.guidance_r5 import ScalarField, build_guidance
from modules.surface_quality.mesh_clearance_native import NativeMeshClearance
from modules.surface_quality.mesh_clearance_batch import BatchedMeshClearance
from modules.navigation.navigation.pipeline import load_prepared, choose_target
from modules.navigation.navigation.camera import poses
from modules.navigation.navigation.guidance import guidance_route_id
from dfx.surface_quality.prepare import pack_scene, unpack_scene

SOURCES = [
    'modules/surface_route/original_surface_replan_r6.py',
    'modules/surface_route/original_surface_mesh_r6.py',
    'modules/surface_route/curve_guidance_r5.py', 'modules/surface_route/guidance_r5.py',
    'modules/surface_route/bend_replan_r3.py', 'modules/surface_route/replan_r1.py',
    'modules/surface_route/refine_r1.py', 'modules/surface_route/audit.py',
    'modules/surface_quality/mesh_clearance_native.py', 'modules/surface_quality/target_mapping.py',
    'modules/surface_quality/mesh_clearance_batch.py',
    'modules/navigation/navigation/pipeline.py', 'modules/navigation/navigation/planner.py',
    'modules/navigation/navigation/centerline.py', 'modules/navigation/navigation/camera.py',
    'modules/navigation/navigation/guidance.py', 'modules/navigation/navigation/lumen.py',
    'modules/navigation/navigation/geometry.py', 'dfx/route_audit_speed/checked_plan.py',
    'dfx/route_audit_speed/protocol.py', 'dfx/surface_quality/prepare.py',
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--native', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    assert not output.exists()
    output.mkdir(parents=True)
    mesh_root = HERE/'results/original_surface_mesh_ARM_r6'
    proof_path = mesh_root/'acceptance.json'
    proof = json.loads(proof_path.read_text())
    assert proof['status'] == 'four_original_fields_actual_PL_mesh_extraction_completed_candidate_not_promoted'
    closure = {proof_path: SHA(proof_path)}
    for name, digest in {**proof['source_sha256'], **proof['input_sha256']}.items():
        assert SHA(ROOT/name) == digest, name
        closure[ROOT/name] = digest
    result = ROOT/'ui/runs/20261004_151324_f601e259'
    nav = result/'navigation'
    source = json.loads((nav/'route.json').read_text())
    c = load_prepared(nav)
    for name in ('centerline.json', 'centerline.npz', 'route.json', 'route.npz'):
        closure[nav/name] = SHA(nav/name)
    nodule = result/'segmentation/nodule_mask.nii.gz'
    assert SHA(nodule) == source['target']['mask_sha256']
    closure[nodule] = SHA(nodule)
    target = choose_target(c, lesion_path=nodule, lesion_index=source['target']['index'])
    assert target.metadata == source['target']
    assert c.metadata['input_sha256'] == SHA(result/'segmentation/airway_mask.nii.gz')
    assert c.metadata['centerline_id'] == hashlib.sha256(c.points_lps_mm.tobytes()+c.edges.tobytes()+str(c.root).encode()).hexdigest()
    image = sitk.ReadImage(str(result/'segmentation/airway_mask.nii.gz'))
    cases = []
    for mesh_case in proof['cases']:
        name = mesh_case['name']
        assert name in EXPECTED
        folder = mesh_root/name
        for filename, digest in mesh_case['files_sha256'].items():
            assert SHA(folder/filename) == digest, str(folder/filename)
            closure[folder/filename] = digest
        if mesh_case['region_review']['status'] == 'refused_for_navigation':
            cases.append(dict(name=name, status='mesh_review_refused_preserved',
                              reason=mesh_case['region_review']['reason']))
            continue
        scalar, binary, offset, info, binding = load_bound(name)
        closure.update(binding)
        saved = np.load(folder/'renderer_field.npy', allow_pickle=False)
        np.testing.assert_array_equal(saved, scalar)
        field = ScalarField(scalar, info['geometry'], info['bits'])
        assert field.sha256 == mesh_case['renderer_scalar_sha256']
        with np.load(folder/'mesh.npz', allow_pickle=False) as archive:
            points, faces = archive['points'], archive['faces']
        region = MeshRegion(points, faces, info['geometry'])
        base = NativeMeshClearance(points, faces) if args.native else BatchedMeshClearance(points, faces)
        oracle = AtThreads(base, 4) if args.native else base
        if args.native:
            native_path = ROOT/'modules/surface_quality/host/build/build.json'
            closure[native_path] = SHA(native_path)
        original_sign = field.sample(c.points_lps_mm)
        original_root = region.root_winding(c.points_lps_mm[c.root])
        for threshold in (0., 1., 10.):
            begin = perf_counter()
            label = name.removesuffix('_ported')+'_bend_'+str(threshold).replace('.', 'p')
            planner = GuidanceSurfaceBendPlanner(c, region, oracle)
            report, route, camera = checked_replan(planner, target,
                scope_diameter_mm=source['scope_diameter_mm'], safety_margin_mm=source['safety_margin_mm'],
                minimum_bend_radius_mm=threshold, forward_window_mm=source['forward_window_mm'])
            validate_stored_audit(route, report)
            for k, v in poses(route['points_lps_mm'], route['arc_mm']).items():
                np.testing.assert_array_equal(camera[k], v)
            guidance, targets = build_guidance(c, route, field, image)
            assert guidance['route_id'] == guidance_route_id(route)
            assert guidance['scalar_sha256'] == field.sha256
            if len(route['points_lps_mm']) > 1:
                assert report['curve_audit']['whole_curve_accepted']
                assert np.all(field.sample(route['points_lps_mm']) > 0)
                if threshold:
                    assert np.all(route['bend_radius_mm']+1e-5 >= threshold)
            else:
                assert not guidance['events'], 'No false forward guide on root-only route'
            all_available = [e for e in guidance['events'] if e['available']]
            assert set(targets) == {e['id'] for e in all_available}
            for event in all_available:
                selected = targets[event['id']]
                assert selected.dtype == np.dtype(bool) and not np.any(selected & (scalar <= 0))
                blob, _ = pack_scene(scalar, selected, 7000+info['bits']*100+event['id'], info['geometry'], bits=info['bits'])
                got, labels = unpack_scene(blob)
                np.testing.assert_array_equal(got, scalar)
                np.testing.assert_array_equal(labels, selected)
                del got, labels, blob
            files = {}
            for suffix, data in [('route', route), ('camera', camera),
                                 ('targets', {'event_'+str(k):v for k,v in targets.items()})]:
                path = output/(label+'_'+suffix+'.npz')
                np.savez_compressed(path, **data)
                files[path.name] = SHA(path)
            for suffix, data in [('report', report), ('guidance', guidance)]:
                path = output/(label+'_'+suffix+'.json')
                write(path, data)
                files[path.name] = SHA(path)
            row = dict(name=name, label=label, status='geometry_filtered_replan_camera_and_scalar_guidance_passed',
                scalar_sha256=field.sha256, minimum_bend_radius_mm=threshold,
                original_graph_nonpositive_points=int(np.count_nonzero(original_sign <= 0)),
                off_route_excluded_nodes_do_not_blanket_reject_scene=True, original_root_winding=original_root,
                route_status=report['status'], route_reason=report['reason'],
                selected_endpoint_id=report['selected_endpoint_id'], point_count=report['point_count'],
                length_mm=report['length_mm'], target_gap_mm=report['final_target_gap_mm'],
                minimum_actual_wall_mm=report['minimum_wall_distance_mm'],
                guidance_events=len(guidance['events']), available_events=len(all_available),
                unavailable_events=[e for e in guidance['events'] if not e['available']],
                route_id=guidance['route_id'], files_sha256=files,
                preparation_seconds=perf_counter()-begin)
            cases.append(row)
            print(label, report['status'], 'points', len(route['arc_mm']), 'cues', len(all_available), flush=True)
        del scalar, binary, saved, points, faces, field, region, base, oracle
    for path, digest in closure.items():
        assert SHA(path) == digest, str(path)
    receipt = dict(status='original_fields_PL_mesh_geometry_filtered_routes_and_guidance_preparation_completed',
        platform=sys.platform, cases=cases,
        input_sha256={p.relative_to(ROOT).as_posix():h for p,h in closure.items()},
        source_sha256={n:SHA(ROOT/n) for n in SOURCES},
        PL_access=False, PS_Marching_Cubes_used=False, new_bitstream=False,
        production_promoted=False, full_UI_and_actual_C9_new_surface_comparison_pending=True)
    write(output/'acceptance.json', receipt)


if __name__ == '__main__':
    main()
