"""Derive current-surface actions while preserving the sealed R10/default source."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json
from modules.surface_route.derive_scene_r9 import replace_once


def main():
    src=ROOT/'ui/releases/feature_completion_r6/src';parent=src/'main_complete_scene_r10.cpp'
    selected=(src/'selected_application_r2.inc').read_text(encoding='utf-8')
    selected=replace_once(selected,' void startSelectedPath(int group,int candidate){',
        ' void startSelectedPath(int group,int candidate){\n  if(scene.contains("complete_surface")){startSurfaceAction("selected-path",group,candidate);return;}')
    legacy=ROOT/'ui/releases/feature_completion_r6/comparison_dialog_selected_r1.inc'
    original=legacy.read_text(encoding='utf-8')
    dispatch=replace_once(original,' void showComparisons(){',' void showComparisons(){\n  if(scene.contains("complete_surface")){showSurfaceComparisons();return;}')
    surface=replace_once(original,' void showComparisons(){',' void showSurfaceComparisons(){')
    surface=replace_once(surface,'全气道比较保留原 Python 规则；实际导航使用含图像保守余量的 PL 净空审核。',
        '当前 C1 表面的完整原始骨架比较；净空包含连续管壁、裁剪与图像保守余量。采用时再次审核完整曲线。')
    surface=replace_once(surface,'d-whole["scope_diameter_mm"].toDouble()','d-diameter->value()')
    surface=replace_once(surface,'尚未包含实际导航的图像保守余量审核。','已包含当前表面的净空审核，采用时继续复核所选曲线及弯曲约束。')
    surface=replace_once(surface,'preview->setPreviewRoute(candidate["points_lps_mm"].toArray());',
        'preview->setPreviewRoute(candidate["points_lps_mm"].toArray());apply->setEnabled(candidate["points_lps_mm"].toArray().size()>1&&!processing());')
    begin=surface.index('  auto*auditPage=');end=surface.index('  int requestedGroup=',begin)
    surface=surface[:begin]+surface[end:]
    begin=surface.index('  if(qEnvironmentVariableIntValue("KV260_WHOLE_COMPARISON_UI_TEST")');end=surface.index('  dialog.exec();',begin)
    test='''  if(activeSurfaceTesting&&surfaceTestStage==2)QTimer::singleShot(500,&dialog,[&]{
   surfaceCheck("five_current_surface_profiles",profiles.size()==5&&fullTable->rowCount()==5);
   surfaceCheck("complete_raw_cycles_preserved",whole["raw_nodes"].toInt()==863&&whole["raw_undirected_edges"].toInt()==871&&whole["cycles_preserved_before_explicit_geometry_filter"].toBool());
   surfaceCheck("no_old_PL_audit_tab",pages->count()==2);QDir().mkpath(evidence);dialog.grab().save(evidence+"/active_profile_chart.png");pages->setCurrentIndex(1);
   int visited=0;
   for(int i=0;i<groups.size();++i){diameters->setCurrentIndex(i);QTest::qWait(40);
    surfaceCheck(QString("current_Pareto_rows_%1").arg(i),routes->rowCount()==groups[i].toObject()["pareto"].toArray().size());
    for(int j=0;j<routes->rowCount();++j){routes->setCurrentCell(j,0);QTest::qWait(25);int id=activeFront[j].toObject()["candidate_id"].toInt();QJsonObject expected;
     for(auto v:activeCandidates)if(v.toObject()["candidate_id"].toInt()==id)expected=v.toObject();
     auto actual=preview->previewRouteMetrics();surfaceCheck(QString("complete_preview_%1_%2").arg(i).arg(j),actual["point_count"].toInt()==expected["points_lps_mm"].toArray().size());++visited;
    }
   }
   surfaceCheck("all_Pareto_paths_previewed",visited>8);diameters->setCurrentIndex(2);int choice=0;double length=-1;
   for(int j=0;j<activeFront.size();++j){double value=activeFront[j].toObject()["route_length_mm"].toDouble();if(value>length){length=value;choice=j;}}
   routes->setCurrentCell(choice,0);QTest::qWait(100);dialog.grab().save(evidence+"/active_Pareto_preview.png");surfaceTickBase=ticks;
   surfaceCheck("actual_apply_button_enabled",apply->isEnabled());if(failed)dialog.reject();else QTest::mouseClick(apply,Qt::LeftButton);
  });
'''
    surface=surface[:begin]+test+surface[end:]
    text=parent.read_text(encoding='utf-8')
    text=replace_once(text,'#include "selected_application_r2.inc"','#include "selected_application_r14.inc"\n#include "active_surface_UI_r14.inc"\n#include "active_surface_test_r14.inc"\n#include "surface_comparison_dialog_r14.inc"')
    text=replace_once(text,'#include "../comparison_dialog_selected_r1.inc"','#include "../comparison_dispatch_r14.inc"')
    text=replace_once(text,'for(auto*b:{compareButton,comparisonResults,rebuildButton,navButton,batchButton,videoButton,recoveryButton})',
        'for(auto*b:{rebuildButton,navButton,batchButton,videoButton,recoveryButton})')
    text=replace_once(text,'comparisonResults->setEnabled(!value&&scene["navigation"].toObject().contains("instrument_profiles"))',
        'comparisonResults->setEnabled(!value&&scene["navigation"].toObject().contains(scene.contains("complete_surface")?"whole_instrument_profiles":"instrument_profiles"))')
    text=replace_once(text,'  if(scene.contains("complete_surface")&&mode!="all")',
        '  if(scene.contains("complete_surface")&&mode=="comparison"){startSurfaceAction(mode);return;}\n  if(scene.contains("complete_surface")&&mode!="all")')
    text=replace_once(text,'root+"/modules/surface_route/native_prepare_r9.py","--scene",complete',
        'root+"/modules/surface_route/active_backend_r14.py","prepare","--active-scene",complete')
    text=replace_once(text,'record("scene_loaded");selectedPathPrepared();','restoreSurfaceComparisonControls();record("scene_loaded");selectedPathPrepared();')
    text=replace_once(text,'busy(false);if(!failed)configureScope();if(completeSceneGuiTesting)',
        'busy(false);if(!failed)configureScope();if(activeSurfaceTesting){QTimer::singleShot(300,this,[this]{surfaceTestAdvance();});}else if(completeSceneGuiTesting)')
    text=replace_once(text,'this,[this](int rc,QProcess::ExitStatus){stopButton->setEnabled(false);if(rc)',
        'this,[this](int rc,QProcess::ExitStatus){if(activeSurfaceJob){surfaceJobFinished(rc);return;}stopButton->setEnabled(false);if(rc)')
    outputs={src/'selected_application_r14.inc':selected,ROOT/'ui/releases/feature_completion_r6/comparison_dispatch_r14.inc':dispatch,
        src/'surface_comparison_dialog_r14.inc':surface,src/'main_complete_scene_r14.cpp':text}
    for path,value in outputs.items():
        with path.open('x',encoding='utf-8',newline='\n') as file:file.write(value)
    write_json(ROOT/'modules/surface_route/native_UI_derivation_r14.json',dict(parent_sha256=sha(parent),
        outputs_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in outputs},
        default_and_R10_sources_unchanged=True,current_surface_actions=True))


if __name__=='__main__':main()
