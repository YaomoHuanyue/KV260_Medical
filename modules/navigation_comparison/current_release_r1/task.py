"""Audited PL route queries; PS selects verified prefixes and formats comparisons."""
from pathlib import Path
import argparse,json,sys,time
import numpy as np
from scipy.spatial import cKDTree

SYSTEM=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(SYSTEM/'dfx/medical'))
sys.path.insert(0,str(SYSTEM/'modules/navigation'))
sys.path.insert(0,str(SYSTEM/'ui'))
sys.path.insert(0,str(SYSTEM/'dfx/route_audit_speed'))
from navigation_session import NavigationSession
from protocol import AuditRoutePlanner as DFXRoutePlanner
from checked_plan import checked_plan
from navigation.pipeline import prepare,choose_target,run_route
from navigation.planner import Target

class CheckedPlanner:
    def __init__(self,planner,threshold):self.planner=planner;self.c=planner.c;self.scene_info=planner.scene_info;self.threshold=threshold
    def plan(self,target,**options):return checked_plan(self.planner,target,self.threshold,**options)

def summary(report):
    return {k:report.get(k) for k in ('status','reason','scope_diameter_mm','safety_margin_mm','minimum_bend_radius_mm',
        'length_mm','final_target_gap_mm','minimum_adjusted_radius_mm','measured_minimum_bend_radius_mm','selected_endpoint_id')}

def comparisons(planner,target,threshold,options):
    profiles=[]
    for diameter in sorted(set([options['scope_diameter_mm'],1.2,1.8,2.8,4.])):
        r,_,_=checked_plan(planner,target,threshold,**dict(options,scope_diameter_mm=diameter));profiles.append(summary(r))
    c=planner.c;degree=np.bincount(c.edges.ravel(),minlength=len(c.points_lps_mm))
    ids=np.flatnonzero((degree<=1)&(c.components==c.components[c.root])&(np.arange(len(degree))!=c.root))
    gaps=cKDTree(target.points_lps_mm).query(c.points_lps_mm[ids])[0] if len(ids) else np.empty(0)
    rows=[];seen=set()
    for i in np.argsort(gaps)[:8]:
        index=int(ids[i]);t=Target('manual_point',c.points_lps_mm[[index]],{})
        r,route,_=checked_plan(planner,t,threshold,**options)
        if r['status'] in ('route_found','limited_reach') and len(route['points_lps_mm'])>1 and r['minimum_adjusted_radius_mm']+1e-5>=r['required_radius_mm']:
            key=tuple(np.round(route['points_lps_mm'][-1],4))
            if key in seen:continue
            seen.add(key)
            r['final_target_gap_mm']=float(cKDTree(target.points_lps_mm).query(route['points_lps_mm'][-1])[0])
            row=summary(r);row['requested_approach_endpoint_id']=index;row['endpoint_id']=int(r['selected_endpoint_id']);row['score']=r['final_target_gap_mm']+.02*r['length_mm'];rows.append(row)
    rows.sort(key=lambda r:r['score'])
    # These are airway approach endpoints, never alternative paths into tissue.
    return dict(kind='PL instrument clearance comparison',profiles=profiles),dict(kind='verified airway approach endpoint alternatives',routes=rows)

