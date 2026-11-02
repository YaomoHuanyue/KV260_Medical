"""Whole-curve, disconnected-wall and original-mask interval tests."""
from pathlib import Path
import argparse,hashlib,json,sys
import numpy as np
SYSTEM=Path(__file__).resolve().parents[2];sys.path.insert(0,str(SYSTEM))
from modules.surface_route.test_audit import cube
from modules.surface_route.audit import MeshRegion
from modules.surface_route.replan_r1 import replan,mask_segments_inside
from modules.surface_quality.mesh_clearance import MeshClearance
from modules.navigation.navigation.geometry import Geometry
from modules.navigation.navigation.centerline import Centerline
from modules.navigation.navigation.planner import Target


def line_centerline(points,geometry):
    p=np.asarray(points,float);n=len(p)
    mask=np.ones(tuple(geometry.size_xyz[::-1]),bool)
    return Centerline(geometry,np.zeros(3,np.int32),mask,np.ones(mask.shape,np.float32),
        np.rint(geometry.to_zyx(p)).astype(np.int32),p,np.ones(n,np.float32),
        np.column_stack((np.arange(n-1),np.arange(1,n))).astype(np.int32),
        np.zeros(n,np.int32),0,dict(warnings=[]))


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    assert not args.output.exists();tests=[]
    vertices,faces=cube();mesh_geometry=dict(size_xyz=[3,3,3],spacing_xyz=[1.,1.,1.],
        origin_lps_mm=[0.,0.,0.],direction=np.eye(3).ravel().tolist())
    region=MeshRegion(vertices,faces,mesh_geometry);oracle=MeshClearance(vertices,faces)
    geometry=Geometry((5,5,5),(.4,.4,.4),(.2,.2,.2),tuple(np.eye(3).ravel()))
    c=line_centerline([[.6,1,1],[1,1,1],[1.4,1,1]],geometry)
    target=Target('manual_point',c.points_lps_mm[[-1]],{})
    result,route,camera,diag=replan(c,target,region,oracle,scope_diameter_mm=.2,safety_margin_mm=0.)
    assert result['status']=='route_found' and result['selected_endpoint_id']==2
    assert result['curve_audit']['whole_curve_accepted'] and np.all(diag['allowed_edges'])
    np.testing.assert_array_equal(camera['position_lps_mm'],route['points_lps_mm'])
    np.testing.assert_allclose(np.linalg.norm(camera['forward_lps'],axis=1),1.,atol=1e-12)
    np.testing.assert_allclose(np.einsum('ij,ij->i',camera['forward_lps'],camera['up_lps']),0.,atol=1e-12)
    tests.append(dict(name='whole_graph_new_curve_and_regenerated_camera',status='passed'))
    result,route,_,_=replan(c,target,region,oracle,scope_diameter_mm=4.,safety_margin_mm=0.)
    assert result['status']=='unreachable' and not len(route['points_lps_mm'])
    tests.append(dict(name='insufficient_root_has_no_fake_root_path',status='passed'))
    try:replan(c,target,region,oracle,minimum_bend_radius_mm=2.)
    except NotImplementedError:pass
    else:raise AssertionError('Unsupported bend policy silently ignored')
    tests.append(dict(name='nonzero_bend_policy_refused_pending_accepted_controller_integration',status='passed'))
    v2,f2=cube((4,0,0));vertices=np.vstack((vertices,v2));faces=np.vstack((faces,f2+8))
    region=MeshRegion(vertices,faces,dict(mesh_geometry,size_xyz=[7,3,3]));oracle=MeshClearance(vertices,faces)
    geometry=Geometry((25,9,9),(.25,.25,.25),(0.,0.,0.),tuple(np.eye(3).ravel()))
    points=np.column_stack((np.arange(1.,5.001,.25),np.ones(17),np.ones(17)))
    c=line_centerline(points,geometry);target=Target('manual_point',points[[-1]],{})
    result,route,camera,diag=replan(c,target,region,oracle,scope_diameter_mm=.2,safety_margin_mm=0.)
    assert result['status']=='limited_reach' and result['selected_endpoint_id']==2
    assert result['requested_endpoint_id']==16 and result['synthetic_bridge_edges']==0
    assert result['curve_audit']['whole_curve_accepted'] and np.all(route['points_lps_mm'][:,0]<2)
    tests.append(dict(name='replan_approach_stops_before_reconstructed_chamber_gap',status='passed'))
    # Endpoints and the midpoint lie in closed foreground cells. A very short
    # background interval lies just after the midpoint, between two grid cuts.
    geometry=Geometry((3,3,3),(1.,1.,1.),(0.,0.,0.),tuple(np.eye(3).ravel()))
    c=line_centerline([[.49,.5102,1.],[.51,.4902,1.]],geometry);c.mask[1,1,1]=False
    assert np.all(c.inside(c.points_lps_mm)) and c.inside(c.points_lps_mm.mean(axis=0)[None])[0]
    assert not mask_segments_inside(c,c.points_lps_mm)[0]
    tests.append(dict(name='complete_voxel_interval_review_catches_subsample_background',status='passed'))
    c=line_centerline([[0,0,0],[0,0,1],[0,1,1]],geometry)
    c.edges=np.array([[0,1],[1,2],[0,2]],np.int32)
    try:replan(c,Target('manual_point',c.points_lps_mm[[-1]],{}),region,oracle)
    except ValueError:pass
    else:raise AssertionError('Input cycle silently removed')
    tests.append(dict(name='nonforest_input_refused_without_topology_repair',status='passed'))
    names=['modules/surface_route/replan_r1.py','modules/surface_route/refine_r1.py',
        'modules/surface_route/test_replan_r1.py','modules/surface_route/audit.py',
        'modules/navigation/navigation/planner.py','modules/navigation/navigation/camera.py',
        'modules/navigation/navigation/centerline.py','modules/navigation/navigation/geometry.py']
    record=dict(status='new_surface_graph_replan_original_mask_curve_and_camera_tests_passed',cases=tests,
        platform=sys.platform,source_sha256={n:hashlib.sha256((SYSTEM/n).read_bytes()).hexdigest() for n in names},
        PL_access=False,clinical_safety_certified=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8');print(record['status'],len(tests))


if __name__=='__main__':main()
