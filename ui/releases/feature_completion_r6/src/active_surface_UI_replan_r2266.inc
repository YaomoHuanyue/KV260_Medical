 bool activeSurfaceJob=false;QString activeSurfaceAction;
 bool replanUnavailable=false,replanRouteWasVisible=false;QJsonObject replanBlockedEvent;
 QString blockedNavigationNotice()const{return u("当前入口不满足通行约束，未生成任何导航路径。\n模型和上次成功结果已保留；检查器械参数及分割模型后，可重新规划。");}
 QJsonObject replanSavedOverview,replanSavedStructures[3];
 void saveReplanOverview(){replanSavedOverview=overview->overviewCamera();for(int i=0;i<3;++i)replanSavedStructures[i]=structureCameras[i];}
 void restoreReplanOverview(){if(!overview->restoreOverviewCamera(replanSavedOverview))throw std::runtime_error("Replanning could not restore overview camera");for(int i=0;i<3;++i)structureCameras[i]=replanSavedStructures[i];}
 bool activeSurfaceTesting=qEnvironmentVariableIntValue("KV260_ACTIVE_SURFACE_UI_TEST")==1;
 void startSurfaceAction(QString action,int group=-1,int candidate=-1){
  qInfo()<<"R14b start surface action"<<action<<"processing"<<processing()<<"graphics"<<graphicsTransition;
  if(processing()||(action!="quality"&&!(!scene.value("complete_surface").toObject().isEmpty())))return;
  if((plScope&&plScope->active())||(plComposite&&plComposite->active())){
   releaseGraphics([this,action,group,candidate]{startSurfaceAction(action,group,candidate);});return;
  }
  if(action=="airway-detail")saveRecoveryView();
  if(action=="replan")saveReplanOverview();
  play.stop();playing=false;playButton->setText(u("沿路径播放"));scope->setPlayback(false);
  if(action=="selected-path"){
   auto options=scene["complete_surface"].toObject()["comparison"].toObject()["options"].toObject();
   if(options.isEmpty()||options["lesion"].toInt(-1)!=lesion->value()||
      std::abs(options["margin"].toDouble()-margin->value())>.001||
      std::abs(options["minimum_bend"].toDouble()-minimumBend->value())>.001){
    message(u("目标或约束已改变，请先按当前表面重新比较。"));return;
   }
   selectedGroup=group;selectedCandidate=candidate;selectedTaskPending=true;
  }else selectedTaskPending=false;
  activeSurfaceJob=true;activeSurfaceAction=action;replanBlockedEvent={};runOutput.clear();pendingResult.clear();failed=false;
  errors.clear();jobPending.clear();stopFile.clear();taskClock.restart();
  QStringList args={root+"/modules/navigation_replan/backend_r2265.py",action,"--active-scene",scenePath,
   "--input",input,"--result",source,"--lesion",QString::number(lesion->value()),"--diameter",QString::number(diameter->value()),
   "--margin",QString::number(margin->value()),"--minimum-bend",QString::number(minimumBend->value())};
  if(action=="quality")args<<"--source"<<(surfaceQuality->currentIndex()<2?"accepted_binary":"network_probability")<<"--quality"<<(surfaceQuality->currentIndex()%2?"ultra":"high");
  if(action=="selected-path")args<<"--group"<<QString::number(group)<<"--candidate"<<QString::number(candidate);
  jobProcess.start(root+"/.venv/bin/python",args);busy(true);stopButton->setEnabled(false);progress->setRange(0,0);
  message(action=="replan"?u("正在按当前管壁和器械约束重新规划导航"):action=="airway-detail"?u("正在审核当前目标的细支气管；模型和导航保持原样"):action=="quality"?u("正在重新生成 PL 气道表面并同步导航"):action=="comparison"?u("正在比较当前表面的器械与接近路径"):u("正在审核所选曲线并同步相机和分岔标记"));
  record("active_surface_"+action+"_started");
 }
 void surfaceJobFinished(int rc){
  activeSurfaceJob=false;stopButton->setEnabled(false);
  if(!rc&&!failed&&activeSurfaceAction=="replan"&&!replanBlockedEvent.isEmpty()){
   if(!replanUnavailable)replanRouteWasVisible=routeCheck->isChecked();replanUnavailable=true;
   play.stop();playing=false;scope->setPlayback(false);scope->clearPlFrame();miniOverview->setReferenceCamera({});
   routeCheck->setChecked(false);scope->hide();scopeUnavailable->setText(blockedNavigationNotice());scopeUnavailable->show();
   playButton->setEnabled(false);cameraSlider->setEnabled(false);progress->setRange(0,100);progress->setValue(100);
   routeInfo->setText(blockedNavigationNotice());message(blockedNavigationNotice());record("active_surface_replan_unreachable");busy(false);
   if(replanTesting)QTimer::singleShot(300,this,[this]{replanAdvance();});return;
  }
  try{
   if(rc||failed||pendingResult.isEmpty())throw std::runtime_error((errors.isEmpty()?u("当前表面任务未完成"):errors).toStdString());
   loadScene(pendingResult);if(activeSurfaceAction=="airway-detail")restoreRecoveryView();if(activeSurfaceAction=="replan")restoreReplanOverview();record("active_surface_"+activeSurfaceAction+"_loaded");
  }catch(const std::exception&e){selectedTaskPending=false;failed=true;message(QString::fromUtf8(e.what()));progress->setRange(0,100);progress->setValue(0);}
  busy(false);if(!failed)configureScope();
  if(replanTesting)QTimer::singleShot(300,this,[this]{replanAdvance();});
  else if(activeRecoveryTesting)QTimer::singleShot(300,this,[this]{recoveryAdvance();});
  else if(qualityTesting)QTimer::singleShot(300,this,[this]{qualityTestAdvance();});
  else if(activeSurfaceTesting)QTimer::singleShot(300,this,[this]{surfaceTestAdvance();});
 }
 void restoreSurfaceComparisonControls(){
  auto complete=scene["complete_surface"].toObject();auto o=complete["comparison"].toObject()["options"].toObject();if(o.isEmpty()){auto repl=complete["explicit_replan"].toObject();if(repl["revision"]==complete["revision"])o=repl["options"].toObject();}if(o.isEmpty())return;
  {QSignalBlocker b(lesion);lesion->setValue(o["lesion"].toInt());}
  {QSignalBlocker b(diameter);diameter->setValue(o["diameter"].toDouble());}
  {QSignalBlocker b(margin);margin->setValue(o["margin"].toDouble());}
  {QSignalBlocker b(minimumBend);minimumBend->setValue(o["minimum_bend"].toDouble());}
  refreshCandidates();updateAnalysis();
 }
