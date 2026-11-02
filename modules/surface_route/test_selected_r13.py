"""Selected raw-path identity, exact source arcs, partial cues and cyclic topology."""
from pathlib import Path
from dataclasses import replace
import argparse,copy,json,sys,tempfile
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from modules.surface_route.comparison_r12 import Comparison
from modules.surface_route.comparison_r11 import solve_all
from modules.surface_route.test_comparison_r11 import fixture,heap_oracle
from modules.surface_route.test_guidance_r5 import fixture as branch_fixture,refused
from modules.surface_route.selected_surface_r13 import selected_source,selected_node_arcs,forest_for_path,audit_selected,arc
from modules.surface_route.guidance_r13 import build_guidance
from modules.surface_route.bundle_r8 import write_json,sha
from modules.navigation.navigation.camera import poses


def save(folder,whole,alternative,data):
    folder.mkdir()
    write_json(folder/'whole_instrument_profiles.json',whole)
    write_json(folder/'whole_alternative_routes.json',alternative)
    np.savez_compressed(folder/'whole_comparison_arrays.npz',**data)


def run():
    tests=[]
    binding=dict(scalar_sha256='synthetic',mesh_sha256='box',CT_input_sha256='fixture',
        centerline_id='synthetic-original-node-order',source_files_sha256={},target={})
    comp=Comparison(*fixture(n=8)[:5],binding=binding)
    q=comp.queries([1.,20.],.1);whole,alternative,data=comp.produce(q,*solve_all(q,heap_oracle))
    with tempfile.TemporaryDirectory(prefix='selected-r13-') as temp:
        folder=Path(temp)/'comparison';save(folder,whole,alternative,data)
        candidate=alternative['groups'][0]['pareto'][0]['candidate_id']
        p,ids,u,options,identity=selected_source(comp,folder,0,candidate)
        assert ids[0]==0 and ids[-1]>0 and np.array_equal(p[0],comp.c.points_lps_mm[0])
        report,route,camera,c=audit_selected(comp,folder,0,candidate)
        assert not report['automatic_route_replanning'] and report['bend_constraint_passed']
        assert route['centerline_point_ids'][-1]==ids[-1]
        assert np.array_equal(route['points_lps_mm'][[0,-1]],p[[0,-1]])
        for key,value in poses(route['points_lps_mm'],route['arc_mm']).items():
            np.testing.assert_array_equal(camera[key],value)
        mapped,_=selected_node_arcs(c,route)
        np.testing.assert_allclose(mapped,np.interp(arc(comp.c.points_lps_mm[ids]),u,arc(p)),rtol=0,atol=1e-12)
        tests.append('full_selected_polyline_actual_wall_review_camera_and_exact_raw_node_mapping')
        for value in (-1,1.5,len(comp.c.points_lps_mm),2**40):
            bad=copy.deepcopy(alternative)
            next(r for r in bad['groups'][0]['candidates'] if r['candidate_id']==candidate)['original_parent_node_ids'][1]=value
            path=folder/'whole_alternative_routes.json';path.write_text(json.dumps(bad),encoding='utf-8')
            refused(lambda:selected_source(comp,folder,0,candidate))
        path.write_text(json.dumps(alternative),encoding='utf-8')
        refused(lambda:selected_source(comp,folder,0,-1));refused(lambda:selected_source(comp,folder,True,candidate))
        bad=copy.deepcopy(whole);bad['binding']['mesh_sha256']='another-wall'
        (folder/'whole_instrument_profiles.json').write_text(json.dumps(bad),encoding='utf-8')
        refused(lambda:selected_source(comp,folder,0,candidate))
        tests.append('corrupt_noninteger_out_of_range_node_wrong_mesh_or_hidden_candidate_rejected')
    c,route,field,image=branch_fixture()
    ids=route['centerline_point_ids'].copy();ref=c.points_lps_mm[ids]
    route.update(guidance_reference_node_ids=ids.copy(),guidance_reference_points_lps_mm=ref,
                 guidance_reference_arc_mm=arc(ref))
    mapped,_=selected_node_arcs(c,route)
    np.testing.assert_allclose(mapped,np.interp(arc(ref),route['guidance_source_parameter_mm'],route['arc_mm']),rtol=0,atol=1e-12)
    cues,targets=build_guidance(c,route,field,image)
    assert len(cues['events'])==1 and cues['events'][0]['available']
    assert cues['events'][0]['selected_exit_point_id']==3
    assert all(t.any() and not np.any(t&(field.values<=0)) for t in targets.values())
    tests.append('selected_daughter_full_reference_source_parameter_and_same_scalar_labels')
    partial=copy.deepcopy(route)
    keep=partial['guidance_source_parameter_mm']<=7.
    for key in ('points_lps_mm','arc_mm','guidance_source_parameter_mm'):partial[key]=partial[key][keep]
    partial['centerline_point_ids']=ids[arc(ref)<=partial['guidance_source_parameter_mm'][-1]+1e-9]
    mapped,proof=selected_node_arcs(c,partial)
    assert np.array_equal(partial['centerline_point_ids'],[0,1]) and proof['unreached_source_nodes_omitted']==3
    cues,targets=build_guidance(c,partial,field,image);assert not cues['events'] and not targets
    root=copy.deepcopy(partial)
    for key in ('points_lps_mm','arc_mm','guidance_source_parameter_mm','centerline_point_ids'):root[key]=root[key][:1]
    cues,targets=build_guidance(c,root,field,image)
    assert not cues['events'] and not targets and all(not len(v) for v in poses(root['points_lps_mm'],root['arc_mm']).values())
    tests.append('audited_prefix_and_root_only_omit_unreached_exits_and_false_camera_motion')
    for key in ('guidance_source_parameter_mm','guidance_reference_arc_mm','arc_mm'):
        bad=copy.deepcopy(route);bad[key][2]=bad[key][1]
        refused(lambda:selected_node_arcs(c,bad))
    bad=copy.deepcopy(partial);bad['centerline_point_ids']=ids.copy();refused(lambda:selected_node_arcs(c,bad))
    bad=copy.deepcopy(route);bad['guidance_reference_points_lps_mm'][2]+=10;refused(lambda:selected_node_arcs(c,bad))
    tests.append('nonmonotone_parameters_false_reference_and_future_node_ids_rejected')
    rotated=np.array([[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])
    moved=replace(c,points_lps_mm=c.points_lps_mm@rotated.T+[7.,3.,-9.])
    transformed=copy.deepcopy(route)
    for key in ('points_lps_mm','guidance_reference_points_lps_mm'):
        transformed[key]=transformed[key]@rotated.T+[7.,3.,-9.]
    np.testing.assert_allclose(selected_node_arcs(moved,transformed)[0],selected_node_arcs(c,route)[0],rtol=0,atol=1e-12)
    tests.append('selected_physical_mapping_invariant_under_rigid_LPS_camera_transform')
    cyc=Comparison(*fixture(indices=[[2,2,0],[2,2,1],[2,3,1]])[:5],binding=binding)
    forest,proof=forest_for_path(cyc,np.array([0,2],np.int32))
    assert proof['changed'] and proof['added_edges']==[(0,2)] and len(forest.edges)==2
    assert np.array_equal(forest.points_lps_mm,cyc.c.points_lps_mm) and np.array_equal(forest.mask,cyc.c.mask)
    assert not proof['original_case_files_or_mask_modified']
    same,proof=forest_for_path(cyc,np.array([0,1,2],np.int32));assert same is cyc.c and not proof['changed']
    refused(lambda:forest_for_path(cyc,np.array([0,2,1,0],np.int32)))
    tests.append('raw_cycle_selected_edge_explicit_derived_forest_no_mask_or_node_change')
    return tests


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    assert not args.output.exists();tests=run()
    write_json(args.output,dict(status='selected_surface_identity_prefix_camera_and_guidance_tests_passed',
        platform=sys.platform,tests=tests,PL_access=False,production_promoted=False,
        source_sha256={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in [Path(__file__),
            ROOT/'modules/surface_route/selected_surface_r13.py',ROOT/'modules/surface_route/guidance_r13.py']}))
    print('passed',len(tests),flush=True)
