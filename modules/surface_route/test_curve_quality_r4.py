"""Physical proposal invariants and rejection of shortcuts through mask/walls."""
from pathlib import Path
import argparse,hashlib,json,sys
import numpy as np
SYSTEM=Path(__file__).resolve().parents[2];sys.path.insert(0,str(SYSTEM))
from modules.surface_route.curve_quality_r4 import gaussian_candidate,QualitySurfaceBendPlanner
from modules.surface_route.test_audit import cube
from modules.surface_route.test_replan_r1 import line_centerline
from modules.surface_route.audit import MeshRegion
from modules.surface_quality.mesh_clearance import MeshClearance
from modules.navigation.navigation.geometry import Geometry
from modules.navigation.navigation.planner import Target


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    assert not args.output.exists();cases=[]
    p=np.array([[.6,.6,1],[.6,1.4,1],[1.4,1.4,1]])
    a,stats=gaussian_candidate(p,.025,.5)
    np.testing.assert_array_equal(a[[0,-1]],p[[0,-1]])
    assert np.max(np.linalg.norm(np.diff(a,axis=0),axis=1))<=.025+1e-12
    rot=np.array([[0,-1.,0],[1.,0,0],[0,0,1.]]);translation=np.array([12.,-23.,7.])
    b,st=gaussian_candidate(p@rot.T+translation,.025,.5)
    np.testing.assert_allclose(b,a@rot.T+translation,atol=2e-12,rtol=0)
    np.testing.assert_allclose(st['maximum_parameter_matched_displacement_mm'],stats['maximum_parameter_matched_displacement_mm'],atol=2e-12)
    cases.append(dict(name='exact_endpoints_step_and_LPS_rigid_transform_equivariance',status='passed'))
    for invalid,step,sigma in [(p,0,.5),(p,.025,np.inf),(np.zeros((3,3)),.025,.5),(p,1e-5,.5)]:
        try:gaussian_candidate(invalid,step,sigma)
        except ValueError:pass
        else:raise AssertionError('Invalid/capacity input accepted')
    cases.append(dict(name='degenerate_nonfinite_step_and_no_silent_capacity_coarsening',status='passed'))
    vertices,faces=cube();meshgeom=dict(size_xyz=[3,3,3],spacing_xyz=[1.,1.,1.],origin_lps_mm=[0.,0.,0.],direction=np.eye(3).ravel().tolist())
    region=MeshRegion(vertices,faces,meshgeom);oracle=MeshClearance(vertices,faces)
    geometry=Geometry((41,41,41),(.05,.05,.05),(0.,0.,0.),tuple(np.eye(3).ravel()))
    c=line_centerline(p,geometry);target=Target('manual_point',p[[-1]],{})
    planner=QualitySurfaceBendPlanner(c,region,oracle,sigma_schedule_mm=(.25,.5,1.))
    report,route,camera=planner.plan(target,scope_diameter_mm=.02,safety_margin_mm=0.,minimum_bend_radius_mm=.5)
    assert report['curve_quality']['accepted'] and report['curve_audit']['whole_curve_accepted']
    assert np.all(route['bend_radius_mm']+1e-5>=.5)
    np.testing.assert_array_equal(route['points_lps_mm'][[0,-1]],p[[0,-1]])
    np.testing.assert_array_equal(camera['position_lps_mm'],route['points_lps_mm'])
    assert np.all(route['radius_mm']<=route['actual_wall_distance_mm'])
    cases.append(dict(name='valid_corner_rounding_keeps_endpoints_geometry_and_regenerates_camera',status='passed'))
    planner=QualitySurfaceBendPlanner(c,region,oracle,sigma_schedule_mm=(.5,1.),maximum_displacement_mm=0.)
    report,_,_=planner.plan(target,scope_diameter_mm=.02,safety_margin_mm=0.,minimum_bend_radius_mm=.5)
    assert not report['curve_quality']['accepted']
    assert all(x['status']=='rejected_displacement_bound' for x in report['curve_quality']['attempts'])
    cases.append(dict(name='explicit_displacement_budget_never_relaxed_to_force_bend_success',status='passed'))
    # The original axis-aligned graph and its small old smoothing avoid this
    # background square; a smooth diagonal shortcut crosses it.
    c.mask[16:25,16:25,16:25]=False
    planner=QualitySurfaceBendPlanner(c,region,oracle,sigma_schedule_mm=(.5,1.))
    report,_,_=planner.plan(target,scope_diameter_mm=.02,safety_margin_mm=0.,minimum_bend_radius_mm=.5)
    assert not report['curve_quality']['accepted']
    assert any(x['status']=='rejected_full_wall_crop_or_source_mask_review' for x in report['curve_quality']['attempts'])
    cases.append(dict(name='smooth_shortcut_through_source_mask_background_refused',status='passed'))
    # A closed oppositely oriented inner cube represents a real wall/cavity.
    # Even an all-foreground source mask must not permit crossing that wall.
    inner=vertices*.2+.8;v=np.vstack((vertices,inner));f=np.vstack((faces,faces[:,::-1]+len(vertices)))
    region=MeshRegion(v,f,meshgeom);oracle=MeshClearance(v,f);c=line_centerline(p,geometry)
    planner=QualitySurfaceBendPlanner(c,region,oracle,sigma_schedule_mm=(.5,1.))
    report,_,_=planner.plan(target,scope_diameter_mm=.02,safety_margin_mm=0.,minimum_bend_radius_mm=.5)
    assert not report['curve_quality']['accepted']
    assert any(x['status']=='rejected_full_wall_crop_or_source_mask_review' for x in report['curve_quality']['attempts'])
    cases.append(dict(name='smooth_shortcut_through_actual_internal_wall_refused',status='passed'))
    planner=QualitySurfaceBendPlanner(c,region,oracle)
    report,_,_=planner.plan(target,scope_diameter_mm=.02,safety_margin_mm=0.,minimum_bend_radius_mm=.5,smooth=False)
    assert not report['curve_quality']['enabled'] and not report['curve_quality']['attempts']
    cases.append(dict(name='explicit_smoothing_off_honored',status='passed'))
    names=['modules/surface_route/curve_quality_r4.py','modules/surface_route/test_curve_quality_r4.py',
        'modules/surface_route/bend_replan_r3.py','modules/surface_route/replan_r1.py',
        'modules/surface_route/refine_r1.py','modules/surface_route/audit.py']
    receipt=dict(status='physical_curve_quality_invariants_and_wall_mask_shortcut_rejection_passed',platform=sys.platform,
        cases=cases,source_sha256={n:hashlib.sha256((SYSTEM/n).read_bytes()).hexdigest() for n in names},PL_access=False)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(receipt['status'],len(cases))


if __name__=='__main__':main()
