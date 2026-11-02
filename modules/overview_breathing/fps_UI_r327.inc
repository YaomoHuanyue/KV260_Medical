 bool breathingFpsTesting=qEnvironmentVariableIntValue("KV260_BREATHING_FPS_TEST")==1;
 QTimer breathingFpsPoll;QElapsedTimer breathingFpsClock,breathingFpsDuration;
 bool breathingFpsCollect=false;int breathingFpsStage=0,breathingFpsQuality=0,breathingFpsRepeat=0;
 double breathingFpsLast=-1;QJsonArray breathingFpsSwaps,breathingFpsTrials,breathingFpsFixed;
 QJsonObject breathingFpsRequest;
 void breathingFpsFinish(bool ok,QString detail={}){
  breathingTimer.stop();breathingFpsPoll.stop();breathingFpsCollect=false;finishingTest=true;
  writeJson(evidence+"/breathing_fps_UI.json",QJsonObject{{"status",ok?"passed_actual_HDMI_breathing_fps_measurement":"failed"},
   {"detail",detail},{"scene",scenePath},{"fixed_phase_frames",breathingFpsFixed},{"trials",breathingFpsTrials},
   {"render_metrics",overview->metrics()},{"same_full_geometry_and_native_resolution",true},
   {"sample_window_ms",8000},{"repeats_per_quality",3},{"new_bitstream",false},{"physical_review",false}});
  releaseGraphics([ok]{QApplication::exit(ok?0:1);});
 }
 void breathingFpsAdvance(){
  try{
   if(failed)throw std::runtime_error("Case preparation failed");
   if(processing())return;
   if(breathingFpsStage==0){
    tabs->setCurrentIndex(1);preciseBlend->setChecked(false);clipCheck->setChecked(false);
    colorMode->setCurrentIndex(0);for(auto*c:meshLayers)c->setChecked(true);
    lungQuality->setCurrentIndex(breathingFpsQuality);overview->resetView();breathingTimer.stop();
    const double phases[]={0.,.35,1.5707963267948966,3.141592653589793,4.71238898038469};
    for(double phase:phases){
     breathingBox->setChecked(true);breathingPhase=phase;syncBreathing();auto frame=overview->grabFramebuffer();
     if(frame.isNull()||!overview->metrics()["error"].toString().isEmpty())throw std::runtime_error("Invalid breathing GPU frame");
     QByteArray pixels(reinterpret_cast<const char*>(frame.constBits()),int(frame.sizeInBytes()));
     breathingFpsFixed.append(QJsonObject{{"quality",breathingFpsQuality},{"phase",phase},
      {"width",frame.width()},{"height",frame.height()},{"format",int(frame.format())},
      {"RGBA_sha256",QString(QCryptographicHash::hash(pixels,QCryptographicHash::Sha256).toHex())},
      {"request",overview->overviewRequest()}});
    }
    breathingBox->setChecked(false);syncBreathing();auto frame=overview->grabFramebuffer();
    QByteArray pixels(reinterpret_cast<const char*>(frame.constBits()),int(frame.sizeInBytes()));
    breathingFpsFixed.append(QJsonObject{{"quality",breathingFpsQuality},{"enabled",false},
     {"width",frame.width()},{"height",frame.height()},{"format",int(frame.format())},
     {"RGBA_sha256",QString(QCryptographicHash::hash(pixels,QCryptographicHash::Sha256).toHex())},
     {"request",overview->overviewRequest()}});
    breathingFpsStage=1;return;
   }
   if(breathingFpsStage==1){
    breathingTimer.stop();breathingBox->setChecked(false);breathingPhase=0;syncBreathing();
    breathingBox->setChecked(true);overview->grabFramebuffer();
    breathingFpsRequest=overview->overviewRequest();breathingFpsSwaps={};breathingFpsLast=0;
    breathingFpsClock.restart();breathingFpsDuration.restart();breathingFpsCollect=true;
    breathingTimer.start();breathingFpsStage=2;return;
   }
   if(breathingFpsStage==2){
    if(breathingFpsDuration.elapsed()<8000)return;
    breathingTimer.stop();breathingFpsCollect=false;double duration=breathingFpsDuration.elapsed();
    if(breathingFpsSwaps.size()<3)throw std::runtime_error("Too few real updated swap frames");
    breathingFpsTrials.append(QJsonObject{{"quality",breathingFpsQuality},{"repeat",breathingFpsRepeat},
     {"elapsed_ms",duration},{"changed_phase_swaps",breathingFpsSwaps},
     {"actual_changed_frame_fps",1000.*breathingFpsSwaps.size()/duration},
     {"phase_start",0.},{"phase_end",breathingPhase},{"timer_interval_ms",breathingTimer.interval()},
     {"first_request",breathingFpsRequest},{"last_request",overview->overviewRequest()}});
    if(++breathingFpsRepeat<3){breathingFpsStage=1;return;}
    if(++breathingFpsQuality<2){breathingFpsRepeat=0;breathingFpsStage=0;return;}
    breathingFpsFinish(true);return;
   }
  }catch(const std::exception&e){breathingFpsFinish(false,QString::fromUtf8(e.what()));}
 }
 void breathingFpsTest(){
  if(!breathingFpsTesting)return;QDir().mkpath(evidence);
  connect(overview,&QOpenGLWidget::frameSwapped,this,[this]{
   if(!breathingFpsCollect)return;auto request=overview->overviewRequest();
   if(!request["breathing"].toObject()["enabled"].toBool()||request["breathing"].toObject()["phase_radians"].toDouble()==breathingFpsLast)return;
   breathingFpsLast=request["breathing"].toObject()["phase_radians"].toDouble();
   breathingFpsSwaps.append(QJsonObject{{"elapsed_ms",double(breathingFpsClock.elapsed())},{"phase",breathingFpsLast}});
  });
  connect(&breathingFpsPoll,&QTimer::timeout,this,[this]{breathingFpsAdvance();});breathingFpsPoll.start(50);
 }
