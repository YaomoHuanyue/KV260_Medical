"""Durable R14 binding, native build and real HDMI/C9 action trial."""
from pathlib import Path
import json,subprocess,sys,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json

def main():
    out=ROOT/'modules/surface_route/results/active_surface_trial_ARM_r14d';out.mkdir(exist_ok=False)
    closure=ROOT/'modules/surface_route/native_UI_source_closure_r14d.json'
    for n,h in json.loads(closure.read_text())['files_sha256'].items():assert sha(ROOT/n)==h,n
    try:
        for script,args in [('modules/surface_route/test_capabilities_r14c.py',['--output','modules/surface_route/results/capabilities_ARM_r14d.json']),('modules/surface_route/test_active_binding_r14.py',['--output','modules/surface_route/results/active_binding_ARM_r14d.json']),
            ('modules/surface_route/board_native_build_r14d.py',[]),('tools/active_surface_GUI_trial_r14d.py',[])]:
            print('RUN',script,flush=True);subprocess.run([str(ROOT/'.venv/bin/python'),'-X','utf8',str(ROOT/script),*args],cwd=ROOT,check=True)
        proof=['modules/surface_route/results/active_binding_ARM_r14d.json',
            'ui/releases/feature_completion_r6/build_complete_scene_r14d/build.json',
            'modules/surface_route/results/native_active_surface_GUI_ARM_r14d/acceptance.json']
        write_json(out/'acceptance.json',dict(status='ARM_current_surface_binding_build_HDMI_actions_and_PS_PL_replay_passed',
            evidence_sha256={n:sha(ROOT/n) for n in proof},source_closure_sha256=sha(closure),
            supervisor_sha256=sha(Path(__file__)),production_promoted=False))
    except BaseException as error:write_json(out/'failure.json',dict(error=str(error),traceback=traceback.format_exc()));raise

if __name__=='__main__':main()
