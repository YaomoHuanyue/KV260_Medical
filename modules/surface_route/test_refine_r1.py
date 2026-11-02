"""Adversaries for adaptive edge review and bounded resource use."""
from pathlib import Path
import argparse,hashlib,json,sys
import numpy as np
SYSTEM=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SYSTEM))
from modules.surface_route.audit import MeshRegion
from modules.surface_route.refine_r1 import refine_segments,PASSED,INTERIOR,UNRESOLVED,BUDGET,ENDPOINT
from modules.surface_route.test_audit import cube
from modules.surface_quality.mesh_clearance import MeshClearance


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    assert not args.output.exists()
    vertices,faces=cube()
    geometry=dict(size_xyz=[3,3,3],spacing_xyz=[1.,1.,1.],origin_lps_mm=[0.,0.,0.],direction=np.eye(3).ravel().tolist())
    region=MeshRegion(vertices,faces,geometry);oracle=MeshClearance(vertices,faces)
    route=np.array([[.6,1,1],[1.4,1,1]])
    wall=oracle.distance(route)[0];edges=np.array([[0,1]],np.int32)
    cases=[]
    # The coarse bound is .2 mm, but the true minimum is .6 mm. Subdivision
    # must recover the edge without lowering its .5 mm threshold.
    r,a=refine_segments(region,route,edges,wall,oracle,threshold_mm=.5)
    assert a['state'][0]==PASSED and r['queried_midpoints']>0
    cases.append(dict(name='recover_safe_edge_coarse_bound_cannot_accept',status='passed'))
    for option,label in [({'maximum_depth':0},UNRESOLVED),({'query_budget':0},BUDGET)]:
        r,a=refine_segments(region,route,edges,wall,oracle,threshold_mm=.5,**option)
        assert a['state'][0]==label and a['accepted_lower_bound_mm'][0]==0
        cases.append(dict(name='bounded_'+str(label),status='passed'))
    v2,f2=cube((4,0,0));vertices=np.vstack((vertices,v2));faces=np.vstack((faces,f2+8))
    region=MeshRegion(vertices,faces,dict(geometry,size_xyz=[7,3,3]));oracle=MeshClearance(vertices,faces)
    route=np.array([[1.,1.,1.],[5.,1.,1.],[5.,1.2,1.]])
    edges=np.array([[0,1],[1,2]],np.int32)
    r,a=refine_segments(region,route,edges,oracle.distance(route)[0],oracle,threshold_mm=.4)
    assert a['state'][0]==INTERIOR and a['state'][1]==PASSED
    assert np.isfinite(a['witness_lps_mm'][0]).all() and a['witness_effective_distance_mm'][0]<.4
    cases.append(dict(name='find_wall_crossing_while_preserving_other_chamber_edge',status='passed'))
    route=np.array([[.01,1,1],[1.,1.,1.]])
    r,a=refine_segments(region,route,np.array([[0,1]]),oracle.distance(route)[0],oracle,threshold_mm=.4)
    assert a['state'][0]==ENDPOINT and r['queried_midpoints']==0
    cases.append(dict(name='reject_bad_endpoint_without_unnecessary_queries',status='passed'))
    empty=np.empty((0,2),np.int32)
    r,a=refine_segments(region,route,empty,oracle.distance(route)[0],oracle,threshold_mm=.4)
    assert r['accepted']==0 and a['accepted'].shape==(0,)
    cases.append(dict(name='empty_graph_is_bounded_and_valid',status='passed'))
    for option in ({'maximum_depth':25},{'query_budget':-1},{'minimum_length_mm':0},{'numerical_guard_mm':0},{'threshold_mm':float('nan')}):
        kwargs=dict(threshold_mm=.4);kwargs.update(option)
        try:refine_segments(region,route,empty,oracle.distance(route)[0],oracle,**kwargs)
        except ValueError:pass
        else:raise AssertionError('Invalid limits accepted')
    cases.append(dict(name='invalid_limits_refused',status='passed'))
    names=['modules/surface_route/refine_r1.py','modules/surface_route/test_refine_r1.py',
           'modules/surface_route/audit.py','modules/surface_route/test_audit.py','modules/surface_quality/mesh_clearance.py']
    result=dict(status='adaptive_actual_wall_edge_refinement_adversaries_passed',cases=cases,platform=sys.platform,
        source_sha256={n:hashlib.sha256((SYSTEM/n).read_bytes()).hexdigest() for n in names},PL_access=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(result['status'],len(cases))


if __name__=='__main__':main()
