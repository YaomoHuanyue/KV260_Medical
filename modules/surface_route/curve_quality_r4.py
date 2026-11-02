"""Physical-scale curve smoothing, accepted only after full wall/mask review.

This is an explicit candidate algorithm. The source graph, target, endpoints,
mask and mesh are unchanged. Failure retains the original checked-prefix path.
"""
from time import perf_counter
import numpy as np
from scipy.ndimage import gaussian_filter1d
from modules.navigation.navigation.camera import poses
from .audit import _points,round_down_float32
from .replan_r1 import review_curve
from .bend_replan_r3 import SurfaceBendPlanner,AUDIT_FIELDS,route_digest,validate_stored_audit


def resample_uniform(points, step_mm):
    p=_points(points)
    if not np.isfinite(step_mm) or step_mm<=0 or len(p)>4096:
        raise ValueError('Positive physical step and at most 4096 points required')
    if len(p)<2:return p.copy(),np.zeros(len(p))
    length=np.linalg.norm(np.diff(p,axis=0),axis=1)
    if np.any(length<=1e-10):raise ValueError('Degenerate adjacent curve samples refused')
    arc=np.r_[0.,np.cumsum(length)]
    n=int(np.ceil(arc[-1]/step_mm))+1
    if n>4096:raise ValueError('Physical resampling exceeds capacity; never silently coarsen')
    u=np.linspace(0.,arc[-1],n)
    q=np.column_stack([np.interp(u,arc,p[:,j]) for j in range(3)])
    q[0],q[-1]=p[0],p[-1]
    return q,u


def gaussian_candidate(points, step_mm, sigma_mm):
    if not np.isfinite(sigma_mm) or sigma_mm<=0:
        raise ValueError('Positive finite smoothing scale in mm required')
    base,u=resample_uniform(points,step_mm)
    if len(base)<3:return base,dict(maximum_parameter_matched_displacement_mm=0.)
    q=gaussian_filter1d(base,sigma_mm/(u[1]-u[0]),axis=0,mode='nearest',truncate=4.)
    # Restore both exact physical endpoints with a smooth linear correction.
    # This is a curve proposal only; its whole interior must still be reviewed.
    t=(u/u[-1])[:,None]
    q+=(base[0]-q[0])*(1-t)+(base[-1]-q[-1])*t
    q[0],q[-1]=base[0],base[-1]
    displacement=float(np.linalg.norm(q-base,axis=1).max())
    q,_=resample_uniform(q,step_mm)
    return q,dict(maximum_parameter_matched_displacement_mm=displacement,
        sigma_mm=float(sigma_mm),step_mm=float(step_mm),endpoint_policy='exact_original_endpoints',
        Gaussian_truncate_sigma=4.,parameter='physical_original_arc_mm',
        continuous_curve_or_instrument_contact_certification=False)


