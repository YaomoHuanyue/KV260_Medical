 bool activeSurfaceJob=false;QString activeSurfaceAction;
 bool activeSurfaceTesting=qEnvironmentVariableIntValue("KV260_ACTIVE_SURFACE_UI_TEST")==1;
 void startSurfaceAction(QString action,int group=-1,int candidate=-1){
  qInfo()<<"R14b start surface action"<<action<<"processing"<<processing()<<"graphics"<<graphicsTransition;
  if(processing()||(action!="quality"&&!scene.contains("complete_surface")))return;
  if((plScope&&plScope->active())||(plComposite&&plComposite->active())){
   releaseGraphics([this,action,group,candidate]{startSurfaceAction(action,group,candidate);});return;
  }
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
  activeSurfaceJob=true;activeSurfaceAction=action;runOutput.clear();pendingResult.clear();failed=false;
  errors.clear();jobPending.clear();stopFile.clear();taskClock.restart();
  QStringList args={root+"/modules/surface_route/active_backend_r16.py",action,"--active-scene",scenePath,
   "--input",input,"--result",source,"--lesion",QString::number(lesion->value()),"--diameter",QString::number(diameter->value()),
   "--margin",QString::number(margin->value()),"--minimum-bend",QString::number(minimumBend->value())};
  if(action=="quality")args<<"--source"<<(surfaceQuality->currentIndex()<2?"accepted_binary":"network_probability")<<"--quality"<<(surfaceQuality->currentIndex()%2?"ultra":"high");
  if(action=="selected-path")args<<"--group"<<QString::number(group)<<"--candidate"<<QString::number(candidate);
  jobProcess.start(root+"/.venv/bin/python",args);busy(true);stopButton->setEnabled(false);progress->setRange(0,0);
  message(action=="quality"?u("正在重新生成 PL 气道表面并同步导航"):action=="comparison"?u("正在比较当前表面的器械与接近路径"):u("正在审核所选曲线并同步相机和分岔标记"));
  record("active_surface_"+action+"_started");
 }
 void surfaceJobFinished(int rc){
  activeSurfaceJob=false;stopButton->setEnabled(false);
  try{
   if(rc||failed||pendingResult.isEmpty())throw std::runtime_error((errors.isEmpty()?u("当前表面任务未完成"):errors).toStdString());
   loadScene(pendingResult);record("active_surface_"+activeSurfaceAction+"_loaded");
  }catch(const std::exception&e){selectedTaskPending=false;failed=true;message(QString::fromUtf8(e.what()));progress->setRange(0,100);progress->setValue(0);}
  busy(false);if(!failed)configureScope();
  if(qualityTesting)QTimer::singleShot(300,this,[this]{qualityTestAdvance();});
  else if(activeSurfaceTesting)QTimer::singleShot(300,this,[this]{surfaceTestAdvance();});
 }
 void restoreSurfaceComparisonControls(){
  auto o=scene["complete_surface"].toObject()["comparison"].toObject()["options"].toObject();if(o.isEmpty())return;
  {QSignalBlocker b(lesion);lesion->setValue(o["lesion"].toInt());}
  {QSignalBlocker b(diameter);diameter->setValue(o["diameter"].toDouble());}
  {QSignalBlocker b(margin);margin->setValue(o["margin"].toDouble());}
  {QSignalBlocker b(minimumBend);minimumBend->setValue(o["minimum_bend"].toDouble());}
  refreshCandidates();updateAnalysis();
 }
