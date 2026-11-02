 QCheckBox*breathingBox=nullptr;QTimer breathingTimer;double breathingPhase=0;bool breathingWaiting=false;
 QElapsedTimer breathingStepClock,breathingRateTestClock;bool breathingStepArmed=false;
 bool breathingTesting=qEnvironmentVariableIntValue("KV260_BREATHING_UI_TEST")==1;
 QTimer breathingTestTimer;QElapsedTimer breathingTestClock;int breathingTestStage=0,breathingTestBase=0;QJsonArray breathingChecks;QJsonObject breathingBeforeNavigation;QImage breathingBaseline;
 void syncBreathing(){
  if(!overview||scene.isEmpty())return;
  try{overview->setBreathing({breathingBox&&breathingBox->isChecked()&&tabs->currentIndex()==1,breathingPhase});}
  catch(const std::exception&e){QSignalBlocker blocked(breathingBox);breathingBox->setChecked(false);overview->setBreathing({});message(QString::fromUtf8(e.what()));}
 }
 void addBreathingControl(QVBoxLayout*layout){
  breathingBox=new QCheckBox(u("呼吸演示（仅总览）"));breathingBox->setToolTip(u("显示肺和气道的小幅缩放及位移；不改变CT、分割、网格或导航数据。导航时暂停；精确透明按完成帧推进。"));layout->addWidget(breathingBox);
  breathingTimer.setInterval(33);breathingTimer.setTimerType(Qt::PreciseTimer);
  connect(&breathingTimer,&QTimer::timeout,this,[this]{
   if(closing||finishingTest||processing()||tabs->currentIndex()!=1||!breathingBox->isChecked()){breathingStepArmed=false;return;}
   if(overview->compositeMode()&&(breathingWaiting||compositeQuiet.isActive()||overview->compositePreviewMode())){breathingStepArmed=false;return;}
   double step=.35;
   if(!overview->compositeMode()){step=breathingStepArmed?double(breathingStepClock.elapsed())*.001:.033;breathingStepClock.restart();breathingStepArmed=true;}else breathingStepArmed=false;
   breathingPhase+=step;syncBreathing();
   if(overview->compositeMode()){breathingWaiting=true;if(plComposite->active())plComposite->request(overview->overviewRequest());else configureScope();}
  });
  connect(breathingBox,&QCheckBox::toggled,this,[this]{breathingWaiting=false;breathingStepArmed=false;syncBreathing();
   if(tabs->currentIndex()==1&&overview->compositeMode()&&!processing()){compositeQuiet.stop();overview->setCompositePreview(false);breathingWaiting=true;configureScope();}});
  breathingTimer.start();
 }
 void breathingCheck(QString name,bool passed){breathingChecks.append(QJsonObject{{"case",name},{"passed",passed}});if(!passed)throw std::runtime_error(("Breathing UI check: "+name).toStdString());}
 void breathingFinish(bool good,QString error={}){
  breathingTimer.stop();breathingTestTimer.stop();finishingTest=true;
  writeJson(evidence+"/breathing_UI.json",QJsonObject{{"status",good?"passed_actual_Qt_breathing_fast_precise_and_navigation_pause":"failed"},
   {"error",error},{"checks",breathingChecks},{"scene",scenePath},{"request",overview->overviewRequest()},{"completed_precise_frame",overview->completedComposite()},
   {"complete_C7_trace",compositeTrace},{"navigation_trace",navigationTrace},{"display_only",true},{"new_bitstream",false},{"physical_review",false}});
  releaseGraphics([good]{QApplication::exit(good?0:1);});
 }
 void breathingTest(){
  if(!breathingTesting)return;QDir().mkpath(evidence);breathingTestClock.start();
  connect(&breathingTestTimer,&QTimer::timeout,this,[this]{try{
   if(failed||breathingTestClock.elapsed()>180000)throw std::runtime_error("Breathing UI timed out or failed");
   if(processing())return;
   switch(breathingTestStage){
    case 0:{tabs->setCurrentIndex(1);preciseBlend->setChecked(false);lungQuality->setCurrentIndex(0);for(auto*c:meshLayers)c->setChecked(true);overview->resetView();
     breathingTimer.stop();breathingBaseline=overview->grabFramebuffer();breathingBeforeNavigation=scope->scopeViewState();
     QTest::mouseClick(breathingBox,Qt::LeftButton,Qt::NoModifier,QPoint(10,breathingBox->height()/2));breathingPhase=1.5707963267948966;syncBreathing();
     auto pixels=overview->grabFramebuffer();breathingCheck("real_checkbox_enables_legacy_display_transform",breathingBox->isChecked()&&overview->overviewRequest()["breathing"].toObject()["enabled"].toBool()&&pixels!=breathingBaseline);
     pixels.save(evidence+"/fast_inhale.png");QTest::mouseClick(breathingBox,Qt::LeftButton,Qt::NoModifier,QPoint(10,breathingBox->height()/2));
     breathingCheck("disabled_restores_original_fast_pixels",overview->grabFramebuffer()==breathingBaseline);
     breathingCheck("navigation_camera_unchanged_by_overview",scope->scopeViewState()==breathingBeforeNavigation);
     QTest::mouseClick(breathingBox,Qt::LeftButton,Qt::NoModifier,QPoint(10,breathingBox->height()/2));breathingPhase=0;syncBreathing();breathingStepArmed=false;breathingRateTestClock.restart();breathingTimer.start();breathingTestStage=1;return;}
    case 1:if(breathingPhase<.7)return;{
     breathingTimer.stop();breathingCheck("wall_clock_preserves_one_radian_per_second_without_accumulated_navigation_time",breathingPhase>=.7&&std::abs(breathingPhase-breathingRateTestClock.elapsed()*.001)<.15);
     auto retained=breathingPhase;tabs->setCurrentIndex(2);breathingCheck("navigation_and_linked_overview_identity",!overview->overviewRequest()["breathing"].toObject()["enabled"].toBool()&&!miniOverview->overviewRequest()["breathing"].toObject()["enabled"].toBool()&&breathingPhase==retained);
     breathingTestBase=plFrames;breathingTestStage=2;return;}
    case 2:if(plFrames<=breathingTestBase)return;{
     breathingCheck("actual_C9_navigation_frame_after_pause",!scope->presentedScopeFrame().isEmpty());
     tabs->setCurrentIndex(1);breathingCheck("return_to_overview_retains_phase",overview->overviewRequest()["breathing"].toObject()["phase_radians"].toDouble()==breathingPhase);
     breathingPhase=.35;syncBreathing();breathingTestBase=compositeFrames;preciseBlend->setChecked(true);breathingTestStage=3;return;}
    case 3:if(compositeFrames<=breathingTestBase)return;{
     auto c=overview->completedComposite()["report"].toObject()["controls"].toObject()["breathing"].toObject();
     breathingCheck("fast_preview_option_does_not_starve_precise_animation",c==overview->overviewRequest()["breathing"].toObject()&&!overview->compositePreviewMode());
     overview->grabFramebuffer().save(evidence+"/precise_inhale.png");breathingTestBase=compositeFrames;breathingTimer.start();breathingTestStage=4;return;}
    case 4:if(compositeFrames<=breathingTestBase)return;{
     breathingTimer.stop();auto c=overview->completedComposite()["report"].toObject()["controls"].toObject()["breathing"].toObject();
     breathingCheck("second_precise_phase_completed_without_queue",c["enabled"].toBool()&&c["phase_radians"].toDouble()>.35);
     breathingFinish(true);return;}
   }
  }catch(const std::exception&e){breathingFinish(false,QString::fromUtf8(e.what()));}});
  breathingTestTimer.start(200);
 }
