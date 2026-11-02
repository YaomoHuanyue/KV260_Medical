"""Independent numerical and policy checks; never compare a function to itself."""
from pathlib import Path
import argparse, hashlib, json, sys
import numpy as np
SYSTEM=Path(__file__).resolve().parents[2];sys.path.insert(0,str(SYSTEM))
from modules.surface_route.bend_replan_r3 import NativeAuditor, AUDIT_FIELDS, route_digest, validate_stored_audit, checked_replan
from modules.navigation.navigation.planner import Target
from ui.features.analysis import bend_radii, route_hud
from types import SimpleNamespace


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    assert not args.output.exists();cases=[];engine=NativeAuditor()
    rng=np.random.default_rng(9403)
    paths=[np.empty((0,3)),np.array([[0.,0,0]]),np.array([[0.,0,0],[1,0,0],[1,1,0]]),
           np.array([[0.,0,0],[1,0,0],[0,0,0]]),np.zeros((7,3)),np.cumsum(rng.normal(size=(4096,3)),axis=0)]
    for p in paths:
        arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(p,axis=0),axis=1))] if len(p) else np.empty(0)
        r=rng.uniform(0,3,len(p)).astype(np.float32)
        for window in (0.,3.,10.):
            values=[window,.3,.7,1.]
            out=engine(p,arc,r,values)
            expected_bend=bend_radii(p)
            np.testing.assert_allclose(out[:,0],expected_bend,rtol=2e-9,atol=1e-7)
            report=dict(resolution_margin_mm=.3,required_radius_mm=.7,minimum_bend_radius_mm=1.)
            old=route_hud(p,arc,r,report,window)['samples']
            for i,row in enumerate(old):
                np.testing.assert_allclose(out[i,1:4],[row['forward_adjusted_diameter_mm']/2,
                    row['forward_minimum_bend_radius_mm'] if row['forward_minimum_bend_radius_mm'] is not None else np.inf,
                    row['spare_radius_mm']],rtol=2e-9,atol=1e-7)
                assert out[i,4]==('clear','caution','blocked').index(row['state'])
    np.testing.assert_allclose(engine(paths[2],np.arange(3.),np.ones(3,np.float32),[0,0,0,0])[1,0],2/np.pi,rtol=1e-14)
    cases.append(dict(name='original_independent_NumPy_bend_and_HUD_all_fields_18_cases_including_4096_capacity',status='passed'))
    for p,a,r,v in [(np.zeros((4097,3)),np.arange(4097.),np.ones(4097),[0,0,0,0]),
        (np.zeros((2,3)),np.array([1.,0]),np.ones(2),[0,0,0,0]),
        (np.zeros((2,3)),np.arange(2.),np.ones(2),[0,0,0,np.nan])]:
        try:engine(p,a,r,v)
        except ValueError:pass
        else:raise AssertionError('Invalid bounded input accepted')
    cases.append(dict(name='capacity_order_and_nonfinite_parameters_refused',status='passed'))

    class Fixture:
        def __init__(self,never_pass=False):
            self.c=SimpleNamespace(root=0,points_lps_mm=np.array([[i,0.,0] for i in range(9)]))
            self.auditor=engine;self.history=[];self.calls=[];self.never_pass=never_pass
        def plan(self,t,minimum_bend_radius_mm=0.,forward_window_mm=10.,**options):
            end=8 if t.kind=='lesion_candidate' else int(np.argmin(np.linalg.norm(self.c.points_lps_mm-t.points_lps_mm[0],axis=1)))
            self.calls.append((t.kind,end))
            p=self.c.points_lps_mm[:end+1].copy();a=np.arange(end+1,dtype=float);r=np.ones(end+1,np.float32)*5
            rows=engine(p,a,r,[forward_window_mm,0.,0.,minimum_bend_radius_mm])
            # Known analytic decision fixture: first forbidden turn is index 5.
            # Its two-sample lead is arc 3; 80%=2.4 selects original node 2.
            if end==8:rows[5,0]=.1
            if self.never_pass:rows[0,0]=.1
            route=dict(points_lps_mm=p,arc_mm=a,radius_mm=r,centerline_point_ids=np.arange(end+1,dtype=np.int32))
            for i,n in enumerate(AUDIT_FIELDS):route[n]=rows[:,i].copy()
            report=dict(target_kind=t.kind,target=t.metadata,requested_endpoint_id=end,
                requested_endpoint_lps_mm=self.c.points_lps_mm[end].tolist(),closest_centerline_gap_mm=2.,
                selected_endpoint_id=end,length_mm=float(end),status='route_found',reason=None,warnings=[],
                required_radius_mm=0.,resolution_margin_mm=0.,minimum_bend_radius_mm=minimum_bend_radius_mm,
                forward_window_mm=forward_window_mm,route_audit=dict(protocol=3,backend=engine.backend,
                    route_sha256=route_digest(route),required_radius_mm=0.,resolution_margin_mm=0.,
                    minimum_bend_radius_mm=minimum_bend_radius_mm,forward_window_mm=forward_window_mm))
            camera=dict(position_lps_mm=p.copy())
            self.history.append(dict(target_kind=t.kind,report=report.copy(),route=route))
            return report,route,camera
    target=Target('lesion_candidate',np.array([[8.,2.,0]]),dict(index=4))
    fixture=Fixture();report,route,_=checked_replan(fixture,target,minimum_bend_radius_mm=1.)
    assert fixture.calls==[('lesion_candidate',8),('manual_point',2)]
    assert report['requested_endpoint_id']==8 and report['target']==dict(index=4) and report['target_kind']=='lesion_candidate'
    assert report['status']=='limited_reach' and report['reason']=='insufficient_bend_radius'
    assert report['bend_prefix_queries']==1 and report['final_target_gap_mm']==np.sqrt(40.)
    cases.append(dict(name='independent_known_80_percent_prefix_and_original_target_restoration',status='passed'))
    fixture=Fixture();report,_,_=checked_replan(fixture,target,minimum_bend_radius_mm=0.)
    assert len(fixture.calls)==1 and report['bend_prefix_queries']==0
    cases.append(dict(name='zero_threshold_preserves_original_query',status='passed'))
    fixture=Fixture(True)
    try:checked_replan(fixture,target,minimum_bend_radius_mm=1.)
    except RuntimeError:pass
    else:raise AssertionError('Unverified bend prefix silently accepted')
    assert len(fixture.calls)==9
    cases.append(dict(name='eight_retry_bound_retained_and_unverified_result_refused',status='passed'))
    route['radius_mm'][0]=4
    try:validate_stored_audit(route,report)
    except ValueError:pass
    else:raise AssertionError('Different geometry accepted by old audit')
    cases.append(dict(name='audit_route_digest_tamper_refused',status='passed'))
    names=['modules/surface_route/bend_replan_r3.py','modules/surface_route/test_bend_replan_r3.py',
        'dfx/route_audit_speed/checked_plan.py','dfx/route_audit_speed/protocol.py','ui/features/analysis.py']
    receipt=dict(status='new_surface_native_bend_numeric_and_original_prefix_policy_tests_passed',platform=sys.platform,
        cases=cases,source_sha256={n:hashlib.sha256((SYSTEM/n).read_bytes()).hexdigest() for n in names},
        native_library_sha256=hashlib.sha256(engine.library.read_bytes()).hexdigest(),PL_access=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8');print(receipt['status'],len(cases))


if __name__=='__main__':main()
