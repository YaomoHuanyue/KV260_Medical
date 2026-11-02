"""Add explicit fast interaction previews without changing precise C7 geometry."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def save(name,text):
    p=HERE/name;assert not p.exists(),name
    p.write_text(text,encoding='utf-8',newline='\n')

def replace(s,old,new):
    assert s.count(old)==1,old[:100]
    return s.replace(old,new)

def main():
    prior=json.loads((HERE/'build_selected_r3/build.json').read_text(encoding='utf-8'))
    for group in ('source_sha256','shared_source_sha256'):
        for n,d in prior[group].items():assert sha(ROOT/n)==d,n
    h=(HERE/'src/views.hpp').read_text(encoding='utf-8')
    h=replace(h,'bool compositeEnabled=false;','bool compositePreview=false;int previewPaints=0,previewSwaps=0;bool lastPaintPreview=false;bool compositeEnabled=false;')
    h=replace(h,'bool compositeMode()const{return compositeEnabled;}',
        'bool compositeMode()const{return compositeEnabled;}\n'
        ' void setCompositePreview(bool value){compositePreview=value&&compositeEnabled;refresh();}\n'
        ' bool compositePreviewMode()const{return compositeEnabled&&compositePreview;}\n'
        ' QJsonObject compositePreviewMetrics()const{return {{"painted",previewPaints},{"swapped",previewSwaps},{"active",compositePreviewMode()}};}')
    h=replace(h,'compositeEnabled=enabled;refresh();}','compositeEnabled=enabled;if(!enabled)compositePreview=false;refresh();}')
    save('src/views_interactive_r1.hpp',h)
    v=(HERE/'src/views.cpp').read_text(encoding='utf-8')
    v=replace(v,'#include "views.hpp"','#include "views_interactive_r1.hpp"')
    v=replace(v,'#include "composite_view.inc"','#include "composite_view_interactive_r1.inc"')
    v=replace(v,'connect(this,&QOpenGLWidget::frameSwapped,this,[this]{','connect(this,&QOpenGLWidget::frameSwapped,this,[this]{if(lastPaintPreview)++previewSwaps;')
    v=replace(v,'if(compositeEnabled&&!scope){drawComposite',
        'lastPaintPreview=compositeEnabled&&compositePreview&&!scope;if(lastPaintPreview)++previewPaints;\n if(compositeEnabled&&!compositePreview&&!scope){drawComposite')
    v=replace(v,'if(compositeEnabled&&!scope&&compositeFrame.isNull())',
        'if(compositeEnabled&&!compositePreview&&!scope&&compositeFrame.isNull())')
    old='if(compositeEnabled&&!scope){p.setPen(QColor("#fff0aa"));'
    v=replace(v,old,'if(compositeEnabled&&compositePreview&&!scope){p.setPen(QColor("#fff0aa"));p.drawText(14,height()-14,QString::fromUtf8("交互预览 · 近似透明 · 停止操作后生成精确画面"));}\n if(compositeEnabled&&!compositePreview&&!scope){p.setPen(QColor("#fff0aa"));')
    save('src/views_interactive_r1.cpp',v)
    c=(HERE/'src/composite_view.inc').read_text(encoding='utf-8')
    c=replace(c,'if(compositeEnabled&&compositeFrame.isNull())return false;',
        'if(compositeEnabled&&!compositePreview&&compositeFrame.isNull())return false;')
    c=replace(c,'auto box=compositeEnabled?compositeRect():QRectF(rect());',
        'auto box=compositeEnabled&&!compositePreview?compositeRect():QRectF(rect());')
    save('src/composite_view_interactive_r1.inc',c)
    s=(HERE/'src/main_selected_r3.cpp').read_text(encoding='utf-8')
    s=replace(s,'#include "views.hpp"','#include "views_interactive_r1.hpp"')
    s=replace(s,'QCheckBox*preciseBlend=nullptr;',
        'QCheckBox*fastTransparency=nullptr;QTimer compositeQuiet;int previewQuietRequests=0,previewStaleFrames=0;\n'
        ' bool transparentInteractionTesting=qEnvironmentVariableIntValue("KV260_TRANSPARENT_INTERACTION_TEST")==1;\n'
        ' QTimer transparentTestCheck,transparentTestMotion;QElapsedTimer transparentTestDeadline,transparentMotionClock;\n'
        ' int transparentTestStage=-1,transparentTestBase=0,transparentMoves=0,transparentSwapBase=0,transparentRequestBase=0;\n'
        ' QJsonObject transparentBaselineRequest,transparentBaselineMeta,transparentTestReport;QByteArray transparentBaselinePixels,transparentLastPixels;\n'
        ' QVector<double>transparentSwapTimes;bool transparentMoving=false;\n'
        ' QCheckBox*preciseBlend=nullptr;')
    s=replace(s,'#include "composite_test.inc"','#include "composite_test.inc"\n#include "transparent_interaction_test_r1.inc"')
    old='preciseBlend->setToolTip(u("逐层排序肺表面并合成。完整肺网格改变视角后需数秒，计算时保留上一张完成画面。"));blendTools->addWidget(preciseBlend);'
    new='preciseBlend->setToolTip(u("停止操作后逐层排序肺表面并用 PL 精确合成；交互预览保留所选网格，使用近似透明。"));blendTools->addWidget(preciseBlend);fastTransparency=new QCheckBox(u("交互时快速预览"));fastTransparency->setChecked(!compositeTesting);fastTransparency->setToolTip(u("旋转、缩放和平移时立即显示当前镜头；停止 450 ms 后生成完整精确透明画面。关闭后始终等待精确帧。"));blendTools->addWidget(fastTransparency);'
    s=replace(s,old,new)
    s=replace(s,'connect(preciseBlend,&QCheckBox::toggled,this,[this](bool enabled){overview->setCompositeEnabled(enabled);configureScope();});',
        'connect(preciseBlend,&QCheckBox::toggled,this,[this](bool enabled){overview->setCompositeEnabled(enabled);compositeQuiet.stop();if(enabled&&fastTransparency->isChecked()){overview->setCompositePreview(true);compositeQuiet.start(450);}else configureScope();});\n'
        '  connect(fastTransparency,&QCheckBox::toggled,this,[this](bool enabled){if(!overview->compositeMode())return;compositeQuiet.stop();overview->setCompositePreview(enabled);if(enabled)compositeQuiet.start(450);else{configureScope();if(plComposite->active()&&!processing())plComposite->request(overview->overviewRequest());}});')
    s=replace(s,'if(!overview->compositeMode())return;if(!overview->setCompositeFrame(frame,meta))',
        'if(!overview->compositeMode())return;\n'
        '   if(fastTransparency->isChecked()&&!transparentFrameMatches(meta,overview->overviewRequest())){++previewStaleFrames;return;}\n'
        '   if(transparentInteractionTesting)transparentLastPixels=QByteArray(reinterpret_cast<const char*>(frame.constBits()),frame.sizeInBytes());\n'
        '   overview->setCompositePreview(false);if(!overview->setCompositeFrame(frame,meta))')
    old='overview->onOverviewChanged=[this]{if(!settingStructure&&overview->compositeMode()&&plComposite->active()&&!processing()&&tabs->currentIndex()==1){overview->setCompositeStatus(u("正在计算新视角，显示上一张完成画面"));plComposite->request(overview->overviewRequest());}};'
    new='compositeQuiet.setSingleShot(true);compositeQuiet.setTimerType(Qt::PreciseTimer);\n'
    new+='  connect(&compositeQuiet,&QTimer::timeout,this,[this]{if(closing||finishingTest||processing()||tabs->currentIndex()!=1||!overview->compositeMode()||!fastTransparency->isChecked())return;++previewQuietRequests;configureScope();});\n'
    new+='  overview->onOverviewChanged=[this]{if(settingStructure||!overview->compositeMode()||processing()||tabs->currentIndex()!=1)return;if(fastTransparency->isChecked()){overview->setCompositePreview(true);compositePerf->setText(u("交互预览 · 停止操作后生成精确透明画面"));compositeQuiet.start(450);}else if(plComposite->active()){overview->setCompositeStatus(u("正在计算新视角，显示上一张完成画面"));plComposite->request(overview->overviewRequest());}};\n'
    new+='  connect(&transparentTestCheck,&QTimer::timeout,this,[this]{transparentTestAdvance();});\n'
    new+='  connect(&transparentTestMotion,&QTimer::timeout,this,[this]{transparentMotionAdvance();});\n'
    new+='  connect(overview,&QOpenGLWidget::frameSwapped,this,[this]{if(transparentMoving&&overview->compositePreviewMode())transparentSwapTimes.append(transparentMotionClock.nsecsElapsed()/1.e6);});'
    s=replace(s,old,new)
    s=replace(s,'if(qEnvironmentVariableIntValue("KV260_SELECTED_PATH_UI_TEST")==1){QTimer::singleShot',
        'if(transparentInteractionTesting){QTimer::singleShot(400,this,[this]{if(failed)transparentTestFinish(false,u("病例准备失败"));else transparentTestCheck.start(100);});}else if(qEnvironmentVariableIntValue("KV260_SELECTED_PATH_UI_TEST")==1){QTimer::singleShot')
    save('src/main_interactive_r1.cpp',s)
    b=(HERE/'build_selected_r3.sh').read_text(encoding='utf-8')
    b=b.replace('build_selected_r3','build_interactive_r1').replace('source_closure_selected_r3','source_closure_interactive_r1').replace('main_selected_r3.cpp','main_interactive_r1.cpp').replace('src/views.cpp','src/views_interactive_r1.cpp').replace('selected_path_application_UI_compiled_actual_ARM','transparent_interaction_UI_compiled_actual_ARM')
    save('build_interactive_r1.sh',b)
    save('run_interactive_r1.sh',(HERE/'run_selected_r3.sh').read_text(encoding='utf-8').replace('build_selected_r3','build_interactive_r1'))
    r=json.loads((HERE/'source_closure_selected_r3.json').read_text(encoding='utf-8'))
    names=['src/views_interactive_r1.hpp','src/views_interactive_r1.cpp','src/composite_view_interactive_r1.inc','src/main_interactive_r1.cpp','src/transparent_interaction_test_r1.inc','derive_transparent_interaction_r1.py','build_interactive_r1.sh','run_interactive_r1.sh']
    r['source_sha256'].update({(HERE/n).relative_to(ROOT).as_posix():sha(HERE/n) for n in names})
    r.update(previous_selected_R3_binary_sha256=prior['binary_sha256'],
        interaction_preview_explicitly_approximate=True,selected_mesh_quality_never_automatically_changed=True,
        unchanged_precise_worker_sha256=sha(ROOT/'dfx/composite/medical/interactive/worker.cpp'),
        complete_precise_geometry_and_C7_core_unchanged=True,old_exact_only_UI_test_retained=True)
    save('source_closure_interactive_r1.json',json.dumps(r,indent=2)+'\n')
    print('Explicit preview and quiet exact-frame candidate derived; not yet compiled or shown')

if __name__=='__main__':main()
