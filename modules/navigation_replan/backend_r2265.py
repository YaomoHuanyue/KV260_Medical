"""QProcess adapter for explicit replanning and the existing surface actions."""
from pathlib import Path
import argparse,json,sys,uuid
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from modules.navigation_replan.action_r2265 import produce,verify_replan
from modules.navigation_replan.no_route_r2265 import NoRoute,verify as verify_no_route
from modules.surface_route.verification_session_r15 import VerificationSession
def event(name,**values):
    print(json.dumps(dict(event=name,**values),ensure_ascii=False,allow_nan=False),flush=True)
def main():
    action=sys.argv[1] if len(sys.argv)>1 else ''
    if action not in ('replan','prepare'):
        from modules.surface_route.active_backend_r20 import main as legacy
        # Validate any retained explicit-replan receipt before an old action.
        if '--active-scene' in sys.argv:
            active=Path(sys.argv[sys.argv.index('--active-scene')+1])
            if json.loads(active.read_text(encoding='utf8')).get('complete_surface'):
                verify_replan(active)
        return legacy()
    p=argparse.ArgumentParser();p.add_argument('action',choices=('replan','prepare'))
    p.add_argument('--active-scene',type=Path,required=True);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--result',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--lesion',type=int);p.add_argument('--diameter',type=float)
    p.add_argument('--margin',type=float);p.add_argument('--minimum-bend',type=float)
    a=p.parse_args();scene=verify_replan(a.active_scene)
    if Path(scene['input']).resolve()!=a.input.resolve() or (a.result and Path(scene['result']).resolve()!=a.result.resolve()):
        raise ValueError('Selected CT/result differs from current scene')
    if a.action=='prepare':return a.active_scene,scene
    if any(v is None for v in (a.lesion,a.diameter,a.margin,a.minimum_bend)):
        raise ValueError('Explicit target, diameter, margin and bend constraint required')
    output=a.output.resolve() if a.output else ROOT/'ui/cache'/('navigation_replan_'+uuid.uuid4().hex)
    event('started',output=str(output))
    path=produce(a.active_scene,output,dict(lesion=a.lesion,diameter=a.diameter,margin=a.margin,minimum_bend=a.minimum_bend),event)
    return (path.receipt,path) if isinstance(path,NoRoute) else (path,verify_replan(path))
if __name__=='__main__':
    try:
        with VerificationSession() as session:path,scene=main()
        event('verification_reuse',**session.metrics())
        if isinstance(scene,NoRoute):
            verified=verify_no_route(path)
            event('navigation_unavailable',receipt=str(path),report=verified.report,options=verified.options,parent_scene=str(verified.parent_scene),PL_access=False)
            event('completed',status='unreachable')
        else:
            event('prepared',scene=str(path.resolve()),revision=scene['complete_surface']['revision'],
                PL_access=('quality' in sys.argv and '--source' in sys.argv))
            event('completed',status='passed')
    except Exception as error:event('error',text=str(error));raise