def main():
    p=argparse.ArgumentParser();p.add_argument('--airway',type=Path,required=True);p.add_argument('--lesion',type=Path,required=True);p.add_argument('--lesion-index',type=int,default=0)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--scope-diameter-mm',type=float,default=1.);p.add_argument('--safety-margin-mm',type=float,default=.2)
    p.add_argument('--minimum-bend-radius-mm',type=float,default=0.);p.add_argument('--compare',action='store_true')
    p.add_argument('--comparison-profile-provider',choices=['PS4','verified-R1PL'],default='verified-R1PL');p.add_argument('--edt-core',choices=['axis','volume'],default='volume');p.add_argument('--experimental-volume',action='store_true');a=p.parse_args()
    if a.experimental_volume and a.edt_core!='volume':p.error('--experimental-volume requires --edt-core volume')
    sys.path.insert(0,str(SYSTEM))
    if a.compare and a.comparison_profile_provider=='verified-R1PL':
        from modules.navigation_comparison.current_release_r1.runtime import verify_current
        verify_current()
    output=a.output.resolve();output.mkdir(parents=True,exist_ok=False);start=time.perf_counter()
    if a.edt_core=='volume':
        sys.path.insert(0,str(SYSTEM/'dfx/edt_volume'))
        from volume_navigation import VolumeNavigationSession
        task_session=VolumeNavigationSession(experimental=a.experimental_volume)
    else:task_session=NavigationSession()
    with task_session as session:
        c,tree=prepare(a.airway,output,backend='pl',session=session)
        from navigation.anatomical import save as save_anatomical
        anatomy=save_anatomical(c,output)
        target=choose_target(c,lesion_path=a.lesion,lesion_index=a.lesion_index)
        planner=DFXRoutePlanner(c,session)
        options=dict(scope_diameter_mm=a.scope_diameter_mm,safety_margin_mm=a.safety_margin_mm,sample_mm=.5,smooth=True)
        if a.compare:
            profiles,alternatives=comparisons(planner,target,a.minimum_bend_radius_mm,options)
            for name,value in [('instrument_profiles',profiles),('alternative_routes',alternatives)]:
                (output/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf-8')
        report=run_route(c,target,output,CheckedPlanner(planner,a.minimum_bend_radius_mm),**options)
        session.report(output/'session.json')
    comparison_backend=None;comparison_runtime=None
    if a.compare:
        # VolumeNavigationSession has released its PL lock before opening any
        # distinct profile session. Do not nest reconfigurable module owners.
        sys.path.insert(0,str(SYSTEM/'modules/navigation_comparison'))
        from produce_r1 import produce,save
        if a.comparison_profile_provider=='verified-R1PL':
            sys.path.insert(0,str(SYSTEM/'dfx/navigation_profile'))
            from modules.navigation_comparison.current_release_r1.runtime import Session as ProfileSession
            with ProfileSession() as profile:
                whole,other,arrays=produce(c,target,profile.solve,provider_kind='verified_PL_R1',
                    scope_diameter_mm=a.scope_diameter_mm,safety_margin_mm=a.safety_margin_mm,
                    minimum_bend_radius_mm=a.minimum_bend_radius_mm)
        else:
            from profile_session_r2 import ProfilePS
            profile=ProfilePS()
            provider=lambda g,d,m,w:profile.solve(g,d,m,w,threads=4)[1:]
            whole,other,arrays=produce(c,target,provider,provider_kind='optimized_PS4',
                scope_diameter_mm=a.scope_diameter_mm,safety_margin_mm=a.safety_margin_mm,
                minimum_bend_radius_mm=a.minimum_bend_radius_mm)
        save(output,whole,other,arrays);comparison_backend=whole['profile_backend']
        comparison_runtime=dict(provider=comparison_backend,PL_calls=getattr(profile,'calls',[]),
            raw_nodes=whole['raw_nodes'],raw_undirected_edges=whole['raw_undirected_edges'],
            distances_precision='FP64',silent_PS_fallback=False,
            PL_session_restored=bool(getattr(profile,'restored',False)))
    result=dict(status='completed',backend='dfx_pl',edt_backend='pl',route_backend='pl',camera_backend='pl',
        total_seconds=time.perf_counter()-start,route_status=report['status'],minimum_bend_radius_mm=a.minimum_bend_radius_mm,
        bend_audit_backend=report['route_audit']['backend'],forward_clearance_backend=report['route_audit']['backend'],rendering=False)
    result['anatomical_generation_backend']='PS_sparse_graph_with_PL_EDT_upstream'
    result['whole_comparison_backend']=comparison_backend
    result['whole_comparison_runtime']=comparison_runtime
    result['actual_navigation_route_replaced_by_comparison']=False
    result['edt_core']='C8_volume' if a.edt_core=='volume' else 'C3_axis'
    result['experimental_volume_candidate']=a.experimental_volume
    result['anatomical_generation_seconds']=anatomy['computation']['seconds']
    (output/'dfx_report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
