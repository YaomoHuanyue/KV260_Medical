"""Derive UI-only camera/control synchronization from the tested R20 UI."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    edits=[]
    def change(parent,child,changes):
        source=(ROOT/parent).read_text(encoding='utf-8')
        for before,after in changes:
            count=3 if before=='main_complete_scene_r20' else 1
            assert source.count(before)==count,(parent,before,source.count(before));source=source.replace(before,after)
        if (ROOT/child).exists():assert (ROOT/child).read_text(encoding='utf-8')==source,child
        else:
            with (ROOT/child).open('x',encoding='utf-8',newline='\n') as f:f.write(source)
        if child.endswith('.py'):compile(source,child,'exec')
        edits.append(dict(parent=parent,parent_sha256=sha(ROOT/parent),child=child,child_sha256=sha(ROOT/child),changes=changes))
    change('ui/releases/feature_completion_r6/src/controls_focus_r3.inc','ui/releases/feature_completion_r6/src/controls_sync_r21.inc',[
        (' QLabel*navigationPosition=nullptr;double navigationSpeedCurrent=2.;',''' QLabel*navigationPosition=nullptr;QCheckBox*navigationAlign=nullptr;double navigationSpeedCurrent=2.;
 // Update presentation from the continuous camera without sending a slider
 // change back into setCamera, which would snap to a sampled path position.
 void syncNavigationControlsFromCamera(){
  if(!scope||!cameraSlider||!navigationPosition)return;
  {QSignalBlocker blocked(cameraSlider);cameraSlider->setValue(scope->cameraForDistance(scope->distance()));}
  navigationPosition->setText(QString(u("位置 %1 / %2 mm")).arg(scope->distance(),0,'f',1).arg(scope->totalDistance(),0,'f',1));
  if(navigationAlign){QSignalBlocker blocked(navigationAlign);navigationAlign->setChecked(scope->scopeViewState()["auto_align"].toBool());}
 }'''),
        ('''  QSignalBlocker blocked(cameraSlider);cameraSlider->setValue(scope->cameraForDistance(scope->distance()));
  navigationPosition->setText(QString(u("位置 %1 / %2 mm")).arg(scope->distance(),0,'f',1)
   .arg(scope->totalDistance(),0,'f',1));''','  syncNavigationControlsFromCamera();')])
    change('ui/releases/feature_completion_r6/src/active_recovery_UI_r20.inc','ui/releases/feature_completion_r6/src/active_recovery_UI_r21.inc',[
        (' QJsonArray activeRecoveryChecks;QTimer activeRecoveryTimer;',''' QJsonArray activeRecoveryChecks;QTimer activeRecoveryTimer;QJsonObject activeRecoveryBeforeControls;
 QJsonObject recoveryNavigationControls()const{
  return {{"slider_index",cameraSlider->value()},{"expected_slider_index",scope->cameraForDistance(scope->distance())},
   {"position_label",navigationPosition->text()},
   {"expected_position_label",QString(u("位置 %1 / %2 mm")).arg(scope->distance(),0,'f',1).arg(scope->totalDistance(),0,'f',1)},
   {"align_checkbox",navigationAlign->isChecked()},{"camera_auto_align",scope->scopeViewState()["auto_align"]},
   {"continuous_distance_mm",scope->distance()}};
 }
 void checkRecoveryControls(QString phase){auto c=recoveryNavigationControls();
  recoveryCheck(phase+"_slider_matches_actual_camera",c["slider_index"]==c["expected_slider_index"]);
  recoveryCheck(phase+"_position_label_matches_actual_camera",c["position_label"]==c["expected_position_label"]);
  recoveryCheck(phase+"_align_checkbox_matches_actual_camera",c["align_checkbox"]==c["camera_auto_align"]);
 }'''),
        ('{"checks",activeRecoveryChecks},{"before_scene",activeRecoveryBefore}', '{"checks",activeRecoveryChecks},{"before_controls",activeRecoveryBeforeControls},{"after_controls",recoveryNavigationControls()},{"before_scene",activeRecoveryBefore}'),
        ('''   lesionList->setCurrentIndex(index);dualCheck->setChecked(true);tabs->setCurrentIndex(2);scope->setDistance(std::min(35.f,scope->totalDistance()*.3f));
   for(auto*c:findChildren<QCheckBox*>())if(c->text()==u("自动对齐路径")&&c->isChecked())QTest::mouseClick(c,Qt::LeftButton);''','''   lesionList->setCurrentIndex(index);dualCheck->setChecked(true);tabs->setCurrentIndex(2);
   if(navigationAlign->isChecked())QTest::mouseClick(navigationAlign,Qt::LeftButton);
   cameraSlider->setFocus();QTest::keyClick(cameraSlider,Qt::Key_Home);
   int sliderTarget=qMin(cameraSlider->maximum()-1,qMax(1,scope->cameraForDistance(std::min(35.f,scope->totalDistance()*.3f))));
   for(int i=0;i<sliderTarget;++i)QTest::keyClick(cameraSlider,Qt::Key_Right);
   recoveryCheck("real_slider_keyboard_changed_camera",cameraSlider->value()==sliderTarget&&scope->distance()>0);
   double sliderDistance=scope->distance();navigationStep->setValue(1.37);QTest::mouseClick(navForward,Qt::LeftButton);
   recoveryCheck("real_forward_button_preserves_continuous_distance",std::abs(scope->distance()-(sliderDistance+1.37))<1.e-4);
   checkRecoveryControls("before_action");'''),
        ('''    if(activeRecoveryStage==1){activeRecoveryBeforeScope=scope->scopeViewState();activeRecoveryBeforeOverview=overview->overviewCamera();
     activeRecoveryStage=2;QTest::mouseClick(recoveryButton,Qt::LeftButton);return;}''','''    if(activeRecoveryStage==1){activeRecoveryBeforeScope=scope->scopeViewState();activeRecoveryBeforeOverview=overview->overviewCamera();
     activeRecoveryBeforeControls=recoveryNavigationControls();tabs->setCurrentIndex(0);
     activeRecoveryStage=2;QTest::mouseClick(recoveryButton,Qt::LeftButton);return;}'''),
        ('    activeRecoveryFrame=shown;recoveryCheck(', '    checkRecoveryControls("restored_presented_frame");capture("restored_navigation_controls");\n    activeRecoveryFrame=shown;recoveryCheck('),
        ('  recoveryCheck("manual_camera_and_overview_restored",', '''  checkRecoveryControls("after_action");recoveryCheck("continuous_camera_and_controls_restored_exact",recoveryNavigationControls()==activeRecoveryBeforeControls);
  recoveryCheck("manual_camera_and_overview_restored",''')])
    change('ui/releases/feature_completion_r6/src/main_complete_scene_r20.cpp','ui/releases/feature_completion_r6/src/main_complete_scene_r21.cpp',[
        ('controls_focus_r3.inc','controls_sync_r21.inc'),('active_recovery_UI_r20.inc','active_recovery_UI_r21.inc'),
        ('auto*alignCheck=new QCheckBox','navigationAlign=new QCheckBox'),
        ('alignCheck->setChecked(true);navTools->addWidget(alignCheck);','navigationAlign->setChecked(true);navTools->addWidget(navigationAlign);'),
        ('connect(alignCheck,&QCheckBox::toggled,scope,','connect(navigationAlign,&QCheckBox::toggled,scope,'),
        ('scope->onCamera=[this](int i){cameraSlider->setValue(i);};','scope->onCamera=[this](int){syncNavigationControlsFromCamera();if(playing){playbackStart=scope->distance();playbackClock.restart();}};'),
        ('scope->onPoseChanged=[this]{if(plScope->active()&&!processing())','scope->onPoseChanged=[this]{syncNavigationControlsFromCamera();if(plScope->active()&&!processing())')])
    change('modules/surface_route/board_native_build_r20.py','modules/surface_route/board_native_build_r21.py',[
        ("out=folder/'build_complete_scene_r20'","out=folder/'build_complete_scene_r21'"),
        ("parent=folder/'build_complete_scene_r19'","parent=folder/'build_complete_scene_r20'"),
        ('native_UI_source_closure_r20','native_UI_source_closure_r21'),
        ('main_complete_scene_r20','main_complete_scene_r21'),('R20 native adapter','R21 native adapter')])
    parent=ROOT/'modules/surface_route/native_UI_source_closure_r20.json';files=json.loads(parent.read_text())['files_sha256']
    for n,h in files.items():assert sha(ROOT/n)==h,n
    names=[e['child'] for e in edits]+['tools/derive_navigation_sync_r21.py']
    files.update({n:sha(ROOT/n) for n in names})
    with (ROOT/'modules/surface_route/native_UI_source_closure_r21.json').open('x',encoding='utf-8') as f:
        json.dump(dict(files_sha256=files,parent_sha256=sha(parent),change='camera driven navigation position, slider and alignment controls; actual keyboard slider and continuous forward/recovery regression',production_promoted=False),f,indent=2);f.write('\n')
    with (ROOT/'modules/navigation_controls/active_derivation_r21.json').open('x',encoding='utf-8') as f:json.dump(dict(edits=edits,new_bitstream=False,renderer_and_transport_objects_unchanged=True),f,indent=2);f.write('\n')
    print('R21 navigation synchronization and actual controls regression derived')

if __name__=='__main__':main()