class QualitySurfaceBendPlanner(SurfaceBendPlanner):
    def __init__(self,*args,sigma_schedule_mm=(.25,.5,.75,1.,1.5,2.,3.,4.),
                 maximum_displacement_mm=2.5,**kwargs):
        super().__init__(*args,**kwargs)
        values=np.asarray(sigma_schedule_mm,float)
        if (values.ndim!=1 or not 1<=len(values)<=16 or not np.isfinite(values).all()
                or np.any(values<=0) or np.any(np.diff(values)<=0)
                or not np.isfinite(maximum_displacement_mm) or maximum_displacement_mm<0):
            raise ValueError('Bounded increasing positive scales and finite displacement bound required')
        self.scales=values;self.maximum_displacement_mm=float(maximum_displacement_mm)

    def plan(self,target,*,minimum_bend_radius_mm=0.,**options):
        start=perf_counter()
        report,route,camera=super().plan(target,minimum_bend_radius_mm=minimum_bend_radius_mm,**options)
        threshold=float(minimum_bend_radius_mm)
        quality=dict(algorithm='physical_arc_Gaussian_then_original_full_continuous_wall_mask_review',
            enabled=threshold>0 and options.get('smooth',True),accepted=False,original_curve_minimum_bend_radius_mm=report['measured_minimum_bend_radius_mm'],
            maximum_displacement_mm=self.maximum_displacement_mm,sigma_schedule_mm=self.scales.tolist(),
            endpoints_changed=False,graph_or_mask_changed=False,attempts=[],
            smooth_continuous_curvature_certified=False,production_promoted=False)
        if quality['enabled'] and len(route['arc_mm'])>2 and np.any(route['bend_radius_mm']+1e-5<threshold):
            step=min(float(options.get('sample_mm',.5)),min(self.c.geometry.spacing_xyz)*.25)
            for sigma in self.scales:
                candidate,attempt=gaussian_candidate(route['points_lps_mm'],step,sigma)
                quality['attempts'].append(attempt)
                if attempt['maximum_parameter_matched_displacement_mm']>self.maximum_displacement_mm:
                    attempt['status']='rejected_displacement_bound';continue
                arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(candidate,axis=0),axis=1))]
                # Cheap same-definition curvature screen before expensive walls.
                screen=self.auditor(candidate,arc,np.ones(len(candidate),np.float32),[0.,0.,0.,threshold])
                bad=screen[:,0]+1e-5<threshold
                finite=screen[:,0][np.isfinite(screen[:,0])]
                attempt.update(bend_violations=int(bad.sum()),minimum_bend_radius_mm=float(finite.min()) if len(finite) else None)
                if np.any(bad):attempt['status']='rejected_discrete_bend_constraint';continue
                valid,curve_report,curve=review_curve(self.c,self.region,self.oracle,candidate,
                    report['required_radius_mm']+report['resolution_margin_mm'])
                attempt['curve_review']=curve_report
                if not valid:attempt['status']='rejected_full_wall_crop_or_source_mask_review';continue
                actual=curve['wall_distance_mm'];bounds=curve['accepted_lower_bound_mm']
                conservative=np.maximum(0.,curve['effective_distance_mm']-1e-6)
                if len(bounds):
                    conservative[:-1]=np.minimum(conservative[:-1],bounds)
                    conservative[1:]=np.minimum(conservative[1:],bounds)
                new=dict(points_lps_mm=candidate,arc_mm=arc,radius_mm=round_down_float32(conservative),
                    actual_wall_distance_mm=actual,centerline_point_ids=route['centerline_point_ids'].copy())
                params=[report['forward_window_mm'],report['resolution_margin_mm'],report['required_radius_mm'],threshold]
                rows=self.auditor(candidate,arc,new['radius_mm'],params)
                for i,name in enumerate(AUDIT_FIELDS):new[name]=rows[:,i].copy()
                if np.any(new['bend_radius_mm']+1e-5<threshold):
                    raise RuntimeError('Final curve audit disagrees with curvature screen')
                np.testing.assert_array_equal(candidate[[0,-1]],route['points_lps_mm'][[0,-1]])
                route=new;camera=poses(candidate,arc)
                report.update(length_mm=float(arc[-1]),point_count=len(arc),curve_audit=curve_report,
                    minimum_wall_distance_mm=float(actual.min()),smoothing_accepted=True,
                    measured_minimum_bend_radius_mm=attempt['minimum_bend_radius_mm'])
                report['route_audit']['route_sha256']=route_digest(route)
                validate_stored_audit(route,report)
                quality.update(accepted=True,selected_sigma_mm=float(sigma),
                    minimum_discrete_bend_radius_mm=attempt['minimum_bend_radius_mm'],
                    whole_curve_wall_crop_source_mask_passed=True)
                attempt['status']='accepted_bend_and_full_geometry';break
        quality['proposal_and_review_seconds']=perf_counter()-start-report['runtime_seconds']
        report['curve_quality']=quality
        # Replace the last inherited query record with the exact audited output
        # consumed by the unchanged prefix controller; retain graph diagnostics.
        previous=self.history[-1]
        diagnostics=dict(previous['diagnostics'])
        if quality['accepted']:diagnostics['curve_audit']=curve
        self.history[-1]=dict(previous,report=report.copy(),route={k:v.copy() for k,v in route.items()},
            camera={k:v.copy() for k,v in camera.items()},diagnostics=diagnostics)
        return report,route,camera
