"""Manual DFX EDT, path planning and camera generation; no rendering."""
from pathlib import Path
import argparse,json,sys,time
from runtime_extended import ROOT,SYSTEM,Session
sys.path.insert(0,str(SYSTEM/'modules/navigation'))
from navigation.pipeline import prepare,choose_target,run_route
from pl.route_runtime import RoutePlanner
from pl.runtime import XRTSession
class DFXRoutePlanner(RoutePlanner):
    def plan(self,*args,**kwargs):
        report,route,camera=super().plan(*args,**kwargs)
        job=report['pl_job']
        job['useful_output_words']=job['wire_output_words']
        job['useful_output_bytes']=job['wire_output_bytes']
        job['wire_output_words']=job['dma_output_words']
        job['wire_output_bytes']=job['dma_output_words']*64
        return report,route,camera
class NavigationSession(Session,XRTSession):
    """Use the DFX session while retaining the geometry helper's PL type tag."""
    pass
def main():
    p=argparse.ArgumentParser();p.add_argument('--airway',type=Path,default=SYSTEM/'fixtures/own_ct/masks/airway_mask.nii.gz');p.add_argument('--lesion',type=Path,default=SYSTEM/'fixtures/own_ct/masks/nodule_mask.nii.gz');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--lesion-index',type=int,default=0);p.add_argument('--target-lps',nargs=3,type=float)
    p.add_argument('--scope-diameter-mm',type=float,default=1.);p.add_argument('--safety-margin-mm',type=float,default=.2);p.add_argument('--sample-mm',type=float,default=.5);a=p.parse_args()
    a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=False);start=time.perf_counter()
    with NavigationSession() as session:
        c,tree=prepare(a.airway,a.output,backend='pl',session=session)
        target=choose_target(c,lesion_path=a.lesion if a.target_lps is None else None,lesion_index=a.lesion_index,target_lps_mm=a.target_lps)
        planner=DFXRoutePlanner(c,session)
        result=run_route(c,target,a.output,planner,scope_diameter_mm=a.scope_diameter_mm,safety_margin_mm=a.safety_margin_mm,sample_mm=a.sample_mm,smooth=True)
        session.report(a.output/'session.json')
    report={'status':'completed','backend':'dfx_pl','edt_backend':'pl','route_backend':'pl','camera_backend':'pl','total_seconds':time.perf_counter()-start,'route_status':result['status'],'rendering':False}
    (a.output/'dfx_report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
