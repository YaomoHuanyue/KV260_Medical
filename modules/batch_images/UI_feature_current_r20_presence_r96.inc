 QPushButton*batchButton=nullptr;QProgressDialog*batchProgress=nullptr;QProcess batchProcess;
 bool batchRunning=false,batchEnding=false,batchAwaiting=false,batchCancelled=false,batchDraining=false;std::thread batchThread;
 QJsonObject batchActiveBinding;
 QJsonObject batchSources;QByteArray batchDepth,batchNormal;QTimer batchWatchdog;QElapsedTimer batchProgressClock;
 QString batchDirectory,batchFinal,batchError;QStringList batchNames;QJsonArray batchViews;QJsonObject batchFrame,batchSavedScope,batchSavedOverview;
 int batchAt=0,batchSavedTab=0,batchTick=0;bool batchSavedPlaying=false;QElapsedTimer batchClock;
 bool batchTesting=qEnvironmentVariableIntValue("KV260_BATCH_UI_TEST")==1;
 bool batchHasNavigation=false,batchSavedExact=false,batchTestCancelClicked=false,batchTestCancelAwaiting=false,batchTestCancelC8=false;
 QString batchTestKind=qEnvironmentVariable("KV260_BATCH_UI_KIND"),batchHelperStage;QByteArray batchStdout;
 qint64 batchCancelAt=-1;
 void batchTestCancel(){
  if(!batchRunning||!batchProgress||batchTestCancelClicked)return;
  batchTestCancelClicked=true;batchTestCancelAwaiting=batchAwaiting;
  batchTestCancelC8=batchProcess.state()==QProcess::Running&&QFileInfo::exists(batchDirectory+"/C8_active.json");batchCancelAt=batchClock.elapsed();
  auto*cancel=batchProgress->findChild<QPushButton*>();if(!cancel)throw std::runtime_error("No actual batch cancel button");QTest::mouseClick(cancel,Qt::LeftButton);
 }
 void batchTestAdvance(){
  if(failed){QApplication::exit(1);return;}
  if(batchTestKind=="no_route"&&!(!scene.value("complete_surface").toObject().isEmpty())){
   releaseGraphics([this]{
    auto oldRoot=QFileInfo(scenePath).dir();auto copy=scene;QString folder=root+"/ui/cache/batch_no_route_r3_"+QString::number(QCoreApplication::applicationPid());
    if(QDir(folder).exists()||!QDir().mkpath(folder+"/result"))throw std::runtime_error("Cannot make isolated no-route fixture");
    for(auto key:{"volume","masks"})copy[key]=oldRoot.filePath(copy[key].toString());
    auto meshes=copy["meshes"].toObject();for(auto it=meshes.begin();it!=meshes.end();++it){auto m=it.value().toObject();m["file"]=oldRoot.filePath(m["file"].toString());auto a=m["attributes"].toObject();if(!a.isEmpty()){a["file"]=oldRoot.filePath(a["file"].toString());m["attributes"]=a;}it.value()=m;}
    copy["meshes"]=meshes;copy["navigation"]=QJsonObject{};copy["result"]=folder+"/result";copy["results"]=QJsonArray{};copy["batch_routeless_fixture"]=true;
    writeJson(folder+"/scene.json",copy);loadScene(folder+"/scene.json");busy(false);
    if(scope->cameraCount()!=0||QFileInfo::exists(source+"/navigation/route.json"))throw std::runtime_error("No-route fixture still has a route");
    QTest::mouseClick(batchButton,Qt::LeftButton);
   });return;
  }
  QTest::mouseClick(batchButton,Qt::LeftButton);
 }
 void batchRequest(){
  if(processing()||source.isEmpty()||scene["meshes"].toObject().isEmpty())return;
  batchSavedScope=scope->scopeViewState();batchSavedOverview=overview->overviewCamera();batchSavedTab=tabs->currentIndex();batchSavedPlaying=playing;
  batchHasNavigation=(!scene.value("complete_surface").toObject().isEmpty())?(scope->cameraCount()>1&&scope->totalDistance()>0&&QFileInfo::exists(scene["complete_surface"].toObject()["bundle"].toString()+"/route.json")):(scope->cameraCount()>0&&QFileInfo::exists(source+"/navigation/route.json"));batchActiveBinding={};batchSavedExact=overview->compositeMode();batchStdout.clear();batchHelperStage.clear();batchTestCancelClicked=batchTestCancelAwaiting=batchTestCancelC8=false;batchCancelAt=-1;
  batchDepth.clear();batchNormal.clear();navigationPause();batchRunning=true;batchEnding=batchAwaiting=batchCancelled=batchDraining=false;batchError.clear();batchFrame={};batchViews={};batchAt=0;batchTick=ticks;batchClock.start();
  overview->setEnabled(false);scope->setEnabled(false);busy(true);
  QString id=QDateTime::currentDateTimeUtc().toString("yyyyMMdd_HHmmss_zzz")+"_"+QUuid::createUuid().toString(QUuid::Id128).left(8);
  batchFinal=root+"/ui/exports/batch_images/"+id;batchDirectory=batchFinal+".pending";
  if(!QDir().mkpath(batchDirectory)){batchFinish(u("无法创建批量导出目录"));return;}
  batchProgress=new QProgressDialog(u("正在准备批量图片"),u("取消导出"),0,16,this);batchProgress->setWindowModality(Qt::WindowModal);
  batchProgress->setAutoClose(false);batchProgress->setAutoReset(false);batchProgress->setMinimumDuration(0);batchProgress->show();
  batchProgressClock.start();batchWatchdog.setInterval(1000);disconnect(&batchWatchdog,nullptr,this,nullptr);
  connect(&batchWatchdog,&QTimer::timeout,this,[this]{if(batchAwaiting&&batchProgressClock.elapsed()>60000){batchCancelled=true;writeJson(batchDirectory+"/cancel",{});plScope->stop([this]{batchFinish(u("等待 PL 完成帧超过 60 秒，已安全停止"));});}});batchWatchdog.start();
  connect(batchProgress,&QProgressDialog::canceled,this,[this]{batchCancelled=true;writeJson(batchDirectory+"/cancel",{});if(batchAwaiting){batchAwaiting=false;plScope->stop([this]{batchFinish();});}});
  QStringList paths{scenePath};if(batchHasNavigation)paths<<source+"/navigation/route.json";QDir cache=QFileInfo(scenePath).dir();paths<<cache.filePath(scene["masks"].toString());
  for(auto v:scene["meshes"].toObject()){auto m=v.toObject();paths<<cache.filePath(m["file"].toString());auto a=m["attributes"].toObject();if(!a.isEmpty())paths<<cache.filePath(a["file"].toString());}
  auto savedScene=scene;QString savedScenePath=scenePath,savedRoot=root;
  batchThread=std::thread([this,paths,savedScene,savedScenePath,savedRoot]{QJsonObject hashes,binding;QString error;
   try{if((!savedScene.value("complete_surface").toObject().isEmpty()))binding=navigation_media::activeVideoBinding(savedRoot,savedScenePath,savedScene,hashes,[this](QString path){return videoHash(path);});
    else for(auto p:paths)hashes[p]=videoHash(p);}catch(const std::exception&e){error=QString::fromUtf8(e.what());}
   QMetaObject::invokeMethod(this,[this,hashes,binding,error]{batchThread.join();batchSources=hashes;batchActiveBinding=binding;if(!error.isEmpty()){batchFinish(error);return;}
    releaseGraphics([this]{if(batchCancelled){batchFinish();return;}busy(true);if(!batchHasNavigation){batchBeginViews();return;}tabs->setCurrentIndex(2);auto req=scope->cameraRequest();req["width"]=640;req["height"]=360;req["interactive"]=false;batchAwaiting=true;batchProgressClock.restart();if(!batchActiveBinding.isEmpty())plScope->startScene(batchActiveBinding["bundle"].toString(),batchActiveBinding["revision"].toString(),req);else plScope->start(source,req);if(batchTesting&&batchTestKind=="cancel_wait_frame")QTimer::singleShot(0,this,[this]{batchTestCancel();});});
   },Qt::QueuedConnection);
  });
 }
 void batchFrameReceived(const QImage&depth,const QImage&normal,const QJsonObject&meta){if(batchRunning&&batchAwaiting){if(!batchActiveBinding.isEmpty()&&!navigation_media::activeVideoFrame(batchActiveBinding,meta)){batchAwaiting=false;plScope->stop([this]{batchFinish(u("批量截图收到其他场景的帧"));});return;}batchFrame=meta;batchDepth=navigation_media::rgbaBytes(depth);batchNormal=navigation_media::rgbaBytes(normal);}}
 void batchPresented(){
  if(!batchRunning||!batchAwaiting||batchFrame.isEmpty())return;auto shown=scope->presentedScopeFrame();if(shown["sequence"]!=batchFrame["sequence"])return;
  batchAwaiting=false;QTimer::singleShot(0,this,[this,shown]{
   try{
    auto image=scope->completedScopeColor();if(image.size()!=QSize(640,360)||scope->presentedScopeFrame()["sequence"]!=shown["sequence"])throw std::runtime_error("Batch PL camera/frame mismatch");
    batchFrame=shown;batchWrite("endoscope_native.png",image,[this]{plScope->stop([this]{batchBeginViews();});});
   }catch(const std::exception&e){plScope->stop([this,e=QString::fromUtf8(e.what())]{batchFinish(e);});}
  });
 }
 void batchWrite(QString name,QImage image,std::function<void()>done){
  if(batchThread.joinable())throw std::runtime_error("Batch writer already active");
  QString path=batchDirectory+"/"+name;QByteArray rawDepth=name=="endoscope_native.png"?batchDepth:QByteArray(),rawNormal=name=="endoscope_native.png"?batchNormal:QByteArray();
  batchThread=std::thread([this,path,image,done,rawDepth,rawNormal]{QString error;
   try{if(!rawDepth.isEmpty()){
    if(rawDepth.size()!=640*360*4||rawNormal.size()!=rawDepth.size())throw std::runtime_error("Invalid complete endoscope reference planes");
    for(auto pair:{qMakePair(QString(batchActiveBinding.isEmpty()?"C6_depth_outline.rgba":"C9_depth_outline.rgba"),rawDepth),qMakePair(QString(batchActiveBinding.isEmpty()?"C6_normals.rgba":"C9_normals.rgba"),rawNormal)}){QSaveFile raw(QFileInfo(path).dir().filePath(pair.first));if(!raw.open(QIODevice::WriteOnly)||raw.write(pair.second)!=pair.second.size()||!raw.commit())throw std::runtime_error("Cannot persist C6 reference plane");}
   }QSaveFile file(path);if(!file.open(QIODevice::WriteOnly))throw std::runtime_error("Batch PNG open failed");
    QImageWriter writer(&file,"png");writer.setCompression(1);if(!writer.write(image)||!file.commit())throw std::runtime_error("Batch PNG write failed");
    if(medical_capture::pixelHash(QImage(path))!=medical_capture::pixelHash(image))throw std::runtime_error("Batch PNG differs after readback");
   }catch(const std::exception&e){error=QString::fromUtf8(e.what());}
   QMetaObject::invokeMethod(this,[this,error,done]{batchThread.join();if(!error.isEmpty())batchFinish(error);else if(batchCancelled)batchFinish();else done();},Qt::QueuedConnection);
  });
 }
 void batchBeginViews(){
  if(batchCancelled){batchFinish();return;}tabs->setCurrentIndex(1);overview->setCompositeEnabled(false);
  // Save the flag separately. UI controls remain unchanged, and configureScope
  // cannot submit while batchRunning is true.
  // batchSavedExact was captured before graphics release, including no-route cases.
  batchNames=QStringList{"lung_airway_overview","airway_detail_view","orbit_rotation_demo","xray_surface_mode","cutaway_view"};
  if(!scene["meshes"].toObject()["airway"].toObject()["attributes"].toObject().isEmpty())batchNames<<"generation_surface_mode"<<"reachability_surface_mode"<<"confidence_surface_mode";
  batchNames<<"navigation_frustum_view";if(!scene["candidates"].toArray().isEmpty())batchNames<<"lesion_focus_view";
  QTimer::singleShot(0,this,[this]{batchNextView();});
 }
 void batchNextView(){
  if(batchCancelled){batchFinish();return;}
  try{
   if(batchAt==batchNames.size()){batchPostprocess();return;}
   QJsonObject proof;QString name=batchNames[batchAt];QElapsedTimer time;time.start();auto image=overview->batchPreset(name,batchFrame,proof);proof["render_seconds"]=time.elapsed()/1000.;
   proof["RGBA_sha256"]=medical_capture::pixelHash(image);batchViews.append(proof);
   batchProgress->setLabelText(u("正在保存 ")+name);batchProgress->setValue(batchAt+1);
   batchWrite(name+".png",image,[this]{++batchAt;QTimer::singleShot(0,this,[this]{batchNextView();});});
   if(batchTesting&&batchTestKind=="cancel_view"&&batchAt==0)QTimer::singleShot(0,this,[this]{batchTestCancel();});
  }catch(const std::exception&e){batchFinish(QString::fromUtf8(e.what()));}
 }
 void batchPostprocess(){
  auto matrix=batchViews[0].toObject()["world_camera"].toObject();QStringList expected;
  for(auto name:batchNames)expected<<name+".png";
  expected<<"outline_glow_mode.png"<<"ray_step_heatmap.png"<<"fpga_feature_overview.png"<<"small_feature_overview.png";if(batchHasNavigation)expected<<"endoscope_view.png"<<"dual_view.png";
  QJsonObject request{{"active_scene_binding",batchActiveBinding},{"scene",scenePath},{"scene_sha256",batchSources[scenePath]},{"input_sha256",scene["input_sha256"]},{"input_sources",batchSources},
   {"world_camera",matrix},{"airway_mask_bit",slices[0]->airwayMaskBit()},{"attributes_available",batchNames.contains("generation_surface_mode")},
   {"candidate_available",batchNames.contains("lesion_focus_view")},{"navigation_available",batchHasNavigation},{"expected_files",QJsonArray::fromStringList(expected)},
   {"native_views",batchViews},{"completed_PL_frame",batchFrame},{"saved_scope",batchSavedScope},{"saved_overview",batchSavedOverview}};
  writeJson(batchDirectory+"/request.json",request);batchProgress->setLabelText(u("正在生成多体积步数热图，可取消后续步骤"));
  disconnect(&batchProcess,nullptr,this,nullptr);
  connect(&batchProcess,&QProcess::readyReadStandardOutput,this,[this]{batchStdout+=batchProcess.readAllStandardOutput();for(int at;(at=batchStdout.indexOf('\n'))>=0;){auto line=batchStdout.left(at);batchStdout.remove(0,at+1);log->appendPlainText(QString::fromUtf8(line));auto d=QJsonDocument::fromJson(line).object();batchHelperStage=d["stage"].toString();
    if(batchTesting&&batchTestKind=="cancel_C8"&&batchHelperStage=="C8_lung_inside")QTimer::singleShot(1000,this,[this]{batchTestCancel();});}});
  connect(&batchProcess,QOverload<int,QProcess::ExitStatus>::of(&QProcess::finished),this,[this](int code,QProcess::ExitStatus){
   QString error=QString::fromUtf8(batchProcess.readAllStandardError());batchFinish(code==0||(batchCancelled&&code==2)?QString():u("批量导出失败：")+error.right(1500));});
  connect(&batchProcess,&QProcess::errorOccurred,this,[this](QProcess::ProcessError e){if(e==QProcess::FailedToStart)batchFinish(u("无法启动图片处理进程"));});
  auto env=QProcessEnvironment::systemEnvironment();env.remove("LD_PRELOAD");env.insert("OPENBLAS_NUM_THREADS","1");env.insert("OMP_NUM_THREADS","4");
  batchProcess.setProcessEnvironment(env);batchProcess.start(root+"/.venv/bin/python",{(batchTesting&&batchTestKind=="fail_helper"?root+"/modules/batch_images/intentionally_absent_helper_r3.py":(batchActiveBinding.isEmpty()?root+"/modules/batch_images/finish_r3.py":root+"/modules/batch_images/finish_current_r20.py")),batchDirectory});
 }
 void batchFinish(QString error={}){
  if(plScope&&plScope->active()){
   if(!batchDraining){batchDraining=true;plScope->stop([this,error]{batchDraining=false;batchFinish(error);});}return;
  }
  if(batchEnding)return;batchEnding=true;batchError=error;batchWatchdog.stop();
  if(batchThread.joinable())throw std::runtime_error("Cannot finish before batch writer drains");
  overview->releaseBatchAssets();overview->setCompositeEnabled(batchSavedExact);
  bool restored=(batchHasNavigation?scope->restoreScopeViewState(batchSavedScope):scope->scopeViewState()==batchSavedScope)&&overview->overviewCamera()==batchSavedOverview;
  tabs->setCurrentIndex(batchSavedTab);batchRunning=false;batchAwaiting=false;overview->setEnabled(true);scope->setEnabled(true);busy(false);
  if(batchProgress){batchProgress->deleteLater();batchProgress=nullptr;}
  bool ok=error.isEmpty()&&!batchCancelled&&QFileInfo::exists(batchDirectory+"/report.json");
  if(ok&&!QDir().rename(batchDirectory,batchFinal)){ok=false;error=u("无法完成批量导出目录");}
  QJsonObject receipt{{"status",ok?"completed":batchCancelled?"cancelled":"failed"},{"error",error},{"directory",ok?batchFinal:batchDirectory},
   {"restored",restored},{"scope_before",batchSavedScope},{"scope_after",scope->scopeViewState()},{"overview_before",batchSavedOverview},{"overview_after",overview->overviewCamera()},
   {"UI_heartbeat_ticks",ticks-batchTick},{"wall_seconds",batchClock.elapsed()/1000.},{"Qt_peak_RSS_MiB",peakRSS()},{"native_views",batchViews},{"one_writer_image_in_flight",true},{"active_scene_binding",batchActiveBinding},{"navigation_available",batchHasNavigation},{"test_kind",batchTestKind},{"cancel_button_clicked",batchTestCancelClicked},{"cancel_requested_while_awaiting_PL",batchTestCancelAwaiting},{"cancel_requested_during_C8_API",batchTestCancelC8},{"cancel_drain_ms",batchCancelAt<0?-1:batchClock.elapsed()-batchCancelAt},{"exact_mode_restored",overview->compositeMode()==batchSavedExact}};
  writeJson((ok?batchFinal:batchDirectory)+"/UI.json",receipt);message(ok?u("批量图片已保存至 ")+batchFinal:batchCancelled?u("已取消批量导出"):error);
  if(batchTesting){QDir().mkpath(evidence);writeJson(evidence+"/batch_UI.json",receipt);closing=true;this->close();bool expected=ok;
   if(batchTestKind.startsWith("cancel_"))expected=batchCancelled&&error.isEmpty()&&!ok&&batchTestCancelClicked;
   if(batchTestKind=="cancel_wait_frame")expected=expected&&batchTestCancelAwaiting;
   if(batchTestKind=="cancel_C8")expected=expected&&batchTestCancelC8;
   if(batchTestKind=="fail_helper")expected=!ok&&!batchCancelled&&!error.isEmpty();
   if(!expected||!restored||overview->compositeMode()!=batchSavedExact)QTimer::singleShot(100,[]{QApplication::exit(1);});}
  else{configureScope();if(batchSavedPlaying&&ok&&restored&&batchSavedTab==2){playing=true;play.start();scope->setPlayback(true);}}
 }
