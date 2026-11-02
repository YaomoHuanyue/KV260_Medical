"""Own-CT revised curves, selected exits, scalar labels and renderer fixtures."""
from pathlib import Path
import argparse, hashlib, json, sys
from time import perf_counter
import numpy as np
import SimpleITK as sitk

HERE=Path(__file__).resolve().parent
SYSTEM=HERE.parents[1]
sys.path.insert(0,str(SYSTEM))
from modules.surface_route.own_ct_trial import scene_binding,bound_input,KEYS,SHA
from modules.surface_route.audit import MeshRegion
from modules.surface_route.own_replan_trial_r1 import AtThreads
from modules.surface_route.bend_replan_r3 import checked_replan,validate_stored_audit
from modules.surface_route.curve_guidance_r5 import GuidanceSurfaceBendPlanner
from modules.surface_route.guidance_r5 import ScalarField,build_guidance
from modules.surface_quality.mesh_clearance_batch import BatchedMeshClearance
from modules.navigation.navigation.pipeline import load_prepared,choose_target
from modules.navigation.navigation.guidance import branch_guidance,guidance_route_id
from modules.navigation.navigation.camera import poses,pose_at
from dfx.surface_quality.prepare import unpack_scene,pack_scene,normal_matrix
import dfx.surface.prepare as reference


