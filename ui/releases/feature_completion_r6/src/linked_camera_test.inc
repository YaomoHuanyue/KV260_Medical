 bool linkedTesting=qEnvironmentVariableIntValue("KV260_LINKED_CAMERA_TEST")==1;
 int linkedStep=-1,linkedWaitBase=0;QElapsedTimer linkedClock,linkedHold;QJsonObject linkedReport;QJsonArray linkedTrace;
 void linkedRecordFrame(){
  auto frame=scope->presentedScopeFrame(),ref=miniOverview->referenceCameraMetrics();
  linkedTrace.append(QJsonObject{{"step",linkedStep},{"elapsed_ms",double(linkedClock.elapsed())},{"frame",frame},{"reference",ref},{"requested",scope->cameraRequest()}});
  if(frame["sequence"]!=ref["sequence"]||!ref["valid"].toBool())failed=true;
  for(auto key:{"camera_lps","forward_lps","right_lps","up_lps"}){auto a=frame[key].toArray(),b=ref[key].toArray();if(a.size()!=3||b.size()!=3){failed=true;continue;}for(int i=0;i<3;++i)if(std::abs(a[i].toDouble()-b[i].toDouble())>3e-5)failed=true;}
  if(std::abs(ref["aspect"].toDouble()-double(frame["width"].toInt())/frame["height"].toInt())>1e-5)failed=true;
 }
 void linkedStart(){
  linkedStep=0;linkedClock.restart();linkedHold.restart();scope->setAutoAlign(false);dualCheck->setChecked(true);syncLinkedOverview();linkedWaitBase=plFrames;
  linkedReport["initial_reference"]=miniOverview->referenceCameraMetrics();
  QTimer::singleShot(100,this,[this]{linkedAdvance();});
 }
 void linkedAdvance(){
  if(linkedClock.elapsed()>25000){failed=true;linkedReport["status"]="timeout";finishTest();return;}
  auto frame=scope->presentedScopeFrame();auto pose=scope->cameraRequest();
  bool current=frame["sequence"].toInt()>0&&frame["width"]==pose["width"]&&frame["height"]==pose["height"];
  if(dualCheck->isChecked()&&!frame.isEmpty())linkedRecordFrame();
  switch(linkedStep){
   case 0:if(current&&plFrames>=linkedWaitBase+2){
    capture("linked_01_open");auto ref=miniOverview->referenceCameraMetrics();testDrag(scope,QPoint(100,100),QPoint(210,140));
    auto after=scope->cameraRequest();linkedReport["manual_request"]=after;
    bool held=miniOverview->referenceCameraMetrics()==ref&&std::abs(after["manual_yaw_degrees"].toDouble())>20;
    linkedReport["pending_request_keeps_presented_reference"]=held;if(!held)failed=true;
    linkedStep=1;linkedHold.restart();
   }break;
   case 1:if(current&&std::abs(frame["manual_yaw_degrees"].toDouble())>20&&!frame["auto_align"].toBool()){
    capture("linked_02_manual");linkedReport["manual_frame"]=frame;linkedStep=2;linkedHold.restart();
   }break;
   case 2:if(linkedHold.elapsed()>900){
    if(std::abs(pose["manual_yaw_degrees"].toDouble())<20)failed=true;
    linkedReport["manual_preserved_with_auto_align_off"]=true;scope->setAutoAlign(true);linkedStep=3;linkedHold.restart();
   }break;
   case 3:
    if(frame["auto_align"].toBool()&&std::abs(frame["manual_yaw_degrees"].toDouble())>.1&&std::abs(frame["manual_yaw_degrees"].toDouble())<20)linkedReport["intermediate_auto_return_observed"]=true;
    if(current&&linkedHold.elapsed()>1000&&!frame["interactive"].toBool()&&std::abs(frame["manual_yaw_degrees"].toDouble())<.1){
     capture("linked_03_aligned");linkedReport["aligned_frame"]=frame;playButton->click();linkedStep=4;linkedHold.restart();linkedWaitBase=plFrames;
    }break;
   case 4:if(linkedHold.elapsed()>2200){
    playButton->click();linkedReport["playback_presented_frames"]=plFrames-linkedWaitBase;linkedReport["playback_frame"]=frame;
    if(plFrames-linkedWaitBase<10)failed=true;scope->setAutoAlign(false);dualCheck->setChecked(false);testDrag(scope,QPoint(200,140),QPoint(90,110));linkedStep=5;linkedHold.restart();
   }break;
   case 5:if(current&&!frame["interactive"].toBool()&&frame["manual_yaw_degrees"].toDouble()<-20){
    auto shown=scope->presentedScopeFrame();dualCheck->setChecked(true);syncLinkedOverview();auto ref=miniOverview->referenceCameraMetrics();
    bool matches=ref["sequence"]==shown["sequence"];auto a=ref["forward_lps"].toArray(),b=shown["forward_lps"].toArray();for(int i=0;i<3;++i)matches=matches&&std::abs(a[i].toDouble()-b[i].toDouble())<3e-5;
    linkedReport["reopen_uses_current_manual_frame"]=matches;
    if(!linkedReport["reopen_uses_current_manual_frame"].toBool())failed=true;
    linkedStep=6;linkedHold.restart();linkedWaitBase=plFrames;
   }break;
   case 6:if(current&&plFrames>=linkedWaitBase+1){
    capture("linked_04_reopened_manual");linkedReport["reopened_frame"]=frame;
    linkedReport["status"]=failed?"failed":"passed";linkedReport["pose_policy"]="Reference uses the presented PL frame, including manual orientation, FOV and actual aspect";
    linkedReport["frames_and_checks"]=linkedTrace.size();finishTest();return;
   }break;
  }
  QTimer::singleShot(100,this,[this]{linkedAdvance();});
 }
