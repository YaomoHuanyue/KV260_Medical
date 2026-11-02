 QDoubleSpinBox*navigationSpeed=nullptr,*navigationStep=nullptr;
 QPushButton*navBackward=nullptr,*navForward=nullptr,*navStart=nullptr,*navEnd=nullptr;
 QLabel*navigationPosition=nullptr;double navigationSpeedCurrent=2.;
 bool controlsTesting=qEnvironmentVariableIntValue("KV260_NAV_CONTROLS_TEST")==1;
 int controlsStage=0,controlsWait=0;QJsonArray controlsTrace;
 QElapsedTimer controlsClock;double controlsExpected=0.;
 bool keyboardNavigationAllowed()const{
  auto*f=QApplication::focusWidget();
  return tabs->currentIndex()==2&&!processing()&&scope->cameraCount()>0&&
   !qobject_cast<QLineEdit*>(f)&&!qobject_cast<QAbstractSpinBox*>(f)&&!qobject_cast<QComboBox*>(f);
 }
 void navigationPause(){
  if(playing)navigationTick();
  play.stop();playing=false;scope->setPlayback(false);playButton->setText(u("沿路径播放"));
 }
 void navigationAt(double at){
  scope->setDistance(float(medical_motion::step(at,0,scope->totalDistance())));
  QSignalBlocker blocked(cameraSlider);cameraSlider->setValue(scope->cameraForDistance(scope->distance()));
  navigationPosition->setText(QString(u("位置 %1 / %2 mm")).arg(scope->distance(),0,'f',1)
   .arg(scope->totalDistance(),0,'f',1));
 }
 void navigationMove(double delta){
  if(processing()||scope->cameraCount()==0)return;
  navigationPause();navigationAt(medical_motion::step(scope->distance(),delta,scope->totalDistance()));
 }
 void navigationBoundary(bool end){
  if(processing()||scope->cameraCount()==0)return;
  navigationPause();if(!end)scope->resetView();navigationAt(end?scope->totalDistance():0);
 }
 void navigationToggle(){
  if(processing()||scope->cameraCount()==0)return;
  if(playing){navigationPause();return;}
  playbackStart=scope->distance();navigationSpeedCurrent=navigationSpeed->value();
  playbackClock.restart();playing=true;scope->setPlayback(true);
  playButton->setText(u("暂停"));play.start(40);
 }
 void navigationTick(){
  double at=medical_motion::position(playbackStart,playbackClock.elapsed(),
   navigationSpeedCurrent,scope->totalDistance());navigationAt(at);
  if(at>=scope->totalDistance()){
   play.stop();playing=false;scope->setPlayback(false);playButton->setText(u("沿路径播放"));
  }
  if(navigationTesting&&navigationBenchmarking){auto sample=scope->cameraRequest();
   sample["elapsed_ms"]=double(playbackClock.elapsed());playbackTestTrace.append(sample);}
 }
 void navigationControls(QVBoxLayout*layout){
  auto*row=new QHBoxLayout;
  row->addWidget(new QLabel(u("速度")));navigationSpeed=new QDoubleSpinBox;
  navigationSpeed->setRange(.25,20);navigationSpeed->setDecimals(2);navigationSpeed->setValue(2);
  navigationSpeed->setSuffix(" mm/s");navigationSpeed->setMaximumWidth(110);row->addWidget(navigationSpeed);
  row->addWidget(new QLabel(u("步长")));navigationStep=new QDoubleSpinBox;
  navigationStep->setRange(.25,10);navigationStep->setDecimals(2);navigationStep->setValue(2);
  navigationStep->setSuffix(" mm");navigationStep->setMaximumWidth(100);row->addWidget(navigationStep);
  navBackward=new QPushButton(u("后退"));navForward=new QPushButton(u("前进"));
  navStart=new QPushButton(u("起点"));navEnd=new QPushButton(u("终点"));
  for(auto*b:{navBackward,navForward,navStart,navEnd})row->addWidget(b);
  layout->addLayout(row);navigationPosition=new QLabel(u("位置 0 mm · W/D/→ 前进，S/A/← 后退；1/2 调步长；Home/End"));
  layout->addWidget(navigationPosition);
  connect(navBackward,&QPushButton::clicked,this,[this]{navigationMove(-navigationStep->value());});
  connect(navForward,&QPushButton::clicked,this,[this]{navigationMove(navigationStep->value());});
  connect(navStart,&QPushButton::clicked,this,[this]{navigationBoundary(false);});
  connect(navEnd,&QPushButton::clicked,this,[this]{navigationBoundary(true);});
  connect(navigationSpeed,QOverload<double>::of(&QDoubleSpinBox::valueChanged),this,[this](double v){
   if(playing){navigationTick();playbackStart=scope->distance();playbackClock.restart();}
   navigationSpeedCurrent=v;
  });
  auto shortcut=[this](int key,std::function<void()> action){
   auto*s=new QShortcut(QKeySequence(key),this);
   connect(s,&QShortcut::activated,this,[this,action]{if(keyboardNavigationAllowed())action();});
  };
  for(int key:{Qt::Key_W,Qt::Key_D,Qt::Key_Right,Qt::Key_Up})
   shortcut(key,[this]{navigationMove(navigationStep->value());});
  for(int key:{Qt::Key_S,Qt::Key_A,Qt::Key_Left,Qt::Key_Down})
   shortcut(key,[this]{navigationMove(-navigationStep->value());});
  shortcut(Qt::Key_1,[this]{navigationStep->setValue(qMax(.25,navigationStep->value()/2));});
  shortcut(Qt::Key_2,[this]{navigationStep->setValue(qMin(10.,navigationStep->value()*2));});
  for(int key:{Qt::Key_R,Qt::Key_Home})shortcut(key,[this]{navigationBoundary(false);});
  for(int key:{Qt::Key_E,Qt::Key_End})shortcut(key,[this]{navigationBoundary(true);});
  shortcut(Qt::Key_Space,[this]{navigationToggle();});
  scope->setFocusPolicy(Qt::StrongFocus);scope->installEventFilter(this);
 }
 bool eventFilter(QObject*object,QEvent*event)override{
  if(object==scope&&tabs->currentIndex()==2&&event->type()==QEvent::Wheel){
   auto*wheel=static_cast<QWheelEvent*>(event);
   if(wheel->angleDelta().y()!=0){navigationMove(navigationStep->value()*wheel->angleDelta().y()/120.);
    wheel->accept();return true;}
  }
  return QWidget::eventFilter(object,event);
 }
 void controlsCheck(QString action,double expected){
  double actual=scope->distance();bool exact=std::abs(actual-expected)<2e-4;
  controlsTrace.append(QJsonObject{{"action",action},{"expected_mm",expected},{"actual_mm",actual},
   {"within_0_0002mm",exact},{"camera",scope->cameraRequest()}});if(!exact)failed=true;
 }
 void controlsFinish(bool passed){
  play.stop();playing=false;scope->setPlayback(false);QDir().mkpath(evidence);
  auto presented=scope->presentedScopeFrame();
  if(passed&&(presented.isEmpty()||presented["pose_source"]!="completed_PL_frame"||
    std::abs(presented["arc_mm"].toDouble()-scope->distance())>.001))passed=false;
  grab().save(evidence+"/navigation_controls.png");
  writeJson(evidence+"/controls_UI.json",QJsonObject{
   {"status",passed?"passed_actual_Qt_physical_navigation_controls":"failed"},
   {"actions",controlsTrace},{"presented_frame",presented},{"current_camera",scope->cameraRequest()},
   {"UI_peak_RSS_MiB",peakRSS()},{"physical_mouse_verified",false},
   {"additional_PL_resources",0},{"production_UI_replaced",false}});
  close();if(!passed)QTimer::singleShot(100,[]{QApplication::exit(1);});
 }
 void controlsAdvance(){
  if(!controlsTesting)return;
  if(failed||source.isEmpty()){controlsFinish(false);return;}
  tabs->setCurrentIndex(2);scope->setFocus();
  switch(controlsStage++){
   case 0:if(scope->presentedScopeFrame().isEmpty()){
    --controlsStage;if(++controlsWait>100){controlsFinish(false);return;}break;}
    QTest::keyClick(scope,Qt::Key_D);break;
   case 1:controlsCheck("D_forward",2);QTest::mouseClick(navForward,Qt::LeftButton);break;
   case 2:controlsCheck("button_forward",4);QTest::keyClick(scope,Qt::Key_1);QTest::keyClick(scope,Qt::Key_S);break;
   case 3:controlsCheck("smaller_step_and_S_back",3);QTest::keyClick(scope,Qt::Key_2);
    QTest::mouseClick(navBackward,Qt::LeftButton);break;
   case 4:controlsCheck("larger_step_and_button_back",1);QTest::keyClick(scope,Qt::Key_Home);break;
   case 5:controlsCheck("Home_start",0);QTest::keyClick(scope,Qt::Key_End);break;
   case 6:controlsCheck("End_terminal",scope->totalDistance());QTest::keyClick(scope,Qt::Key_W);break;
   case 7:controlsCheck("forward_clamped_at_end",scope->totalDistance());
    QTest::mouseClick(navStart,Qt::LeftButton);break;
   case 8:controlsCheck("button_start",0);navigationSpeed->setValue(4);
    QTest::keyClick(scope,Qt::Key_Space);controlsClock.restart();
    QTimer::singleShot(900,this,[this]{controlsAdvance();});return;
   case 9:{double before=scope->distance();double elapsed=playbackClock.elapsed();
    QTest::keyClick(scope,Qt::Key_Space);double after=scope->distance();
    double elapsedAfter=playbackClock.elapsed();
    bool good=!playing&&after>=elapsed*.004-2e-4&&after<=elapsedAfter*.004+2e-4&&after>2.8;
    controlsTrace.append(QJsonObject{{"action","4mm_s_play_pause"},{"elapsed_ms",elapsed},
     {"before_mm",before},{"actual_mm",after},{"physical_clock_passed",good}});
    if(!good)failed=true;
    navigationSpeed->setValue(1);QTest::mouseClick(playButton,Qt::LeftButton);break;}
   case 10:{double before=scope->distance();
    double low=medical_motion::position(playbackStart,playbackClock.elapsed(),navigationSpeedCurrent,scope->totalDistance());
    navigationSpeed->setValue(8);double after=scope->distance();
    bool good=playing&&after>=before&&after>=low-2e-4&&
      std::abs(after-playbackStart)<2e-4;
    controlsTrace.append(QJsonObject{{"action","live_speed_change_without_rewinding"},
     {"before_mm",before},{"after_mm",after},{"passed",good}});if(!good)failed=true;break;}
   case 11:QTest::mouseClick(playButton,Qt::LeftButton);
    navigationStep->setValue(.25);controlsExpected=scope->distance()+.25;
    {QWheelEvent wheel(QPointF(100,100),scope->mapToGlobal(QPoint(100,100)),QPoint(),
     QPoint(0,120),Qt::NoButton,Qt::NoModifier,Qt::NoScrollPhase,false);
     QApplication::sendEvent(scope,&wheel);}break;
   case 12:controlsCheck("wheel_one_detent_0_25mm",controlsExpected);
    QTest::mouseClick(navEnd,Qt::LeftButton);break;
   case 13:controlsCheck("button_end",scope->totalDistance());
    QTest::mouseClick(navStart,Qt::LeftButton);break;
   case 14:controlsCheck("return_to_start",0);break;
   default:if(scope->metrics()["last_paint_awaiting_pl"].toBool()||
     std::abs(scope->presentedScopeFrame()["arc_mm"].toDouble()-scope->distance())>.001){
      --controlsStage;if(++controlsWait>100){controlsFinish(false);return;}break;}
    controlsFinish(!failed);return;
  }
  QTimer::singleShot(300,this,[this]{controlsAdvance();});
 }
