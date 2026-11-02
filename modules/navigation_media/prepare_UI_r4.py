"""Derive native dual-view video without altering the accepted single-view UI."""
from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;UI=ROOT/'ui/releases/feature_completion_r6'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def save(p,s):
    assert not p.exists(),p
    p.write_text(s,encoding='utf-8',newline='\n')

def replace(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b)

def main():
    old=json.loads((UI/'source_closure_media_r3.json').read_text())
    for group in ('source_sha256','shared_source_sha256'):
        for n,d in old[group].items():assert sha(ROOT/n)==d,n
    feature=(HERE/'UI_feature_r3.inc').read_text(encoding='utf-8')
    feature=replace(feature,'QSize videoSize{1280,720};','bool videoLinked=false;QSize videoPaneSize{1280,720};QJsonObject videoSavedOverviewCamera;QSize videoSize{1280,720};')
    feature=replace(feature,'layout->addLayout(form);','layout->addLayout(form);QCheckBox linked(u("同时保存联动总览（左总览 / 右气镜）"));layout->addWidget(&linked);')
    feature=replace(feature,'原生计算 640×360；视频帧率代表回放速度。','每个视图原生计算 640×360；保存尺寸按单个视图设置。\\n视频帧率代表回放速度，联动视频总宽度为两倍。')
    feature=replace(feature,'if(videoTesting)QTimer::singleShot(150,&setup,', 'if(videoTesting){linked.setChecked(videoTestPhase==2);if(videoTestPhase==2)size.setCurrentIndex(1);}\n  if(videoTesting)QTimer::singleShot(150,&setup,')
    feature=replace(feature,'videoSize=size.currentIndex()==0?QSize(1280,720):QSize(640,360);',
        'videoLinked=linked.isChecked();videoPaneSize=size.currentIndex()==0?QSize(1280,720):QSize(640,360);videoSize=QSize(videoPaneSize.width()*(videoLinked?2:1),videoPaneSize.height());')
    feature=replace(feature,'videoSavedPlaying=playing;','videoSavedPlaying=playing;videoSavedOverviewCamera=miniOverview->overviewCamera();')
    feature=replace(feature,'scope->setDistance(0);','scope->setDistance(0);if(videoLinked)dualCheck->setChecked(true);')
    feature=feature.replace('videoTestPhase==2&&videoIndex==3','videoTestPhase==3&&videoIndex==3').replace('videoTestPhase==3?', 'videoTestPhase==4?').replace('(videoTestPhase==3&&report','(videoTestPhase==4&&report')
    feature=replace(feature,'videoLastImage=navigation_media::videoFrame(native,videoSize,shown,at<hud.size()?hud[at].toObject():QJsonObject{},videoPlan->length);',
        '''QJsonObject linkedProof;QImage overviewColor;
    if(videoLinked){miniOverview->setUpdatesEnabled(false);overviewColor=miniOverview->linkedOverviewColor(QSize(640,360),shown,linkedProof);}
    videoLastImage=videoLinked?navigation_media::linkedVideoFrame(overviewColor,native,videoPaneSize,shown,at<hud.size()?hud[at].toObject():QJsonObject{},videoPlan->length):
      navigation_media::videoFrame(native,videoPaneSize,shown,at<hud.size()?hud[at].toObject():QJsonObject{},videoPlan->length);''')
    feature=replace(feature,'png=stem+".png";', 'png=stem+".png";if(videoLinked){meta["overview_reference"]=stem+".overview.rgba";extra[meta["overview_reference"].toString()]=navigation_media::rgbaBytes(overviewColor);}')
    feature=replace(feature,'if(!png.isEmpty())row["reference_png"]=png;',
        'if(videoLinked){row["linked_overview"]=linkedProof;row["overview_color_sha256"]=medical_capture::pixelHash(overviewColor);}\n    if(!png.isEmpty())row["reference_png"]=png;')
    feature=replace(feature,'{"capture_fit_policy","native_C6_color_FBO_aspect_preserved"}',
        '{"linked_overview_enabled",videoLinked},{"pane_output_size",QJsonArray{videoPaneSize.width(),videoPaneSize.height()}},{"overview_native_size",videoLinked?QJsonArray{640,360}:QJsonArray{}},\n   {"capture_fit_policy",videoLinked?"native_C6_and_linked_overview_FBOs_aspect_preserved":"native_C6_color_FBO_aspect_preserved"}')
    feature=replace(feature,'"GPU shading/HUD","bounded pipe"','"GPU shading/HUD","linked overview/frustum/color capture","bounded pipe"')
    feature=replace(feature,'bool restored=scope->restoreScopeViewState(videoSavedCamera);',
        'miniOverview->setUpdatesEnabled(true);bool overviewRestored=miniOverview->restoreOverviewCamera(videoSavedOverviewCamera);\n  bool restored=scope->restoreScopeViewState(videoSavedCamera);')
    feature=replace(feature,'{"restored",restored},', '{"linked_overview_enabled",videoLinked},{"overview_restored",overviewRestored},{"restored_overview_camera",miniOverview->overviewCamera()},{"restored",restored},')
    feature=replace(feature,'if(!restored||(', 'if(!restored||!overviewRestored||(')
    feature=feature.replace('passed_actual_GUI_full_route_video_setup_cancel_PL_cancel_codec_failure_camera_restore',
        'passed_actual_GUI_single_and_linked_full_route_video_cancel_failure_view_restore')
    feature=replace(feature,'{"camera",scope->scopeViewState()},{"request",request}',
        '{"camera",scope->scopeViewState()},{"overview_camera",miniOverview->overviewCamera()},{"request",request}')
    feature=replace(feature,'if(videoTestPhase==3){if(!videoTestCancelAwaiting)',
        'if(videoTestPhase==3){QTest::mouseClick(videoButton,Qt::LeftButton);return;}\n  if(videoTestPhase==4){if(!videoTestCancelAwaiting)')
    feature=replace(feature,'if(videoTestPhase==4)videoTestFinish(true);','if(videoTestPhase==5)videoTestFinish(true);')
    save(HERE/'UI_feature_r4.inc',feature)
    encoder=(HERE/'encoder_UI_r2.hpp').read_text(encoding='utf-8')
    encoder=replace(encoder,'(depth|normal)','(depth|normal|overview)')
    save(HERE/'encoder_UI_r3.hpp',encoder)
    mainSource=(UI/'src/main_media_r3.cpp').read_text(encoding='utf-8').replace('views_media_r3.hpp','views_media_r4.hpp').replace('UI_feature_r3.inc','UI_feature_r4.inc').replace('frame_r1.hpp','frame_r2.hpp').replace('encoder_UI_r2.hpp','encoder_UI_r3.hpp')
    save(UI/'src/main_media_r4.cpp',mainSource)
    header=(UI/'src/views_media_r3.hpp').read_text(encoding='utf-8')
    header=replace(header,'void paintOverlay(QPainter&);','void paintOverlay(QPainter&,QSize captureSize={});')
    header=replace(header,'std::unique_ptr<QOpenGLFramebufferObject> scopeColor;', 'std::unique_ptr<QOpenGLFramebufferObject> linkedColor,scopeColor;')
    header=replace(header,'QImage completedScopeColor();','QImage completedScopeColor();\n QImage linkedOverviewColor(QSize,const QJsonObject&,QJsonObject&);')
    save(UI/'src/views_media_r4.hpp',header)
    view=(UI/'src/views_media_r3.cpp').read_text(encoding='utf-8').replace('views_media_r3.hpp','views_media_r4.hpp')
    view=replace(view,'makeCurrent();normalBackground.reset();','makeCurrent();linkedColor.reset();normalBackground.reset();')
    start=view.index('void MeshView::paintOverlay(QPainter &p){');end=view.index('\nvoid MeshView::setPreviewRoute',start)
    overlay=view[start:end].replace('rect()','bounds')
    overlay=re.sub(r'(?<![\w.])width\(\)','overlaySize.width()',overlay)
    overlay=re.sub(r'(?<![\w.])height\(\)','overlaySize.height()',overlay)
    overlay=replace(overlay,'void MeshView::paintOverlay(QPainter &p){','void MeshView::paintOverlay(QPainter &p,QSize captureSize){\n const QSize overlaySize=captureSize.isValid()?captureSize:size();const QRectF bounds(QPointF(0,0),overlaySize);')
    overlay=replace(overlay,'return projectOverview(v,out);',
        '''if(!captureSize.isValid())return projectOverview(v,out);QVector4D c=lastMvp*QVector4D(v,1);
  if(c.w()<=0||c.z() < -c.w()||c.z()>c.w())return false;
  out={(c.x()/c.w()+1)*captureSize.width()/2,(1-c.y()/c.w())*captureSize.height()/2};return true;''')
    view=view[:start]+overlay+view[end:]+ '\n#include "../../../../modules/navigation_media/linked_view_r1.inc"\n'
    save(UI/'src/views_media_r4.cpp',view)
    for n in ('build_media_r4.sh','run_media_r4.sh'):
        save(UI/n,(UI/n.replace('r4','r3')).read_text(encoding='utf-8').replace('media_r3','media_r4'))
    test=(HERE/'test_native_UI_r3.py').read_text(encoding='utf-8')
    test=test.replace('verify_release_r12','verify_release_r13').replace("HERE/'results/native_UI_restored_r2.json'","ROOT/'results/profile_R3_host_board_state_r1.json'").replace('_r3','_r4')
    test=test.replace('passed_actual_GUI_full_route_video_setup_cancel_PL_cancel_codec_failure_camera_restore','passed_actual_GUI_single_and_linked_full_route_video_cancel_failure_view_restore')
    test=replace(test,"['setup_cancelled','completed','cancelled','failed']","['setup_cancelled','completed','completed','cancelled','failed']")
    test=replace(test,"assert entries[2]['cancel_requested_while_awaiting_PL']", "assert entries[3]['cancel_requested_while_awaiting_PL']")
    test=replace(test,"not entries[3]['cancel_requested_while_awaiting_PL']","not entries[4]['cancel_requested_while_awaiting_PL']")
    test=replace(test,"report=json.loads((Path(entries[1]['directory'])/'report.json').read_text())",
        "assert not entries[1]['linked_overview_enabled'] and entries[2]['linked_overview_enabled']\n                assert all(x['overview_restored'] and x['restored_overview_camera']==r['before']['overview_camera'] for x in entries[1:])\n                report=json.loads((Path(entries[2]['directory'])/'report.json').read_text())")
    test=replace(test,"passed_actual_HDMI_native_video_and_R4_depth_cache_regression", "passed_actual_HDMI_single_linked_native_video_and_R4_depth_cache_regression")
    save(HERE/'test_native_UI_r4.py',test)
    verifier=(HERE/'verify_native_export_r3.py').read_text(encoding='utf-8')
    verifier=replace(verifier,"assert report['native_GUI_button'] and report['capture_fit_policy']=='native_C6_color_FBO_aspect_preserved'",
        "linked=report['linked_overview_enabled'];pane=report['pane_output_size']\n    assert report['native_GUI_button'] and report['capture_fit_policy']==('native_C6_and_linked_overview_FBOs_aspect_preserved' if linked else 'native_C6_color_FBO_aspect_preserved')\n    assert pane[0]*9==pane[1]*16 and report['output_size']==[pane[0]*(2 if linked else 1),pane[1]]")
    verifier=replace(verifier,"for n,d in report['source_sha256'].items():",'''linked_checks=[]
    if linked:
        assert report['overview_native_size']==[640,360]
        for r in trace[:moving]:
            m=r['completed_frame'];v=r['linked_overview']
            assert v['valid'] and v['enabled'] and v['sequence']==m['sequence']
            assert v['pose_source']=='presented_PL_frame' and v['same_live_route_frustum_painter']
            assert v['native_size']==[640,360] and v['ordinary_opacity_renderer']=='accepted_R4_nearest_shell_cache'
            assert abs(v['arc_mm']-m['arc_mm'])<.001
            for key in ('camera_lps','forward_lps','right_lps','up_lps'):
                np.testing.assert_allclose(v[key],m[key],atol=2e-5,rtol=0)
            eye=np.array(m['camera_lps']);f=np.array(m['forward_lps']);right=np.array(m['right_lps']);up=np.array(m['up_lps'])
            vertical=15*m['field'];horizontal=vertical*640/360;far=eye+f*15
            corners=np.array([far+right*horizontal+up*vertical,far-right*horizontal+up*vertical,
                              far-right*horizontal-up*vertical,far+right*horizontal-up*vertical])
            np.testing.assert_allclose(v['corners_lps'],corners,atol=1e-4,rtol=0)
            assert v['overview_camera']==trace[0]['linked_overview']['overview_camera']
        # With updates suspended, reference-camera changes never rebuild geometry.
        assert all(r['linked_overview']['geometry_cache_builds_this_capture']==0 for r in trace[1:moving])
    for n,d in report['source_sha256'].items():''')
    verifier=replace(verifier,"w,h=report['output_size'];data=",'''if linked:
            v=r['linked_overview'];raw=directory/m['overview_reference']
            assert sha(raw)==r['overview_color_sha256'] and raw.stat().st_size==640*360*4
            overview=np.fromfile(raw,np.uint8).reshape(360,640,4)
            assert np.all(overview[:,:,3]==255) and float(overview[:,:,:3].std())>10
            if pane==[640,360]:np.testing.assert_array_equal(image[:,:640,:],overview)
            matrix=np.asarray(v['mvp_column_major']).reshape(4,4,order='F')
            at=matrix@np.r_[v['camera_lps'],1.];projected=None;marker=False
            if at[3]>0 and -at[3]<=at[2]<=at[3]:
                x=int(round((at[0]/at[3]+1)*320));y=int(round((1-at[1]/at[3])*180));projected=[x,y]
                if 8<=x<632 and 35<=y<352:
                    crop=overview[y-7:y+8,x-7:x+8,:3].astype(int)
                    marker=bool(np.any((crop[:,:,0]<170)&(crop[:,:,1]>180)&(crop[:,:,2]>180)))
                    assert marker,('Reference marker missing at independently projected position',r['frame_index'],x,y)
            linked_checks.append(dict(frame_index=r['frame_index'],native_overview_RGBA_and_video_pane_equal=pane==[640,360],
                independently_projected_camera_pixel=projected,cyan_camera_marker_found=marker))
        w,h=report['output_size'];data=''')
    verifier=replace(verifier,"color_checks.append(dict(frame_index=r['frame_index']",'''if linked:
            for half in range(2):
                piece=difference[:,half*pane[0]:(half+1)*pane[0],:]
                assert float(piece.mean())<6 and float(np.percentile(piece,99))<35
        color_checks.append(dict(frame_index=r['frame_index']''')
    verifier=replace(verifier,"assert len(color_checks)==3 and len(checks)==6", "assert len(color_checks)==3 and len(checks)==6\n    if linked:assert len(linked_checks)==3 and any(x['cyan_camera_marker_found'] for x in linked_checks)")
    verifier=replace(verifier,"frame_checks=checks,decoded_color_checks=color_checks,", "linked_overview_enabled=linked,linked_reference_checks=linked_checks,all_route_frames_reference_pose_synced=True,\n        frame_checks=checks,decoded_color_checks=color_checks,")
    save(HERE/'verify_native_export_r4.py',verifier)
    files=[HERE/n for n in ('prepare_UI_r4.py','UI_feature_r4.inc','encoder_UI_r3.hpp','frame_r2.hpp','linked_view_r1.inc','test_native_UI_r4.py','verify_native_export_r4.py')]
    files +=[UI/n for n in ('src/main_media_r4.cpp','src/views_media_r4.cpp','src/views_media_r4.hpp','build_media_r4.sh','run_media_r4.sh')]
    new=dict(old,status='accepted_R3_single_video_plus_native_linked_overview_candidate',source_sha256=dict(old['source_sha256']))
    for p in files:new['source_sha256'][p.relative_to(ROOT).as_posix()]=sha(p)
    save(UI/'source_closure_media_r4.json',json.dumps(new,indent=2)+'\n')
    print('Derived single and linked video candidate; accepted UI unchanged',flush=True)
if __name__=='__main__':main()
