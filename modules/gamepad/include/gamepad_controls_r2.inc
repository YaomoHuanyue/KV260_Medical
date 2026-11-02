// MainWindow integration; device input and camera math remain separate modules.
std::unique_ptr<medical_gamepad::ThreadedInput> gamepadInput;
medical_gamepad::Motion gamepadMotion;
QTimer gamepadTimer;QElapsedTimer gamepadClock;
QCheckBox*gamepadEnable=nullptr;QLabel*gamepadStatus=nullptr;QDoubleSpinBox*gamepadTurnSpeed=nullptr;
bool gamepadAllowed()const{
 return gamepadInput&&gamepadInput->connected()&&gamepadEnable&&gamepadEnable->isChecked()&&
  tabs->currentIndex()==2&&isActiveWindow()&&!QApplication::activeModalWidget()&&!processing()&&!closing&&!finishingTest&&scope->cameraCount()>0&&gamepadContextAllowed();
}
void gamepadSuspend(){gamepadTimer.stop();gamepadClock.invalidate();gamepadMotion.suspend();}
void gamepadLabel(){
 if(!gamepadInput||!gamepadStatus)return;
 bool owns=gamepadInput->connected()&&gamepadEnable->isChecked()&&scope->manualNavigation();
 if(navigationAlign)navigationAlign->setEnabled(!owns);
 QString text=gamepadInput->statusText();
 if(gamepadInput->connected()){
  if(!gamepadEnable->isChecked())text=u("手柄控制已关闭");
  else if(!gamepadAllowed())text=u("手柄已连接 · 仅导航空闲时响应");
  else if(!gamepadMotion.armed())text=u("请先将两个摇杆回中");
  else text=owns?u("手柄手动镜头 · 自动矫正已关闭"):u("手柄就绪 · 左杆移动，右杆转向");
 }
 if(gamepadStatus->text()!=text)gamepadStatus->setText(text);
}
void gamepadRefresh(){
 if(!gamepadInput)return;
 gamepadMotion.update(gamepadInput->current(),gamepadAllowed());gamepadLabel();
 if(!gamepadMotion.moving()){gamepadTimer.stop();gamepadClock.invalidate();return;}
 if(!gamepadTimer.isActive()){gamepadClock.restart();gamepadTimer.start(16);}
}
void gamepadTick(){
 if(!gamepadAllowed()){gamepadSuspend();gamepadLabel();return;}
 gamepadMotion.update(gamepadInput->current(),true);
 if(!gamepadMotion.moving()||!gamepadClock.isValid()){gamepadTimer.stop();return;}
 auto delta=gamepadMotion.step(gamepadClock.nsecsElapsed()/1e9,navigationSpeed->value(),gamepadTurnSpeed->value());gamepadClock.restart();
 if(!scope->manualNavigation()){navigationPause();scope->setManualNavigation(true);gamepadLabel();}
 scope->manualMotion(delta.millimeters,delta.yaw,delta.pitch);
}
void installGamepadControls(QVBoxLayout*layout){
 gamepadEnable=new QCheckBox(u("手柄控制"));gamepadEnable->setObjectName("gamepadControl");gamepadEnable->setChecked(true);layout->addWidget(gamepadEnable);
 auto*row=new QHBoxLayout;row->addWidget(caption(u("手柄转向速度")));gamepadTurnSpeed=new QDoubleSpinBox;gamepadTurnSpeed->setRange(5,120);gamepadTurnSpeed->setValue(45);gamepadTurnSpeed->setSuffix(u(" °/s"));row->addWidget(gamepadTurnSpeed);layout->addLayout(row);
 gamepadStatus=new QLabel(u("手柄未连接"));gamepadStatus->setWordWrap(true);gamepadStatus->setProperty("role","muted");layout->addWidget(gamepadStatus);
 auto*hint=new QLabel(u("左杆上下：前进 / 后退\n右杆：镜头左右 / 上下\n松杆停止，保持当前视角；不自动回正"));hint->setWordWrap(true);hint->setProperty("role","muted");layout->addWidget(hint);
 connect(gamepadEnable,&QCheckBox::toggled,this,[this]{gamepadSuspend();gamepadRefresh();});
}
void setupGamepad(){
 if(qEnvironmentVariableIntValue("KV260_UI_CONTROL_CHECK")==1)return;
 try{
  auto config=medical_gamepad::Config::load(root+"/modules/gamepad/config.json");gamepadTurnSpeed->setValue(config.turnDegreesPerSecond);
  gamepadInput=std::make_unique<medical_gamepad::ThreadedInput>(config,this);
  gamepadInput->onFrame=[this](medical_gamepad::Axes){gamepadRefresh();};
  gamepadInput->onLost=[this]{gamepadSuspend();gamepadLabel();};gamepadInput->onStatus=[this](QString){gamepadLabel();};
  gamepadTimer.setTimerType(Qt::PreciseTimer);connect(&gamepadTimer,&QTimer::timeout,this,[this]{gamepadTick();});
  gamepadInput->start();
 }catch(const std::exception&e){gamepadStatus->setText(u("手柄配置或输入异常：")+QString::fromUtf8(e.what()));gamepadEnable->setChecked(false);gamepadEnable->setEnabled(false);}
}
