"""Rebase native video export onto the accepted R4 depth/cache renderer."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;UI=ROOT/'ui/releases/feature_completion_r6'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,s):
    assert not p.exists(),p
    p.write_text(s,encoding='utf-8',newline='\n')
def replace(s,a,b):
    assert s.count(a)==1,a
    return s.replace(a,b)
def main():
    r=json.loads((ROOT/'ui/active_release.json').read_text(encoding='utf-8'))
    assert r['name']=='complete_feature_UI_with_correct_cached_fast_lung_depth_and_canvas_alpha_r4'
    for key in ('source_sha256','shared_source_sha256'):
        for n,d in r['UI_build'][key].items():assert sha(ROOT/n)==d,n
    encoder=(HERE/'encoder_UI_r1.hpp').read_text(encoding='utf-8')
    encoder=replace(encoder,'QString path;QSize size;int rate;','QString path,codec;QSize size;int rate;')
    encoder=replace(encoder,'process.start("/usr/bin/ffmpeg",','process.start(codec,')
    encoder=replace(encoder,'std::function<void(QString)> onFinished)','std::function<void(QString)> onFinished,QString executable="/usr/bin/ffmpeg")')
    encoder=replace(encoder,':target(t),path(file),size(dimensions)',':target(t),path(file),codec(executable),size(dimensions)')
    save(HERE/'encoder_UI_r2.hpp',encoder)
    feature=(HERE/'UI_feature_r1.inc').read_text(encoding='utf-8')
    feature=replace(feature,'bool videoTestCancelAwaiting=false;','bool videoTestCancelAwaiting=false,videoSetupRejected=false;QTimer videoWatchdog;QElapsedTimer videoProgressClock;int videoStartTick=0;')
    feature=replace(feature,'if(videoTesting)QTimer::singleShot(150,&setup,[&]{QTest::mouseClick(buttons.button(QDialogButtonBox::Ok),Qt::LeftButton);});',
        '''if(videoTesting)QTimer::singleShot(150,&setup,[&]{QTest::mouseClick(buttons.button(!videoSetupRejected?QDialogButtonBox::Cancel:QDialogButtonBox::Ok),Qt::LeftButton);});''')
    feature=replace(feature,'if(setup.exec()!=QDialog::Accepted)return;',
        '''if(setup.exec()!=QDialog::Accepted){if(videoTesting){videoSetupRejected=true;videoTestTrace.append(QJsonObject{{"status","setup_cancelled"},{"camera_unchanged",scope->scopeViewState()==videoTestSnapshot["camera"].toObject()}});QTimer::singleShot(200,this,[this]{videoTestAdvance();});}return;}''')
    feature=replace(feature,'videoSavedPlaying=playing;navigationPause();','videoSavedPlaying=playing;')
    feature=replace(feature,'videoPending=true;videoRunning=', 'navigationPause();videoPending=true;videoRunning=')
    feature=replace(feature,'videoError.clear();videoClock.start();',
        '''videoError.clear();videoClock.start();videoProgressClock.start();videoStartTick=ticks;
   videoWatchdog.setInterval(1000);disconnect(&videoWatchdog,nullptr,this,nullptr);connect(&videoWatchdog,&QTimer::timeout,this,[this]{if(!videoEnding&&videoProgressClock.elapsed()>60000)videoEnd(u("当前导出步骤等待超过 60 秒，正在安全恢复"));});videoWatchdog.start();''')
    feature=replace(feature,'videoPending=false;videoRunning=true;busy(true);',
        '''videoPending=false;videoRunning=true;busy(true);scope->setEnabled(false);''')
    feature=replace(feature,'[this](QString){videoEncoding=false;++videoIndex;',
        '''[this](QString){videoProgressClock.restart();videoEncoding=false;++videoIndex;''')
    feature=replace(feature,'if(videoTesting&&videoTestPhase==2&&videoIndex==3)',
        'if(videoTesting&&videoTestPhase==2&&videoIndex==3)')
    feature=replace(feature,'[this](QString error){videoEncoderDone=true;if(!error.isEmpty())videoEnd(error);videoComplete();});',
        '''[this](QString error){videoEncoderDone=true;if(!error.isEmpty())videoEnd(error);videoComplete();},
   videoTesting&&videoTestPhase==3?"/nonexistent/kv260_codec_failure_test":"/usr/bin/ffmpeg");''')
    feature=replace(feature,'if(videoEnding)return;if(videoCancelled)', 'try{if(videoEnding)return;if(videoCancelled)')
    feature=replace(feature,'else plScope->request(request);\n }',
        '''else plScope->request(request);videoProgressClock.restart();
  }catch(const std::exception&e){videoEnd(QString::fromUtf8(e.what()));}
 }''')
    feature=replace(feature,'videoLastMeta=meta;videoDepth=', 'videoProgressClock.restart();videoLastMeta=meta;videoDepth=')
    feature=replace(feature,'bool ok=videoError.isEmpty()', 'videoWatchdog.stop();bool ok=videoError.isEmpty()')
    feature=replace(feature,'{"native_GUI_button",true}',
        '''{"native_GUI_button",true},{"UI_ticks_during_export",ticks-videoStartTick},{"codec", "libx264"},{"encoder_threads",2}''')
    # A commit or source-binding failure must not leave a completed report.
    feature=replace(feature,'}catch(const std::exception&e){ok=false;videoError=QString::fromUtf8(e.what());}',
        '''}catch(const std::exception&e){ok=false;videoError=QString::fromUtf8(e.what());report["status"]="failed";report["error"]=videoError;try{writeJson(videoDirectory+"/report.json",report);}catch(...){}}''')
    feature=replace(feature,'bool restored=scope->restoreScopeViewState(videoSavedCamera);',
        '''bool restored=scope->restoreScopeViewState(videoSavedCamera);scope->setEnabled(true);''')
    feature=replace(feature,'if(!restored||(!ok&&!videoCancelled))',
        '''if(!restored||(!ok&&!videoCancelled&&!(videoTestPhase==3&&report["status"]=="failed"&&videoError.contains("Cannot start FFmpeg"))))''')
    feature=replace(feature,'passed_actual_GUI_full_route_video_cancel_and_camera_restore',
        'passed_actual_GUI_full_route_video_setup_cancel_PL_cancel_codec_failure_camera_restore')
    feature=replace(feature,'if(videoTestPhase==3){if(!videoTestCancelAwaiting){videoTestFinish(false,u("未覆盖等待 PL 时的取消"));return;}videoTestFinish(true);}',
        '''if(videoTestPhase==3){if(!videoTestCancelAwaiting){videoTestFinish(false,u("未覆盖等待 PL 时的取消"));return;}QTest::mouseClick(videoButton,Qt::LeftButton);return;}
  if(videoTestPhase==4)videoTestFinish(true);''')
    save(HERE/'UI_feature_r2.inc',feature)
    header=(UI/'src/views_fast_opacity_r4.hpp').read_text(encoding='utf-8')
    header=replace(header,' QJsonObject cameraRequest()const;',
        ' QJsonObject cameraRequest()const;\n QJsonObject scopeViewState()const;bool restoreScopeViewState(const QJsonObject&);QImage completedScopeColor();')
    save(UI/'src/views_media_r2.hpp',header)
    source=(UI/'src/views_fast_opacity_r4.cpp').read_text(encoding='utf-8').replace('"views_fast_opacity_r4.hpp"','"views_media_r2.hpp"')
    source+='\n#include "../../../../modules/navigation_media/native_view_methods_r1.inc"\n'
    save(UI/'src/views_media_r2.cpp',source)
    main=(UI/'src/main_fast_opacity_r4.cpp').read_text(encoding='utf-8').replace('"views_fast_opacity_r4.hpp"','"views_media_r2.hpp"')
    token='#include "../../../../modules/user_capture/capture.hpp"'
    main=replace(main,token,token+'\n#include "../../../../modules/navigation_media/timeline.hpp"\n#include "../../../../modules/navigation_media/frame_r1.hpp"\n#include "../../../../modules/navigation_media/encoder_UI_r2.hpp"')
    token='#include "capture_feature.inc"'
    main=replace(main,token,token+'\n#include "../../../../modules/navigation_media/UI_feature_r2.inc"')
    main=replace(main,'void busy(bool value){','void busy(bool value){value=value||videoPending||videoRunning;if(videoButton)videoButton->setEnabled(!value&&scope->cameraCount()>1&&!source.isEmpty());')
    main=replace(main,'bool processing()const{return ','bool processing()const{return videoPending||videoRunning||')
    token='snapshotButton=button(u("保存截图 · PNG"),left);'
    main=replace(main,token,token+'videoButton=button(u("导出导航视频 · MP4"),left);connect(videoButton,&QPushButton::clicked,this,[this]{videoRequest();});')
    token='plScope->onFrame=[this](QImage frame,QImage normals,QJsonObject meta){'
    main=replace(main,token,token+'videoFrameReceived(frame,normals,meta);')
    token='scope->onPlPresented=[this](int){syncLinkedOverview();'
    main=replace(main,token,token+'videoPresented();')
    token='if(qEnvironmentVariableIntValue("KV260_FAST_OPACITY_TEST")==1){QTimer::singleShot(400'
    main=replace(main,token,'if(videoTesting){QTimer::singleShot(400,this,[this]{videoTestAdvance();});}else '+token)
    token='if(exitRequested&&!processing())this->close();'
    main=replace(main,token,'if(exitRequested&&(videoPending||videoRunning))videoCancel();'+token)
    token='void closeEvent(QCloseEvent*e)override{'
    main=replace(main,token,token+'if(videoPending||videoRunning){videoCancel();e->ignore();return;}')
    save(UI/'src/main_media_r2.cpp',main)
    build=(UI/'build_media_r1.sh').read_text(encoding='utf-8').replace('media_r1','media_r2').replace('pl_composite_exact_speed_r7.cpp','pl_composite_exact_speed_r8.cpp')
    save(UI/'build_media_r2.sh',build)
    run=(UI/'run_fast_opacity_r4.sh').read_text(encoding='utf-8').replace('build_fast_opacity_r4','build_media_r2')
    save(UI/'run_media_r2.sh',run)
    closure=dict(status='accepted_R4_UI_plus_bounded_full_route_video_export',inherited_UI_sha256=r['UI_build']['binary_sha256'],
        inherited_descriptor_sha256=sha(ROOT/'ui/active_release.json'),source_sha256=dict(r['UI_build']['source_sha256']),
        shared_source_sha256=dict(r['UI_build']['shared_source_sha256']),medical_PL_algorithms_changed=False)
    files=[HERE/n for n in ('timeline.hpp','frame_r1.hpp','encoder_UI_r2.hpp','native_view_methods_r1.inc','UI_feature_r2.inc','prepare_UI_r2.py')]
    files+=[UI/n for n in ('src/views_media_r2.cpp','src/views_media_r2.hpp','src/main_media_r2.cpp','build_media_r2.sh','run_media_r2.sh')]
    for p in files:closure['source_sha256'][p.relative_to(ROOT).as_posix()]=sha(p)
    save(UI/'source_closure_media_r2.json',json.dumps(closure,indent=2)+'\n')
    print('Rebased native video GUI from the accepted R4 renderer')
if __name__=='__main__':main()
