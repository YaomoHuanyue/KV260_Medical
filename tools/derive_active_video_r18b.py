"""Permit Qt's extra read-created nulls, preserve all declared scene values."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def emit(name,data):
    with (ROOT/name).open('x',encoding='utf-8',newline='\n') as f:f.write(data)
def main():
    edits=[]
    def change(parent,child,changes):
        source=(ROOT/parent).read_text(encoding='utf-8')
        for item in changes:
            before,after=item[:2];count=item[2] if len(item)>2 else 1
            assert source.count(before)==count,(parent,before);source=source.replace(before,after)
        emit(child,source);edits.append(dict(parent=parent,parent_sha256=sha(ROOT/parent),child=child,child_sha256=sha(ROOT/child),changes=changes))
    header='modules/navigation_media/active_binding_r18.hpp'
    helper='''inline bool sameSavedVideoScene(const QJsonObject&saved,const QJsonObject&displayed,QStringList*extraNulls=nullptr){
 // QJsonObject non-const operator[] inserts null for a missing read. Only
 // these additional top-level nulls are ignored; all saved values stay exact.
 for(auto it=saved.begin();it!=saved.end();++it)
  if(!displayed.contains(it.key())||displayed.value(it.key())!=it.value())return false;
 for(auto it=displayed.begin();it!=displayed.end();++it)if(!saved.contains(it.key())){
  if(!it.value().isNull())return false;
  if(extraNulls)extraNulls->append(it.key());
 }
 return true;
}
'''
    change(header,header.replace('r18.','r18b.'),[
        ('// The UI scene has already passed',helper+'// The UI scene has already passed'),
        (' if(mediaObject(scenePath)!=scene)throw std::runtime_error("Displayed and saved video scene differ");',
         ' QStringList extraNulls;if(!sameSavedVideoScene(mediaObject(scenePath),scene,&extraNulls))throw std::runtime_error("Displayed and saved video scene differ");'),
        ('{"render_backend","PL_C9"},{"quality",quality}',
         '{"render_backend","PL_C9"},{"extra_UI_null_keys",QJsonArray::fromStringList(extraNulls)},{"quality",quality}')])
    main='ui/releases/feature_completion_r6/src/main_complete_scene_r18.cpp'
    change(main,main.replace('r18.cpp','r18b.cpp'),[('active_binding_r18.hpp','active_binding_r18b.hpp')])
    build='modules/surface_route/board_native_build_r18.py'
    change(build,build.replace('r18.py','r18b.py'),[
        ("out=folder/'build_complete_scene_r18'","out=folder/'build_complete_scene_r18b'"),
        ("parent=folder/'build_complete_scene_r17'","parent=folder/'build_complete_scene_r18'"),
        ('native_UI_source_closure_r18.json','native_UI_source_closure_r18b.json'),
        ("obj=out/'main_complete_scene_r18.o'","obj=out/'main_complete_scene_r18b.o'"),
        ("src/main_complete_scene_r18.cpp","src/main_complete_scene_r18b.cpp"),
        ("out/'main_complete_scene_r18.log'","out/'main_complete_scene_r18b.log'"),
        ('R18 native adapter','R18b native adapter')])
    trial='tools/active_video_trial_r18.py'
    change(trial,trial.replace('r18.py','r18b.py'),[
        ("active_C9_video_ARM_r18'","active_C9_video_ARM_r18b'"),
        ("old=state['UI'];ready(old);", "old=json.loads((ROOT/'modules/navigation_media/results/active_C9_video_ARM_r18/fallback_review/live.json').read_text());ready(old);"),
        ('build_complete_scene_r18/','build_complete_scene_r18b/',3),
        ('R18 current C9','R18b current C9')])
    parent=ROOT/'modules/surface_route/native_UI_source_closure_r18.json'
    files=json.loads(parent.read_text())['files_sha256']
    for n,h in files.items():assert sha(ROOT/n)==h,n
    names=[e['child'] for e in edits]+['tools/derive_active_video_r18b.py']
    files.update({n:sha(ROOT/n) for n in names})
    emit('modules/surface_route/native_UI_source_closure_r18b.json',json.dumps(dict(files_sha256=files,parent_sha256=sha(parent),
        change='ignore only Qt read-created extra null keys in saved-scene equality',production_promoted=False),indent=2)+'\n')
    emit('modules/navigation_media/active_video_derivation_r18b.json',json.dumps(dict(edits=edits,new_bitstream=False),indent=2)+'\n')
    print('R18b preserves declared scene values and Qt extra-null compatibility')
if __name__=='__main__':main()
