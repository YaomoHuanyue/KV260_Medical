"""Compile source-bound active-surface UI separately from the accepted default."""
from pathlib import Path
import json,subprocess,sys,traceback
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json


def main():
    folder=ROOT/'ui/releases/feature_completion_r6';out=folder/'build_complete_scene_r14';out.mkdir(exist_ok=False)
    closure=ROOT/'modules/surface_route/native_UI_source_closure_r14.json';bound=json.loads(closure.read_text())['files_sha256']
    try:
        for name,h in bound.items():assert sha(ROOT/name)==h,name
        flags=subprocess.check_output(['pkg-config','--cflags','--libs','Qt5Widgets','Qt5OpenGL','Qt5Test'],text=True).split()
        argv=['g++','-std=c++17','-O2','-fPIC','-pthread','-mcpu=cortex-a53','-I',str(folder/'src'),
            *[str(folder/'src'/n) for n in ('main_complete_scene_r14.cpp','views_batch_r3.cpp','pl_scope_complete_r9.cpp','pl_composite_exact_speed_r8.cpp')],
            *flags,'-o',str(out/'medical_ui')]
        with (out/'build.log').open('xb') as log:subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        for name,h in bound.items():assert sha(ROOT/name)==h,name
        write_json(out/'build.json',dict(status='compiled_separate_active_surface_native_UI',argv=argv,
            source_closure_sha256=sha(closure),source_sha256=bound,binary_sha256=sha(out/'medical_ui'),
            builder_sha256=sha(Path(__file__)),production_promoted=False,new_bitstream=False,PL_access=False))
        print('R14 native UI compiled',flush=True)
    except BaseException as error:write_json(out/'failure.json',dict(error=str(error),traceback=traceback.format_exc()));raise


if __name__=='__main__':main()
