"""Build the preview correction with retained objects for later UI iterations."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json,subprocess,sys,traceback
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json


def main():
    folder=ROOT/'ui/releases/feature_completion_r6';out=folder/'build_complete_scene_r14d';out.mkdir(exist_ok=False)
    closure=ROOT/'modules/surface_route/native_UI_source_closure_r14d.json';bound=json.loads(closure.read_text())['files_sha256']
    try:
        for n,h in bound.items():assert sha(ROOT/n)==h,n
        flags=subprocess.check_output(['pkg-config','--cflags','Qt5Widgets','Qt5OpenGL','Qt5Test'],text=True).split()
        libs=subprocess.check_output(['pkg-config','--libs','Qt5Widgets','Qt5OpenGL','Qt5Test'],text=True).split()
        names=['main_complete_scene_r14d.cpp','views_batch_r3.cpp','pl_scope_complete_r9.cpp','pl_composite_exact_speed_r8.cpp'];commands=[]
        def compile_one(name):
            obj=out/(Path(name).stem+'.o');level='-O1' if name.startswith('main_') else '-O2'
            argv=['g++','-std=c++17',level,'-fPIC','-pthread','-mcpu=cortex-a53','-I',str(folder/'src'),*flags,'-c',str(folder/'src'/name),'-o',str(obj)]
            with (out/(Path(name).stem+'.log')).open('xb') as log:subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            return argv,obj
        with ThreadPoolExecutor(max_workers=2) as pool:built=list(pool.map(compile_one,names))
        argv=['g++','-pthread',*[str(obj) for _,obj in built],*libs,'-o',str(out/'medical_ui')]
        with (out/'build.log').open('xb') as log:subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        for n,h in bound.items():assert sha(ROOT/n)==h,n
        write_json(out/'build.json',dict(status='compiled_preview_target_native_UI',argv=argv,compile_argv=[a for a,_ in built],
            source_closure_sha256=sha(closure),source_sha256=bound,binary_sha256=sha(out/'medical_ui'),
            object_sha256={p.name:sha(p) for _,p in built},builder_sha256=sha(Path(__file__)),
            GUI_control_compiled_O1_renderer_and_transports_O2=True,production_promoted=False,new_bitstream=False,PL_access=False))
        print('R14d native preview correction compiled',flush=True)
    except BaseException as error:write_json(out/'failure.json',dict(error=str(error),traceback=traceback.format_exc()));raise


if __name__=='__main__':main()
