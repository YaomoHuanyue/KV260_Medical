"""Explicit complete-scene candidate; keep accepted R17 entry and sources intact."""
from pathlib import Path
import hashlib
import json
from modules.surface_route.derive_scene_r9 import replace_once

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'ui/releases/feature_completion_r6/src'


def main():
    parent=SRC/'main_xray_r2.cpp';text=parent.read_text(encoding='utf-8')
    text=replace_once(text,'#include "pl_scope.hpp"','#include "pl_scope_complete_r9.hpp"')
    text=replace_once(text,'reason=="insufficient_root_clearance"?',
        'reason=="insufficient_new_surface_route_clearance"?u("新表面部分管段净空不足"):\n  reason=="insufficient_root_clearance"?')
    text=replace_once(text,'  if(needsScope)plScope->start(source,scope->cameraRequest());else if(page==2)',
        '  if(needsScope){auto complete=scene["complete_surface"].toObject();\n'
        '   if(!complete.isEmpty())plScope->startScene(complete["bundle"].toString(),complete["revision"].toString(),scope->cameraRequest());\n'
        '   else plScope->start(source,scope->cameraRequest());\n'
        '  }else if(page==2)')
    old='  QStringList args={root+"/ui/releases/feature_completion_r6/backend_selected_r1.py","prepare","--input",input};if(!selected.isEmpty())args<<"--result"<<selected;'
    text=replace_once(text,old,old+'\n'
        '  QString complete=qEnvironmentVariable("KV260_COMPLETE_SCENE");\n'
        '  if(scene.isEmpty()&&selected.isEmpty()&&!complete.isEmpty())args={root+"/modules/surface_route/native_prepare_r9.py","--scene",complete,"--input",input};')
    # Individual legacy jobs/export would overwrite or silently export old geometry.
    # Keep these pending visibly in the candidate until new-field dispatch exists.
    text=replace_once(text,' void startJob(QString mode){',
        ' void startJob(QString mode){\n'
        '  if(scene.contains("complete_surface")&&mode!="all"){message(u("当前新表面场景的单项重规划尚未接入；请保留当前场景，或选择原结果。"));return;}')
    text=replace_once(text,'void startUtility(QString action,QStringList args){',
        'void startUtility(QString action,QStringList args){\n'
        '  if(action=="export"&&scene.contains("complete_surface")){message(u("当前新表面的完整导出尚未接入，已保留当前场景。"));return;}')
    text=replace_once(text,'stopButton->setEnabled(jobProcess.state()!=QProcess::NotRunning&&!selectedTaskPending);}',
        'stopButton->setEnabled(jobProcess.state()!=QProcess::NotRunning&&!selectedTaskPending);\n'
        '  if(scene.contains("complete_surface")){\n'
        '   for(auto*b:{exportButton,compareButton,comparisonResults,rebuildButton,navButton,batchButton,videoButton,recoveryButton})if(b){\n'
        '    b->setEnabled(false);b->setToolTip(u("新表面场景仍在独立验证；此操作需要对应的新场景算法接口。"));}\n'
        '  }\n }')
    text=replace_once(text,' void record(QString action){',
        ''' bool completeSceneGuiTesting=qEnvironmentVariableIntValue("KV260_COMPLETE_SCENE_GUI_TEST")==1;
 int completeSceneGuiStage=0;QJsonArray completeSceneGuiTrace;
 void completeSceneGuiTest(){
  if(failed||!scene.contains("complete_surface")){writeJson(evidence+"/complete_scene_UI.json",{{"status","failed_complete_scene_load"},{"PL_access",false}});QApplication::exit(1);return;}
  if(completeSceneGuiStage==0){tabs->setCurrentIndex(1);preciseBlend->setChecked(false);showStructure(0);}
  else if(completeSceneGuiStage==1){showStructure(1);colorMode->setCurrentIndex(1);testDrag(overview,QPoint(180,160),QPoint(260,200));}
  else if(completeSceneGuiStage==2){showStructure(2);colorMode->setCurrentIndex(0);overview->turn(12);}
  else{
   bool good=plFrames==0&&compositeFrames==0&&scope->cameraCount()==scene["navigation"].toObject()["positions"].toArray().size();
   writeJson(evidence+"/complete_scene_UI.json",{{"status",good?"passed_complete_native_scene_model_interactions_no_PL":"failed"},
    {"scene",scenePath},{"revision",scene["complete_surface"].toObject()["revision"]},{"trace",completeSceneGuiTrace},
    {"scope_features",scope->featureMetrics()},{"camera_count",scope->cameraCount()},{"UI_peak_RSS_MiB",peakRSS()},
    {"PL_access",false},{"new_bitstream",false},{"physical_review",false}});QApplication::exit(good?0:1);return;
  }
  QString file=evidence+QString("/model_%1.png").arg(completeSceneGuiStage);
  QTimer::singleShot(700,this,[this,file]{bool saved=grab().save(file);completeSceneGuiTrace.append(QJsonObject{{"stage",completeSceneGuiStage},{"PNG",file},{"saved",saved},{"features",overview->featureMetrics()},{"camera",overview->overviewCamera()}});if(!saved)failed=true;++completeSceneGuiStage;completeSceneGuiTest();});
 }
 void record(QString action){''')
    text=replace_once(text,'if(!failed)configureScope();if(batchTesting){',
        'if(!failed)configureScope();if(completeSceneGuiTesting){QTimer::singleShot(400,this,[this]{completeSceneGuiTest();});}else if(batchTesting){')
    dest=SRC/'main_complete_scene_r9.cpp'
    with dest.open('x',encoding='utf-8',newline='\n') as stream:stream.write(text)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    proof=dict(parent_sha256=sha(parent),output_sha256=sha(dest),production_sources_unchanged=True,
        changes=['explicit preverified complete scene startup', 'C9 complete revision dispatch',
                 'full actual native model scene regression',
                 'legacy new-field replanning/export/media guarded pending corresponding adapters'])
    with (Path(__file__).parent/'native_UI_derivation_r9.json').open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(json.dumps(proof,indent=2)+'\n')


if __name__=='__main__':main()
