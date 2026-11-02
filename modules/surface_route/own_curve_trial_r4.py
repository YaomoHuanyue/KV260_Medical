"""Own CT Q5/Q6 nonzero-bend prefix review, fresh geometry on every query."""
from pathlib import Path
import argparse,json,sys
from time import perf_counter
import numpy as np
HERE=Path(__file__).resolve().parent;SYSTEM=HERE.parents[1];sys.path.insert(0,str(SYSTEM))
from modules.surface_route.own_ct_trial import scene_binding,bound_input,KEYS,SHA
from modules.surface_route.audit import MeshRegion
from modules.surface_route.own_replan_trial_r1 import AtThreads
from modules.surface_route.bend_replan_r3 import NativeAuditor,checked_replan,validate_stored_audit
from modules.surface_route.curve_quality_r4 import QualitySurfaceBendPlanner as SurfaceBendPlanner
from modules.surface_quality.mesh_clearance_batch import BatchedMeshClearance
from modules.navigation.navigation.pipeline import load_prepared,choose_target


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--native',action='store_true');args=parser.parse_args()
    output=args.output.resolve();assert not output.exists();output.mkdir(parents=True)
    cases=[];scenarios=[];closure={};audit=NativeAuditor()
    for key in KEYS:
        cache=SYSTEM/'dfx/surface_quality/ui_cache_r1'/key
        scene,binding=scene_binding(cache);result=bound_input(scene['identity']['result']);nav=result/'navigation'
        source_report=json.loads((nav/'route.json').read_text());c=load_prepared(nav)
        nodule=result/'segmentation/nodule_mask.nii.gz'
        assert SHA(nodule)==source_report['target']['mask_sha256']
        for path in (nav/'centerline.json',nodule):binding[path]=SHA(path)
        assert c.metadata['input_sha256']==SHA(result/'segmentation/airway_mask.nii.gz')
        assert c.metadata['centerline_id']==__import__('hashlib').sha256(c.points_lps_mm.tobytes()+c.edges.tobytes()+str(c.root).encode()).hexdigest()
        np.testing.assert_allclose(c.points_lps_mm,c.geometry.to_lps(c.indices_zyx),rtol=0,atol=1e-10)
        target=choose_target(c,lesion_path=nodule,lesion_index=source_report['target']['index'])
        assert target.metadata==source_report['target']
        mesh=dict(np.load(cache/'mesh.npz',allow_pickle=False));region=MeshRegion(mesh['points'],mesh['faces'],scene['geometry'])
        if args.native:
            from modules.surface_quality.mesh_clearance_native import NativeMeshClearance
            oracle=AtThreads(NativeMeshClearance(mesh['points'],mesh['faces']),4)
        else:oracle=BatchedMeshClearance(mesh['points'],mesh['faces'])
        tier='Q'+str(scene['identity']['bits'])
        for threshold in (0.,.05,1.,10.):
            label=tier+'_bend_'+str(threshold).replace('.','p');times=[];baseline=None
            for repetition in range(2):
                planner=SurfaceBendPlanner(c,region,oracle,audit)
                start=perf_counter()
                report,route,camera=checked_replan(planner,target,scope_diameter_mm=source_report['scope_diameter_mm'],
                    safety_margin_mm=source_report['safety_margin_mm'],minimum_bend_radius_mm=threshold,
                    forward_window_mm=source_report['forward_window_mm'])
                times.append(perf_counter()-start)
                validate_stored_audit(route,report)
                assert report['requested_endpoint_id']==source_report['requested_endpoint_id']
                assert report['target']==source_report['target'] and report['target_kind']=='lesion_candidate'
                assert report['bend_constraint_passed'] and report['bend_prefix_queries']<=8
                assert np.all(route['bend_radius_mm']+1e-5>=threshold)
                if threshold==1.:
                    assert report['curve_quality']['accepted'] and report['point_count']>1
                    assert report['bend_prefix_queries']==0 and report['selected_endpoint_id']==496
                assert np.all(route['radius_mm']<=route['actual_wall_distance_mm'])
                for query in planner.history:
                    assert query['report']['curve_audit']['whole_curve_accepted']
                    assert not np.any(query['diagnostics']['curve_audit']['state'])
                if baseline is None:baseline=(report,route,camera,planner.history)
                else:
                    br,bo,bc,bh=baseline
                    assert report['query_trace']==br['query_trace'] and len(planner.history)==len(bh)
                    for n in route:np.testing.assert_allclose(route[n],bo[n],rtol=0,atol=1e-11)
                    for n in camera:np.testing.assert_allclose(camera[n],bc[n],rtol=0,atol=1e-11)
            files={}
            for suffix,data in [('route',route),('camera',camera)]:
                f=output/(label+'_'+suffix+'.npz');np.savez_compressed(f,**data);files[f.name]=SHA(f)
            f=output/(label+'_route.json');f.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8');files[f.name]=SHA(f)
            for i,query in enumerate(planner.history):
                q=query['route'];qr=query['report'];name=label+'_query_'+str(i)
                data=dict(points_lps_mm=q['points_lps_mm'],arc_mm=q['arc_mm'],conservative_radius_mm=q['radius_mm'],
                    actual_wall_distance_mm=q['actual_wall_distance_mm'],
                    **{n:q[n] for n in ('bend_radius_mm','forward_adjusted_radius_mm','forward_minimum_bend_radius_mm','spare_radius_mm','clearance_state')})
                f=output/(name+'.npz');np.savez_compressed(f,**data);files[f.name]=SHA(f)
                cases.append(dict(tier=name,arrays_file=f.name,arrays_sha256=SHA(f),
                    source_binding_sha256={p.relative_to(SYSTEM).as_posix():d for p,d in binding.items()},
                    instrument_parameters={n:qr[n] for n in ('forward_window_mm','resolution_margin_mm','required_radius_mm','minimum_bend_radius_mm')}))
            scenarios.append(dict(tier=tier,minimum_bend_radius_mm=threshold,report=report,files_sha256=files,
                complete_fresh_prefix_replan_samples_seconds=times,
                timing_includes_every_fresh_graph_wall_mask_curve_smoothing_camera_and_native_audit_query=True,
                timing_excludes_common_mesh_index_target_loading_and_IO=True))
            print(label,'queries',len(planner.history),'endpoint',report['selected_endpoint_id'],
                  'length',report['length_mm'],'gap',report['final_target_gap_mm'],flush=True)
        for p,d in binding.items():assert SHA(p)==d
        closure.update(binding)
    for p,d in closure.items():assert SHA(p)==d
    sources=['modules/surface_route/own_curve_trial_r4.py','modules/surface_route/bend_replan_r3.py','modules/surface_route/curve_quality_r4.py',
        'modules/surface_route/replan_r1.py','modules/surface_route/refine_r1.py','modules/surface_route/audit.py',
        'modules/surface_route/own_replan_trial_r1.py','modules/surface_route/own_ct_trial.py',
        'modules/surface_quality/mesh_clearance_batch.py','modules/surface_quality/mesh_clearance.py',
        'dfx/route_audit_speed/checked_plan.py','dfx/route_audit_speed/protocol.py',
        'dfx/route_audit/archive/float_atan_r1/hls/audit.hpp',
        'modules/navigation/navigation/pipeline.py','modules/navigation/navigation/planner.py',
        'modules/navigation/navigation/camera.py','modules/navigation/navigation/centerline.py','modules/navigation/navigation/geometry.py']
    if args.native:sources+=['modules/surface_quality/mesh_clearance_native.py','modules/surface_quality/host/build/build.json']
    receipt=dict(status='own_CT_Q5_Q6_physical_curve_quality_bend_wall_mask_camera_passed',
        platform=sys.platform,scenarios=scenarios,cases=cases,source_sha256={n:SHA(SYSTEM/n) for n in sources},
        native_audit_library_sha256=SHA(audit.library),all_input_hashes_rechecked=True,
        source_route_overwritten=False,production_promoted=False,new_bitstream=False,PL_access=False,
        original_probability_surface_and_new_branch_guidance_UI_integration_pending=True)
    (output/'acceptance.json').write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n',encoding='utf-8');print(receipt['status'],flush=True)


if __name__=='__main__':main()
