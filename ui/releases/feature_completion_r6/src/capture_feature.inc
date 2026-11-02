 QPushButton*snapshotButton=nullptr;bool capturePending=false,captureRunning=false;
 QElapsedTimer captureWait;std::thread captureThread;
 bool captureTesting=qEnvironmentVariableIntValue("KV260_CAPTURE_UI_TEST")==1;
 int captureStep=0;QJsonArray captureTrace;
 void captureRequest(){
  if(processing()||capturePending||input.isEmpty())return;
  capturePending=true;captureWait.start();snapshotButton->setEnabled(false);capturePoll();
 }
 void capturePoll(){
  if(!capturePending)return;
  if(tabs->currentIndex()==2&&scope->cameraCount()>0&&(scope->presentedScopeFrame().isEmpty()||scope->metrics()["last_paint_awaiting_pl"].toBool())){
   if(captureWait.elapsed()>5000){capturePending=false;snapshotButton->setEnabled(true);
    message(u("尚无完成的导航画面，请稍后重试截图"));if(captureTesting)captureTestFinish(false);return;}
   QTimer::singleShot(100,this,[this]{capturePoll();});return;
  }
  capturePending=false;captureRunning=true;
  QJsonObject before=scope->presentedScopeFrame();
  QMap<QString,QImage> images{{"window",grab().toImage()},{"active_view",tabs->currentWidget()->grab().toImage()}};
  QJsonObject after=scope->presentedScopeFrame();
  QJsonObject meta{{"input",input},{"input_sha256",scene["input_sha256"]},{"source_result",source},
   {"tab_index",tabs->currentIndex()},{"tab_name",tabs->tabText(tabs->currentIndex())},
   {"slice_indices",QJsonArray{slices[0]->currentSlice(),slices[1]->currentSlice(),slices[2]->currentSlice()}},
   {"overview_camera",overview->overviewCamera()},{"presented_scope_before_capture",before},
   {"presented_scope_after_capture",after},{"scope_pose_metadata_is_capture_boundary",true},
   {"navigation_available",scope->cameraCount()>0},{"display_only",true},{"source_masks_geometry_and_route_changed",false}};
  QString destination=root+"/ui/exports/snapshots";int startTick=ticks;
  captureThread=std::thread([this,images,meta,destination,startTick]{
   QJsonObject result;QString error;
   try{result=medical_capture::save(destination,images,meta);}
   catch(const std::exception&e){error=QString::fromUtf8(e.what());}
   QMetaObject::invokeMethod(this,[this,result,error,startTick]{
    if(captureThread.joinable())captureThread.join();captureRunning=false;
    snapshotButton->setEnabled(!input.isEmpty());
    if(!error.isEmpty()){message(error);if(captureTesting)captureTestFinish(false);return;}
    message(u("截图已保存至 ")+result["path"].toString());
    if(captureTesting){captureTrace.append(QJsonObject{{"capture",result},
      {"heartbeat_ticks_during_write",ticks-startTick}});++captureStep;
      QTimer::singleShot(300,this,[this]{captureTestAdvance();});}
   },Qt::QueuedConnection);
  });
 }
 void captureTestFinish(bool passed){
  QDir().mkpath(evidence);
  writeJson(evidence+"/capture_UI.json",QJsonObject{
    {"status",passed?"passed_actual_Qt_three_tabs_user_PNG_capture":"failed"},
    {"captures",captureTrace},{"UI_peak_RSS_MiB",peakRSS()},
    {"physical_mouse_verified",false},{"production_UI_replaced",false},{"Ctrl_S_exercised",captureStep==3},
    {"file_writes_on_worker_thread",true},{"new_medical_PL_core_loaded",false}});
  this->close();if(!passed)QTimer::singleShot(100,[]{QApplication::exit(1);});
 }
 void captureTestAdvance(){
  if(!captureTesting||captureRunning||capturePending)return;
  if(failed||source.isEmpty()){captureTestFinish(false);return;}
  if(captureStep==3){captureTestFinish(true);return;}
  if(tabs->currentIndex()!=captureStep){tabs->setCurrentIndex(captureStep);
   QTimer::singleShot(captureStep==2?1000:500,this,[this]{captureTestAdvance();});return;}
  if(captureStep==1)colorMode->setCurrentIndex(1);
  if(captureStep==2){scope->setFocus();QTest::keyClick(scope,Qt::Key_S,Qt::ControlModifier);}else QTest::mouseClick(snapshotButton,Qt::LeftButton);
 }
