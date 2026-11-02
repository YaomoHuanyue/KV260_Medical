from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'ui/releases/feature_completion_r6/src'
def update(text,a,b):
    if text.count(a)!=1:raise ValueError((a,text.count(a)))
    return text.replace(a,b)
def main():
    text=(SRC/'main_complete_scene_r15.cpp').read_text(encoding='utf-8')
    changes=[
      ('#include "active_surface_UI_r15.inc"','#include "active_surface_UI_r16.inc"\n#include "surface_quality_UI_r16.inc"'),
      ('active_backend_r15.py','active_backend_r16.py'),
      ('restoreSurfaceComparisonControls();record("scene_loaded");','restoreSurfaceComparisonControls();restoreQualityControls();record("scene_loaded");'),
      ('value=value||videoPending||videoRunning||batchRunning;','value=value||videoPending||videoRunning||batchRunning;qualityBusy(value);'),
      ('for(auto*b:{rebuildButton,navButton,batchButton,videoButton,recoveryButton})','for(auto*b:{navButton,batchButton,videoButton,recoveryButton})'),
      ('  if(scene.contains("complete_surface")&&mode=="comparison")','  if(scene.contains("complete_surface")&&mode=="reconstruction"){startSurfaceAction("quality");return;}\n  if(scene.contains("complete_surface")&&mode=="comparison")'),
      ('meshLayout->addWidget(quality);auto*analysisTools','qualityControls(meshLayout);meshLayout->addWidget(quality);auto*analysisTools'),
      ('if(activeSurfaceTesting){QTimer::singleShot(300,this,[this]{surfaceTestAdvance();});}else if(completeSceneGuiTesting)',
       'if(qualityTesting){QTimer::singleShot(300,this,[this]{qualityTestAdvance();});}else if(activeSurfaceTesting){QTimer::singleShot(300,this,[this]{surfaceTestAdvance();});}else if(completeSceneGuiTesting)'),
    ]
    for a,b in changes:text=update(text,a,b)
    with (SRC/'main_complete_scene_r16.cpp').open('x',encoding='utf-8',newline='\n') as f:f.write(text)
    text=(SRC/'active_surface_UI_r15.inc').read_text(encoding='utf-8')
    changes=[
      ('active_backend_r15.py','active_backend_r16.py'),
      ('if(processing()||!scene.contains("complete_surface"))return;','if(processing()||(action!="quality"&&!scene.contains("complete_surface")))return;'),
      ('  if(action=="selected-path")args<<',
       '  if(action=="quality")args<<"--source"<<(surfaceQuality->currentIndex()<2?"accepted_binary":"network_probability")<<"--quality"<<(surfaceQuality->currentIndex()%2?"ultra":"high");\n  if(action=="selected-path")args<<'),
      ('  message(action=="comparison"?', '  message(action=="quality"?u("正在重新生成 PL 气道表面并同步导航"):action=="comparison"?'),
      ('  if(activeSurfaceTesting)QTimer::singleShot(300,this,[this]{surfaceTestAdvance();});',
       '  if(qualityTesting)QTimer::singleShot(300,this,[this]{qualityTestAdvance();});\n  else if(activeSurfaceTesting)QTimer::singleShot(300,this,[this]{surfaceTestAdvance();});'),
    ]
    for a,b in changes:text=update(text,a,b)
    with (SRC/'active_surface_UI_r16.inc').open('x',encoding='utf-8',newline='\n') as f:f.write(text)
    text=(ROOT/'modules/surface_route/board_native_build_r15.py').read_text(encoding='utf-8')
    text=text.replace('r15','r16').replace('r14d','r15').replace('R14d','R15').replace('R15','R16')
    with (ROOT/'modules/surface_route/board_native_build_r16.py').open('x',encoding='utf-8',newline='\n') as f:f.write(text)
    parent=json.loads((ROOT/'modules/surface_route/native_UI_source_closure_r15.json').read_text(encoding='utf-8'))['files_sha256']
    names=set(parent)
    names.update(p.relative_to(ROOT).as_posix() for folder in ('modules/surface_quality','modules/surface_route') for p in (ROOT/folder).glob('*.py'))
    names.update(['ui/releases/feature_completion_r6/src/'+n for n in ('main_complete_scene_r16.cpp','active_surface_UI_r16.inc','surface_quality_UI_r16.inc')])
    names.update(['modules/surface_route/derivations_r16.json','tools/derive_surface_quality_r16.py','tools/derive_surface_quality_UI_r16.py'])
    for n,h in parent.items():
        if hashlib.sha256((ROOT/n).read_bytes()).hexdigest()!=h:raise ValueError('Sealed parent source changed: '+n)
    hashes={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(names)}
    with (ROOT/'modules/surface_route/native_UI_source_closure_r16.json').open('x',encoding='utf-8') as f:json.dump(dict(files_sha256=hashes),f,indent=2)
if __name__=='__main__':main()
