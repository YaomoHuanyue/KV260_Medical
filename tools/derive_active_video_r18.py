"""Versioned C9 dispatch and source binding; preserve legacy video and UI."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,data):
 p=ROOT/name
 with p.open('x',encoding='utf-8',newline='\n') as f:f.write(data)
def main():
 edits=[]
 parent='modules/navigation_media/UI_feature_r4.inc';source=(ROOT/parent).read_text(encoding='utf-8')
 replacements=[
  (' QImage videoLastImage;',' QJsonObject videoActiveBinding;\n QImage videoLastImage;',1),
  ('&&QFileInfo::exists(source+"/navigation/route.json")',
   '&&QFileInfo::exists(scene.contains("complete_surface")?scene["complete_surface"].toObject()["bundle"].toString()+"/route.json":source+"/navigation/route.json")',1),
  ('   videoSources={};for(QString path:{scenePath,source+"/navigation/route.json",source+"/segmentation/airway_mask.nii.gz",root+"/dfx/surface/release/manifest.json"})videoSources[path]=videoHash(path);',
   '''   videoSources={};videoActiveBinding={};
   if(scene.contains("complete_surface"))videoActiveBinding=navigation_media::activeVideoBinding(root,scenePath,scene,videoSources,[this](QString path){return videoHash(path);});
   else for(QString path:{scenePath,source+"/navigation/route.json",source+"/segmentation/airway_mask.nii.gz",root+"/dfx/surface/release/manifest.json"})videoSources[path]=videoHash(path);''',1),
  ('  if(first)plScope->start(source,request);else plScope->request(request);videoProgressClock.restart();',
   '''  if(first){if(!videoActiveBinding.isEmpty())plScope->startScene(videoActiveBinding["bundle"].toString(),videoActiveBinding["revision"].toString(),request);
   else plScope->start(source,request);}else plScope->request(request);videoProgressClock.restart();''',1),
  ('  videoProgressClock.restart();videoLastMeta=meta;',
   '  if(!videoActiveBinding.isEmpty()&&!navigation_media::activeVideoFrame(videoActiveBinding,meta)){videoEnd(u("视频收到其他表面或路径的帧"));return;}\n  videoProgressClock.restart();videoLastMeta=meta;',1),
  ('    QJsonObject linkedProof;QImage overviewColor;',
   '    QJsonObject videoHUD=videoActiveBinding.isEmpty()?(at<hud.size()?hud[at].toObject():QJsonObject{}):shown["hud"].toObject();\n    QJsonObject linkedProof;QImage overviewColor;',1),
  ('videoPaneSize,shown,at<hud.size()?hud[at].toObject():QJsonObject{},videoPlan->length)',
   'videoPaneSize,shown,videoHUD,videoPlan->length)',2),
  ('   {"linked_overview_enabled",videoLinked},{"pane_output_size",',
   '   {"active_scene_binding",videoActiveBinding},{"linked_overview_enabled",videoLinked},{"pane_output_size",',1),
  ('videoLinked?"native_C6_and_linked_overview_FBOs_aspect_preserved":"native_C6_color_FBO_aspect_preserved"',
   'videoActiveBinding.isEmpty()?(videoLinked?"native_C6_and_linked_overview_FBOs_aspect_preserved":"native_C6_color_FBO_aspect_preserved"):(videoLinked?"native_C9_and_linked_overview_FBOs_aspect_preserved":"native_C9_color_FBO_aspect_preserved")',1),
  ('{"PL",QJsonArray{"C6 wall intersection","target visibility","outline","depth-aware normals"}}',
   '{"PL",videoActiveBinding.isEmpty()?QJsonArray{"C6 wall intersection","target visibility","outline","depth-aware normals"}:QJsonArray{"C9 scalar wall intersection","current target visibility","outline","scalar-gradient normals"}}',1),
  ('{"physical_mouse_verified",false}});',
   '{"physical_mouse_verified",false},{"active_scene_binding",videoActiveBinding}});',1)]
 for old,new,count in replacements:
  assert source.count(old)==count,(old,source.count(old));source=source.replace(old,new)
 child='modules/navigation_media/UI_feature_C9_r18.inc';write(child,source)
 edits.append(dict(parent=parent,parent_sha256=sha(ROOT/parent),child=child,child_sha256=sha(ROOT/child),replacements=replacements))
 parent='ui/releases/feature_completion_r6/src/main_complete_scene_r17.cpp';child=parent.replace('_r17.cpp','_r18.cpp')
 source=(ROOT/parent).read_text(encoding='utf-8')
 changes=[('modules/navigation_media/UI_feature_r4.inc','modules/navigation_media/UI_feature_C9_r18.inc'),
  ('#include "../../../../modules/navigation_media/encoder_UI_r3.hpp"','#include "../../../../modules/navigation_media/encoder_UI_r3.hpp"\n#include "../../../../modules/navigation_media/active_binding_r18.hpp"'),
  ('for(auto*b:{navButton,batchButton,videoButton,recoveryButton})','for(auto*b:{navButton,batchButton,recoveryButton})')]
 for old,new in changes:assert source.count(old)==1,old;source=source.replace(old,new)
 write(child,source);edits.append(dict(parent=parent,parent_sha256=sha(ROOT/parent),child=child,child_sha256=sha(ROOT/child),changes=changes))
 parent='modules/surface_route/board_native_build_r17.py';child=parent.replace('_r17.py','_r18.py')
 source=(ROOT/parent).read_text(encoding='utf-8').replace('build_complete_scene_r17','build_complete_scene_r18').replace('build_complete_scene_r16','build_complete_scene_r17').replace('native_UI_source_closure_r17','native_UI_source_closure_r18').replace('main_complete_scene_r17','main_complete_scene_r18').replace('R17 native adapter','R18 native adapter')
 write(child,source);edits.append(dict(parent=parent,parent_sha256=sha(ROOT/parent),child=child,child_sha256=sha(ROOT/child),change='versioned main-only build; reuse verified unchanged R17 renderer/transport objects'))
 parent=ROOT/'modules/surface_route/native_UI_source_closure_r17.json';files=json.loads(parent.read_text())['files_sha256'].copy()
 for n,h in files.items():assert sha(ROOT/n)==h,n
 names=[e['child'] for e in edits]+['modules/navigation_media/active_binding_r18.hpp','tools/derive_active_video_r18.py']
 files.update({n:sha(ROOT/n) for n in names})
 write('modules/surface_route/native_UI_source_closure_r18.json',json.dumps(dict(files_sha256=files,parent_sha256=sha(parent),
  change='active C9 single and linked route video; same UI renderer and cooperative transports',production_promoted=False),indent=2)+'\n')
 write('modules/navigation_media/active_video_derivation_r18.json',json.dumps(dict(edits=edits,new_bitstream=False),indent=2)+'\n')
 print('Derived active C9 video; legacy implementation retained')
if __name__=='__main__':main()
