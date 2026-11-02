"""Async native action adapter; it never initializes XRT or loads a bitstream."""
from pathlib import Path
import argparse,json,sys,uuid,os
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from modules.surface_route.active_actions_r15 import verify_active_scene,compare_action,selected_action
from modules.surface_route.verification_session_r15 import sha,VerificationSession

def event(name,**values):print(json.dumps(dict(event=name,**values),ensure_ascii=False,allow_nan=False),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','comparison','selected-path'])
    p.add_argument('--active-scene',type=Path,required=True);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--result',type=Path);p.add_argument('--lesion',type=int);p.add_argument('--diameter',type=float,default=1.)
    p.add_argument('--margin',type=float,default=.2);p.add_argument('--minimum-bend',type=float,default=0.)
    p.add_argument('--group',type=int);p.add_argument('--candidate',type=int);p.add_argument('--output',type=Path)
    a=p.parse_args();scene=verify_active_scene(a.active_scene)
    if Path(scene['input']).resolve()!=a.input.resolve() or sha(a.input)!=scene['input_sha256']:
        raise ValueError('Selected CT differs from active scene')
    if a.result and Path(scene['result']).resolve()!=a.result.resolve():raise ValueError('Selected result differs from active scene')
    if a.action=='prepare':path=a.active_scene
    else:
        output=a.output.resolve() if a.output else ROOT/'ui/cache'/('surface_action_'+uuid.uuid4().hex)
        if not output.is_relative_to(ROOT):raise ValueError('Project action output required')
        event('started',output=str(output));event('progress',text='正在按当前表面计算，完成后一次更新场景')
        if a.action=='comparison':
            if a.lesion is None:raise ValueError('Explicit target required')
            compare_action(a.active_scene,output,dict(lesion=a.lesion,diameter=a.diameter,margin=a.margin,minimum_bend=a.minimum_bend))
        else:
            if a.group is None or a.candidate is None:raise ValueError('Explicit selected Pareto path required')
            selected_action(a.active_scene,output,a.group,a.candidate)
        path=output/'UI/scene.json'
    scene=verify_active_scene(path)
    return path,scene

if __name__=='__main__':
    try:
        with VerificationSession() as session:
            path,scene=main()
        event('verification_reuse',**session.metrics())
        event('prepared',scene=str(path.resolve()),revision=scene['complete_surface']['revision'],PL_access=False)
        event('completed',status='passed')
    except Exception as error:event('error',text=str(error));raise