def write(path,value):
    assert not path.exists()
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--native',action='store_true');args=parser.parse_args()
    output=args.output.resolve();assert not output.exists();output.mkdir(parents=True)
    baseline=HERE/('results/curve_own_CT_ARM_r4' if sys.platform=='linux' else 'results/curve_own_CT_Windows_r4')
    old_proof=json.loads((baseline/'acceptance.json').read_text())
    scenarios=[];fixtures=[];closure={baseline/'acceptance.json':SHA(baseline/'acceptance.json')}
    for scenario in old_proof['scenarios']:
        for name,digest in scenario['files_sha256'].items():
            assert SHA(baseline/name)==digest,name
    for key in KEYS:
        cache=SYSTEM/'dfx/surface_quality/ui_cache_r1'/key
        scene,binding=scene_binding(cache);result=bound_input(scene['identity']['result']);nav=result/'navigation'
        source=json.loads((nav/'route.json').read_text());c=load_prepared(nav)
        nodule=result/'segmentation/nodule_mask.nii.gz'
        assert SHA(nodule)==source['target']['mask_sha256']
        for path in (nav/'centerline.json',nodule):binding[path]=SHA(path)
        target=choose_target(c,lesion_path=nodule,lesion_index=source['target']['index'])
        assert target.metadata==source['target']
        image=sitk.ReadImage(str(result/'segmentation/airway_mask.nii.gz'))
        bits=scene['identity']['bits'];tier='Q'+str(bits)
        scalar_file=SYSTEM/f'dfx/surface_quality/fixtures/own_CT_native_support_{tier}.scene.bin'
        fixture_manifest=SYSTEM/'dfx/surface_quality/fixtures/manifest.json'
        binding[scalar_file]=SHA(scalar_file);binding[fixture_manifest]=SHA(fixture_manifest)
        q,_=unpack_scene(scalar_file.read_bytes())
        field=ScalarField(q,scene['geometry'],bits)
        assert field.sha256==scene['renderer_scalar_sha256']==scene['mesh']['scalar_sha256']
        mesh=dict(np.load(cache/'mesh.npz',allow_pickle=False))
        region=MeshRegion(mesh['points'],mesh['faces'],scene['geometry'])
        if args.native:
            from modules.surface_quality.mesh_clearance_native import NativeMeshClearance
            oracle=AtThreads(NativeMeshClearance(mesh['points'],mesh['faces']),4)
        else:
            oracle=BatchedMeshClearance(mesh['points'],mesh['faces'])
        for threshold in (0.,.05,1.,10.):
            label=tier+'_bend_'+str(threshold).replace('.','p')
            planner=GuidanceSurfaceBendPlanner(c,region,oracle)
            start=perf_counter()
            report,route,camera=checked_replan(planner,target,
                scope_diameter_mm=source['scope_diameter_mm'],safety_margin_mm=source['safety_margin_mm'],
                minimum_bend_radius_mm=threshold,forward_window_mm=source['forward_window_mm'])
            replan_time=perf_counter()-start
            validate_stored_audit(route,report)
            original_route=dict(np.load(baseline/(label+'_route.npz'),allow_pickle=False))
            original_camera=dict(np.load(baseline/(label+'_camera.npz'),allow_pickle=False))
            for name,values in original_route.items():np.testing.assert_array_equal(route[name],values)
            for name,values in original_camera.items():np.testing.assert_array_equal(camera[name],values)
            for name,values in poses(route['points_lps_mm'],route['arc_mm']).items():
                np.testing.assert_array_equal(camera[name],values)
            start=perf_counter();guidance,targets=build_guidance(c,route,field,image)
            guidance_time=perf_counter()-start
            old_guidance=branch_guidance(c,original_route)
            expected_events=0 if threshold==10. else 3
            assert len(guidance['events'])==expected_events and guidance.get('unavailable_events',0)==0
            assert guidance['route_id']==guidance_route_id(route)
            if expected_events:
                assert [e['junction_point_ids'] for e in guidance['events']]==[[822],[789],[500]]
                assert [e['selected_branch_id'] for e in guidance['events']]==[80,51,52]
                for event in guidance['events']:
                    assert 0<=event['show_from_mm']<=event['junction_arc_mm']<event['marker_arc_mm']<=route['arc_mm'][-1]
                    assert event['hide_after_mm']<event['marker_arc_mm']
                    assert not np.any(targets[event['id']]&(q<=0))
                    if event['aperture']:
                        assert event['aperture']['scalar_sha256']==field.sha256
                        assert np.all(field.sample(np.asarray(event['aperture']['sample_points_lps_mm']))>0)
            files={}
            for suffix,data in [('route',route),('camera',camera),('targets',{'event_'+str(i):v for i,v in targets.items()})]:
                path=output/(label+'_'+suffix+'.npz');np.savez_compressed(path,**data);files[path.name]=SHA(path)
            for suffix,data in [('report',report),('guidance',guidance)]:
                path=output/(label+'_'+suffix+'.json');write(path,data);files[path.name]=SHA(path)
            for name in ('route','camera'):
                path=baseline/(label+'_'+name+'.npz');binding[path]=SHA(path)
            row=dict(label=label,bits=bits,minimum_bend_radius_mm=threshold,
                route_id=guidance['route_id'],scalar_sha256=field.sha256,
                R4_all_route_and_audit_arrays_and_camera_byte_exact=True,
                old_guidance_events=len(old_guidance['events']),new_guidance_events=len(guidance['events']),
                all_events_available=True,files_sha256=files,
                full_fresh_replan_seconds=replan_time,guidance_and_label_preparation_seconds=guidance_time,
                guidance_preparation_runs_once_not_per_display_frame=True)
            scenarios.append(row)
            if threshold==1.:
                directory=output/'render_cases';directory.mkdir(exist_ok=True)
                reference.OUTSIDE_Q5=-(4<<bits)
                for event in guidance['events']:
                    name=label+'_event_'+str(event['id']);token=5000+bits*100+event['id']
                    blob,stats=pack_scene(q,targets[event['id']],token,scene['geometry'],bits=bits)
                    scalar,selected=unpack_scene(blob)
                    np.testing.assert_array_equal(scalar,q);np.testing.assert_array_equal(selected,targets[event['id']])
                    pose=pose_at(camera,route['arc_mm'],max(0.,event['junction_arc_mm']-4))
                    request,_=reference.frame_parameters(np.array(pose['position_lps_mm']),
                        np.array(pose['forward_lps']),np.array(pose['up_lps']),scene['geometry'],np.zeros(3),16,7,token+1000)
                    pixels=reference.reference(q,selected,request,normal_matrix(scene['geometry'],bits))
                    neutral=reference.reference(q,np.zeros_like(selected),request,normal_matrix(scene['geometry'],bits))
                    np.testing.assert_array_equal(pixels&np.uint64(0xffffffff0000ffff),neutral&np.uint64(0xffffffff0000ffff))
                    payloads={'scene.bin':blob,'request.bin':request.tobytes(),'expected.bin':pixels.tobytes()}
                    for suffix,data in payloads.items():(directory/(name+'.'+suffix)).write_bytes(data)
                    fixture=dict(name=name,event_id=event['id'],selected_branch_id=event['selected_branch_id'],
                        route_id=guidance['route_id'],scalar_sha256=field.sha256,bits=bits,geometry=scene['geometry'],
                        camera_pose=pose,pose_arc_is_revised_route=True,**stats,
                        selected_pixels=int(np.count_nonzero((pixels>>16)&255)),
                        outline_pixels=int(np.count_nonzero((pixels>>24)&255)),
                        all_scalar_depth_and_normals_unchanged_by_labels=True,
                        files_sha256={name+'.'+suffix:SHA(directory/(name+'.'+suffix)) for suffix in payloads})
                    fixtures.append(fixture)
            print(label,'old/new cues',len(old_guidance['events']),len(guidance['events']),
                'guidance seconds',round(guidance_time,6),flush=True)
        for path,digest in binding.items():assert SHA(path)==digest,str(path)
        closure.update(binding)
    sources=['modules/surface_route/own_guidance_trial_r5.py','modules/surface_route/curve_guidance_r5.py',
        'modules/surface_route/guidance_r5.py','modules/surface_route/curve_guidance_derivation_r5.json',
        'modules/surface_route/curve_quality_r4.py','modules/surface_route/bend_replan_r3.py',
        'modules/surface_route/replan_r1.py','modules/surface_route/refine_r1.py','modules/surface_route/audit.py',
        'modules/surface_route/own_ct_trial.py','modules/surface_route/own_replan_trial_r1.py',
        'modules/navigation/navigation/guidance.py','modules/navigation/navigation/centerline.py',
        'modules/navigation/navigation/lumen.py','modules/navigation/navigation/camera.py',
        'modules/navigation/navigation/pipeline.py','modules/navigation/navigation/planner.py',
        'modules/navigation/navigation/geometry.py','modules/surface_quality/target_mapping.py',
        'dfx/surface_quality/prepare.py','dfx/surface/prepare.py','dfx/route_audit_speed/checked_plan.py',
        'dfx/route_audit_speed/protocol.py','modules/surface_quality/mesh_clearance_batch.py']
    for path,digest in closure.items():assert SHA(path)==digest,str(path)
    proof=dict(status='eight_own_CT_R4_curves_unchanged_three_displaced_junctions_restored_same_scalar_labels_and_six_renderer_fixtures_passed',
        platform=sys.platform,scenarios=scenarios,render_cases=fixtures,
        source_sha256={n:SHA(SYSTEM/n) for n in sources},
        input_sha256={p.relative_to(SYSTEM).as_posix():h for p,h in closure.items()},
        original_source_route_mask_and_mesh_unchanged=True,new_bitstream=False,PL_access=False,
        original_probability_surface_and_complete_UI_integration_pending=True,production_promoted=False)
    write(output/'acceptance.json',proof);print(proof['status'],flush=True)


if __name__=='__main__':main()
