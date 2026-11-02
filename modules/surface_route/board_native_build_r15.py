"""Compile changed UI only; copy/link SHA-verified unchanged R14d objects."""
from pathlib import Path
import json,shutil,subprocess,sys,traceback

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json


def main():
    folder=ROOT/'ui/releases/feature_completion_r6';out=folder/'build_complete_scene_r15';out.mkdir(exist_ok=False)
    parent=folder/'build_complete_scene_r14d';old=json.loads((parent/'build.json').read_text())
    closure=ROOT/'modules/surface_route/native_UI_source_closure_r15.json';bound=json.loads(closure.read_text())['files_sha256']
    try:
        def verify():
            assert sha(parent/'medical_ui')==old['binary_sha256']
            for n,h in old['source_sha256'].items():assert sha(ROOT/n)==h,n
            for n,h in bound.items():assert sha(ROOT/n)==h,n
            for n,h in old['object_sha256'].items():assert sha(parent/n)==h,n
        verify()
        flags=subprocess.check_output(['pkg-config','--cflags','Qt5Widgets','Qt5OpenGL','Qt5Test'],text=True).split()
        libs=subprocess.check_output(['pkg-config','--libs','Qt5Widgets','Qt5OpenGL','Qt5Test'],text=True).split()
        obj=out/'main_complete_scene_r15.o'
        argv=['g++','-std=c++17','-O1','-fPIC','-pthread','-mcpu=cortex-a53','-I',str(folder/'src'),
              *flags,'-c',str(folder/'src/main_complete_scene_r15.cpp'),'-o',str(obj)]
        with (out/'main_complete_scene_r15.log').open('xb') as log:subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        objects=[obj];reused={}
        for name in ('views_batch_r3.o','pl_scope_complete_r9.o','pl_composite_exact_speed_r8.o'):
            source=parent/name;dest=out/name;shutil.copyfile(source,dest)
            assert sha(dest)==old['object_sha256'][name];objects.append(dest);reused[name]=sha(dest)
        link=['g++','-pthread',*[str(p) for p in objects],*libs,'-o',str(out/'medical_ui')]
        with (out/'build.log').open('xb') as log:subprocess.run(link,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        verify()
        write_json(out/'build.json',dict(status='compiled_scoped_verification_native_UI_with_verified_unchanged_render_objects',
            argv=link,compile_argv=[argv],source_closure_sha256=sha(closure),source_sha256=bound,
            object_sha256={p.name:sha(p) for p in objects},binary_sha256=sha(out/'medical_ui'),
            reused_unchanged_objects_sha256=reused,parent_build_sha256=sha(parent/'build.json'),
            parent_objects_complete_source_closure_verified=True,builder_sha256=sha(Path(__file__)),
            GUI_control_compiled_O1_renderer_and_transports_O2=True,production_promoted=False,new_bitstream=False,PL_access=False))
        print('R15 native adapter compiled; renderer and transports identical',flush=True)
    except BaseException as error:write_json(out/'failure.json',dict(error=str(error),traceback=traceback.format_exc()));raise


if __name__=='__main__':main()
