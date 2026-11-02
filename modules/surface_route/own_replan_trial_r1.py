"""Own CT: refine old-route uncertainty, replan the complete source forest anew."""
from pathlib import Path
import argparse,hashlib,json,statistics,sys
from time import perf_counter
import numpy as np

HERE=Path(__file__).resolve().parent;SYSTEM=HERE.parents[1]
sys.path.insert(0,str(SYSTEM))
from modules.surface_route.own_ct_trial import scene_binding,bound_input,KEYS,SHA
from modules.surface_route.audit import MeshRegion,round_down_float32
from modules.surface_route.refine_r1 import refine_segments,_query
from modules.surface_route.replan_r1 import replan
from modules.surface_quality.mesh_clearance_batch import BatchedMeshClearance
from modules.navigation.navigation.pipeline import load_prepared,choose_target


class AtThreads:
    def __init__(self,base,threads):self.base,self.threads=base,threads
    def distance(self,p):return self.base.distance(p,threads=self.threads)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--native',action='store_true');args=parser.parse_args()
    output=args.output.resolve();assert not output.exists();output.mkdir(parents=True)
    records=[];all_bindings={}
    for key in KEYS:
        begin=perf_counter();cache=SYSTEM/'dfx/surface_quality/ui_cache_r1'/key
        scene,binding=scene_binding(cache);result=bound_input(scene['identity']['result'])
        nav=result/'navigation';source_report=json.loads((nav/'route.json').read_text())
        for name in ('centerline.json',):binding[nav/name]=SHA(nav/name)
        nodule=result/'segmentation/nodule_mask.nii.gz'
        assert SHA(nodule)==source_report['target']['mask_sha256'];binding[nodule]=SHA(nodule)
        c=load_prepared(nav)
        assert c.metadata['input_sha256']==SHA(result/'segmentation/airway_mask.nii.gz')
        assert c.metadata['centerline_id']==hashlib.sha256(c.points_lps_mm.tobytes()+c.edges.tobytes()+str(c.root).encode()).hexdigest()
        np.testing.assert_allclose(c.points_lps_mm,c.geometry.to_lps(c.indices_zyx),rtol=0,atol=1e-10)
        target=choose_target(c,lesion_path=nodule,lesion_index=source_report['target']['index'])
        assert target.metadata==source_report['target']
        assert source_report['minimum_bend_radius_mm']==0.,'Nonzero accepted prefix controller still pending, never ignore it'
        mesh=dict(np.load(cache/'mesh.npz',allow_pickle=False));region=MeshRegion(mesh['points'],mesh['faces'],scene['geometry'])
        if args.native:
            from modules.surface_quality.mesh_clearance_native import NativeMeshClearance
            base=NativeMeshClearance(mesh['points'],mesh['faces'])
            engines={'native_PS1':AtThreads(base,1),'native_PS4':AtThreads(base,4)}
        else:engines={'bounded_NumPy_PS':BatchedMeshClearance(mesh['points'],mesh['faces'])}
        oracle=list(engines.values())[-1]
        old=dict(np.load(nav/'route.npz',allow_pickle=False));old_wall=_query(oracle,old['points_lps_mm'])
        old_edges=np.column_stack((np.arange(len(old_wall)-1),np.arange(1,len(old_wall)))).astype(np.int32)
        old_review,old_arrays=refine_segments(region,old['points_lps_mm'],old_edges,old_wall,oracle,
            threshold_mm=source_report['required_radius_mm']+source_report['resolution_margin_mm'])
        first=np.flatnonzero(~old_arrays['accepted']);prefix=int(first[0])+1 if len(first) else len(old_wall)
        old_review.update(reviewed_prefix_points=prefix,reviewed_prefix_length_mm=float(old['arc_mm'][prefix-1]),
            source_route_overwritten=False)
        tier='Q'+str(scene['identity']['bits']);np.savez_compressed(output/(tier+'_old_refined.npz'),**old_arrays)
        samples={name:[] for name in engines};baseline=None;final=None
        for repetition in range(3):
            order=list(engines)
            if repetition%2:order.reverse()
            for name in order:
                start=perf_counter()
                actual=replan(c,target,region,engines[name],scope_diameter_mm=source_report['scope_diameter_mm'],
                    safety_margin_mm=source_report['safety_margin_mm'],minimum_bend_radius_mm=source_report['minimum_bend_radius_mm'])
                samples[name].append(perf_counter()-start)
                report,route,camera,diag=actual
                assert report['requested_endpoint_id']==source_report['requested_endpoint_id']
                assert report['curve_audit']['whole_curve_accepted']
                if baseline is None:baseline=actual
                else:
                    br,bo,bc,bd=baseline
                    for name2 in route:
                        np.testing.assert_allclose(route[name2],bo[name2],rtol=0,atol=1e-11)
                    for name2 in camera:np.testing.assert_allclose(camera[name2],bc[name2],rtol=0,atol=1e-11)
                    np.testing.assert_array_equal(diag['allowed_edges'],bd['allowed_edges'])
                    np.testing.assert_allclose(diag['all_costs'],bd['all_costs'],rtol=0,atol=1e-11)
                    np.testing.assert_array_equal(diag['all_parents'],bd['all_parents'])
                    assert report['selected_endpoint_id']==br['selected_endpoint_id']
                final=actual
        report,route,camera,diag=final
        # The retained graph has no inserted edges, and every selected pair
        # belongs to both the source forest and the reviewed allowed subset.
        selected=route['centerline_point_ids'];allowed_pairs={tuple(sorted(map(int,e))) for e in c.edges[diag['allowed_edges']]}
        assert all(tuple(sorted(map(int,e))) in allowed_pairs for e in zip(selected[:-1],selected[1:]))
        arc=route['arc_mm'];effective=diag['curve_audit']['effective_distance_mm']
        conservative=np.maximum(0.,effective-1e-6)
        seg=diag['curve_audit']['accepted_lower_bound_mm']
        if len(seg):
            conservative[:-1]=np.minimum(conservative[:-1],seg);conservative[1:]=np.minimum(conservative[1:],seg)
        audit_arrays=dict(points_lps_mm=route['points_lps_mm'],arc_mm=arc,
            actual_wall_distance_mm=route['radius_mm'],segment_lower_bound_mm=seg,
            conservative_radius_mm=round_down_float32(conservative))
        names={}
        for suffix,data in [('audit',audit_arrays),('route',route),('camera',camera),
            ('graph',dict(node_wall_distance_mm=diag['node_wall_distance_mm'],node_effective_distance_mm=diag['node_effective_distance_mm'],
                allowed_edges=diag['allowed_edges'],all_costs=diag['all_costs'],all_parents=diag['all_parents'],edges=c.edges)),
            ('edge_review',diag['edge_audit']),('curve_review',diag['curve_audit'])]:
            file=output/(tier+'_'+suffix+'.npz');np.savez_compressed(file,**data);names[file.name]=SHA(file)
        report_file=output/(tier+'_route.json');report_file.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8');names[report_file.name]=SHA(report_file)
        for path,digest in binding.items():assert SHA(path)==digest,str(path)
        all_bindings.update(binding)
        records.append(dict(tier=tier,field_revision=scene['key'],surface_rule=scene['identity']['surface_rule'],
            source_binding_sha256={p.relative_to(SYSTEM).as_posix():d for p,d in binding.items()},
            old_source_route_length_mm=source_report['length_mm'],old_source_selected_endpoint_id=source_report['selected_endpoint_id'],
            old_route_refinement=old_review,new_route=report,
            complete_warm_replan_samples_seconds=samples,
            complete_warm_replan_medians_seconds={n:statistics.median(v) for n,v in samples.items()},
            timing_includes_all_new_node_and_curve_distances_graph_review_smoothing_camera=True,
            timing_excludes_common_mesh_index_creation_target_loading_file_IO=True,
            arrays_file=tier+'_audit.npz',arrays_sha256=names[tier+'_audit.npz'],
            instrument_parameters={k:source_report[k] for k in ('required_radius_mm','resolution_margin_mm','minimum_bend_radius_mm',
                'forward_window_mm','scope_diameter_mm','safety_margin_mm')},
            files_sha256=names,trial_seconds=perf_counter()-begin))
        print(tier,'graph',report['accepted_edges'],'/',report['original_edges'],'endpoint',report['selected_endpoint_id'],
            'length',report['length_mm'],'target_gap',report['final_target_gap_mm'],flush=True)
    for path,digest in all_bindings.items():assert SHA(path)==digest,str(path)
    sources=['modules/surface_route/own_replan_trial_r1.py','modules/surface_route/replan_r1.py','modules/surface_route/refine_r1.py',
        'modules/surface_route/audit.py','modules/surface_route/own_ct_trial.py','modules/surface_quality/mesh_clearance.py',
        'modules/surface_quality/mesh_clearance_batch.py','modules/navigation/navigation/pipeline.py',
        'modules/navigation/navigation/planner.py','modules/navigation/navigation/camera.py',
        'modules/navigation/navigation/centerline.py','modules/navigation/navigation/geometry.py']
    if args.native:sources+=['modules/surface_quality/mesh_clearance_native.py','modules/surface_quality/host/build/build.json']
    result=dict(status='own_CT_Q5_Q6_original_forest_replanned_new_walls_full_curve_camera_passed',platform=sys.platform,cases=records,
        source_sha256={n:SHA(SYSTEM/n) for n in sources},input_hashes_checked_before_and_after=True,
        nonzero_bend_policy_pending=True,branch_guidance_and_complete_UI_pending=True,
        production_promoted=False,PL_access=False,PS_Marching_Cubes_used=False)
    (output/'acceptance.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8');print(result['status'],flush=True)


if __name__=='__main__':main()
