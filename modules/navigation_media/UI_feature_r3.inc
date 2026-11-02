 QPushButton*videoButton=nullptr;QProgressDialog*videoProgress=nullptr;
 bool videoPending=false,videoRunning=false,videoEnding=false,videoAwaiting=false,videoEncoding=false,videoCancelled=false,videoDrained=false,videoEncoderDone=false;
 std::unique_ptr<navigation_media::Timeline> videoPlan;std::unique_ptr<navigation_media::Encoder> videoEncoder;
 int videoIndex=0,videoRendered=0,videoFPS=24,videoSavedTab=2,videoSavedQuality=0;double videoSpeed=18;
 QSize videoSize{1280,720};QString videoDirectory,videoFinalDirectory,videoError;QElapsedTimer videoClock;
 QJsonArray videoTrace;QJsonObject videoSources,videoSavedCamera,videoSavedRequest,videoLastMeta;
 QImage videoLastImage;QByteArray videoDepth,videoNormal;bool videoSavedPlaying=false,videoSavedDual=false,videoCancelledAtPL=false;
 bool videoTesting=qEnvironmentVariableIntValue("KV260_MEDIA_UI_TEST")==1;int videoTestPhase=0;QJsonArray videoTestTrace;QJsonObject videoTestSnapshot;bool videoTestCancelAwaiting=false,videoSetupRejected=false;QTimer videoWatchdog;QElapsedTimer videoProgressClock;int videoStartTick=0;
 QString videoHash(QString path){QFile f(path);if(!f.open(QIODevice::ReadOnly))throw std::runtime_error("Cannot hash video source");QCryptographicHash h(QCryptographicHash::Sha256);if(!h.addData(&f))throw std::runtime_error("Cannot read video source");return QString::fromLatin1(h.result().toHex());}
 bool videoAvailable()const{return !processing()&&!source.isEmpty()&&scope->cameraCount()>1&&scope->totalDistance()>0&&QFileInfo::exists(source+"/navigation/route.json");}
 void videoRequest(){
  if(!videoAvailable())return;
  QDialog setup(this);setup.setWindowTitle(u("导出当前导航路径"));auto*layout=new QVBoxLayout(&setup);auto*form=new QFormLayout;
  QSpinBox fps;fps.setRange(1,60);fps.setValue(24);QDoubleSpinBox speed;speed.setRange(.25,100);speed.setDecimals(2);speed.setValue(18);speed.setSuffix(" mm/s");
  QComboBox size;size.addItems({"1280 × 720","640 × 360"});form->addRow(u("视频帧率"),&fps);form->addRow(u("路径速度"),&speed);form->addRow(u("保存尺寸"),&size);layout->addLayout(form);
  auto*note=new QLabel(u("沿当前完整路径逐帧保存，期间可取消。\n原生计算 640×360；视频帧率代表回放速度。"));note->setWordWrap(true);layout->addWidget(note);
  QDialogButtonBox buttons(QDialogButtonBox::Ok|QDialogButtonBox::Cancel);buttons.button(QDialogButtonBox::Ok)->setText(u("开始导出"));buttons.button(QDialogButtonBox::Cancel)->setText(u("返回"));layout->addWidget(&buttons);
  connect(&buttons,&QDialogButtonBox::accepted,&setup,&QDialog::accept);connect(&buttons,&QDialogButtonBox::rejected,&setup,&QDialog::reject);
  if(videoTesting)QTimer::singleShot(150,&setup,[&]{QTest::mouseClick(buttons.button(!videoSetupRejected?QDialogButtonBox::Cancel:QDialogButtonBox::Ok),Qt::LeftButton);});
  if(setup.exec()!=QDialog::Accepted){if(videoTesting){videoSetupRejected=true;videoTestTrace.append(QJsonObject{{"status","setup_cancelled"},{"camera_unchanged",scope->scopeViewState()==videoTestSnapshot["camera"].toObject()}});QTimer::singleShot(200,this,[this]{videoTestAdvance();});}return;}
  videoFPS=fps.value();videoSpeed=speed.value();videoSize=size.currentIndex()==0?QSize(1280,720):QSize(640,360);
  try{
   videoSavedPlaying=playing;
   videoSavedCamera=scope->scopeViewState();videoSavedRequest=scope->cameraRequest();videoSavedTab=tabs->currentIndex();videoSavedQuality=scopeQuality->currentIndex();videoSavedDual=dualCheck->isChecked();
   videoPlan=std::make_unique<navigation_media::Timeline>(scope->totalDistance(),videoFPS,videoSpeed);
   videoSources={};for(QString path:{scenePath,source+"/navigation/route.json",source+"/segmentation/airway_mask.nii.gz",root+"/dfx/surface/release/manifest.json"})videoSources[path]=videoHash(path);
   QString id=QDateTime::currentDateTimeUtc().toString("yyyyMMdd_HHmmss_zzz")+"_"+QUuid::createUuid().toString(QUuid::Id128).left(8);
   videoFinalDirectory=root+"/ui/exports/navigation_media/"+id;videoDirectory=videoFinalDirectory+".pending";
   if(QFileInfo::exists(videoDirectory)||!QDir().mkpath(videoDirectory))throw std::runtime_error("Cannot create video destination");
   navigationPause();videoPending=true;videoRunning=videoEnding=videoAwaiting=videoEncoding=videoCancelled=videoDrained=videoEncoderDone=false;
   videoCancelledAtPL=false;videoIndex=videoRendered=0;videoTrace={};videoLastMeta={};videoError.clear();videoClock.start();videoProgressClock.start();videoStartTick=ticks;
   videoWatchdog.setInterval(1000);disconnect(&videoWatchdog,nullptr,this,nullptr);connect(&videoWatchdog,&QTimer::timeout,this,[this]{if(!videoEnding&&videoProgressClock.elapsed()>60000)videoEnd(u("当前导出步骤等待超过 60 秒，正在安全恢复"));});videoWatchdog.start();
   videoProgress=new QProgressDialog(u("正在准备导航视频"),u("取消导出"),0,videoPlan->total(),this);videoProgress->setWindowTitle(u("保存导航视频"));videoProgress->setWindowModality(Qt::WindowModal);videoProgress->setAutoClose(false);videoProgress->setAutoReset(false);videoProgress->setMinimumDuration(0);videoProgress->show();
   connect(videoProgress,&QProgressDialog::canceled,this,[this]{videoCancel();});
   releaseGraphics([this]{videoBegin();});
  }catch(const std::exception&e){message(QString::fromUtf8(e.what()));if(videoTesting)videoTestFinish(false,QString::fromUtf8(e.what()));}
 }
 void videoBegin(){
  if(videoCancelled){videoPending=false;videoEncoderDone=true;videoEnd();return;}
  videoPending=false;videoRunning=true;busy(true);scope->setEnabled(false);tabs->setCurrentIndex(2);scope->setAutoAlign(false);scope->resetView();scope->setDistance(0);
  videoEncoder=std::make_unique<navigation_media::Encoder>(this,videoDirectory+"/navigation.mp4",videoSize,videoFPS,
   [this](QString error){if(!error.isEmpty()){videoEncoderDone=true;videoEnd(error);return;}if(!videoEnding)videoSend(true);},
   [this](QString){videoProgressClock.restart();videoEncoding=false;++videoIndex;videoProgress->setValue(videoIndex);videoProgress->setLabelText(QString(u("已保存 %1 / %2 帧")).arg(videoIndex).arg(videoPlan->total()));
    if(videoTesting&&videoTestPhase==2&&videoIndex==3){videoSend(false);QTimer::singleShot(20,this,[this]{videoTestCancelAwaiting=videoAwaiting;auto*b=videoProgress->findChild<QPushButton*>();if(b)QTest::mouseClick(b,Qt::LeftButton);else videoEnd(u("缺少取消按钮"));});return;}
    if(!videoEnding)videoSend(false);},
   [this](QString error){videoEncoderDone=true;if(!error.isEmpty())videoEnd(error);videoComplete();},
   videoTesting&&videoTestPhase==3?"/nonexistent/kv260_codec_failure_test":"/usr/bin/ffmpeg");
 }
 void videoSend(bool first){
  try{if(videoEnding)return;if(videoCancelled){videoEnd();return;}if(videoIndex>=videoPlan->total()){videoEnd();return;}
  if(videoIndex>=videoPlan->moving){auto m=videoTrace.last().toObject();m["frame_index"]=videoIndex;m["hold"]=true;videoTrace.append(m);videoEncoding=true;videoEncoder->submit(videoLastImage);return;}
  scope->setDistance(videoPlan->arc(videoIndex));auto request=scope->cameraRequest();request["width"]=640;request["height"]=360;request["interactive"]=false;videoAwaiting=true;
  if(first)plScope->start(source,request);else plScope->request(request);videoProgressClock.restart();
  }catch(const std::exception&e){videoEnd(QString::fromUtf8(e.what()));}
 }
 void videoFrameReceived(const QImage&depth,const QImage&normal,QJsonObject meta){
  if(!videoRunning||videoEnding)return;
  if(!videoAwaiting||depth.size()!=QSize(640,360)||normal.size()!=depth.size()||meta["normal_computation"]!="PL"){videoEnd(u("导航视频收到未配对的 PL 帧"));return;}
  videoProgressClock.restart();videoLastMeta=meta;videoDepth=navigation_media::rgbaBytes(depth);videoNormal=navigation_media::rgbaBytes(normal);
 }
 void videoPresented(){
  if(!videoRunning||videoEnding||!videoAwaiting||videoLastMeta.isEmpty())return;
  auto shown=scope->presentedScopeFrame();if(shown["sequence"]!=videoLastMeta["sequence"])return;
  if(shown["pose_source"]!="completed_PL_frame"||std::abs(shown["arc_mm"].toDouble()-videoPlan->arc(videoIndex))>.001){videoEnd(u("视频镜头与完成帧不一致"));return;}
  videoAwaiting=false;QTimer::singleShot(0,this,[this,shown]{
   if(videoEnding)return;
   try{
    auto native=scope->completedScopeColor();auto after=scope->presentedScopeFrame();if(after["sequence"]!=shown["sequence"])throw std::runtime_error("Video capture crossed a completed frame");
    auto hud=scene["navigation"].toObject()["hud"].toObject()["samples"].toArray();int at=scope->cameraForDistance(scope->distance());
    videoLastImage=navigation_media::videoFrame(native,videoSize,shown,at<hud.size()?hud[at].toObject():QJsonObject{},videoPlan->length);
    QJsonObject meta=shown;QMap<QString,QByteArray> extra;QString png;
    QString stem=QString("reference_%1").arg(videoIndex,6,10,QChar('0'));
    if(videoIndex==0||videoIndex==videoPlan->moving/2||videoIndex==videoPlan->moving-1){
     meta["depth_reference"]=stem+".depth.rgba";meta["normal_reference"]=stem+".normal.rgba";extra[meta["depth_reference"].toString()]=videoDepth;extra[meta["normal_reference"].toString()]=videoNormal;png=stem+".png";
    }
    auto hash=[](QByteArray b){return QString::fromLatin1(QCryptographicHash::hash(b,QCryptographicHash::Sha256).toHex());};
    QJsonObject row{{"frame_index",videoIndex},{"arc_mm",videoPlan->arc(videoIndex)},{"hold",false},{"completed_frame",meta},
      {"captured_pixel_sha256",medical_capture::pixelHash(videoLastImage)},{"raw_depth_outline_sha256",hash(videoDepth)},{"raw_normal_sha256",hash(videoNormal)},
      {"native_color_sha256",medical_capture::pixelHash(native)},{"source_capture_size",QJsonArray{640,360}},{"fitted_capture_size",QJsonArray{videoSize.width(),videoSize.height()}}};
    if(!png.isEmpty())row["reference_png"]=png;videoTrace.append(row);++videoRendered;videoEncoding=true;
    videoEncoder->submit(videoLastImage,extra,png);
   }catch(const std::exception&e){videoEnd(QString::fromUtf8(e.what()));}
  });
 }
 void videoCancel(){
  if(!videoPending&&!videoRunning)return;videoCancelledAtPL=videoAwaiting;videoCancelled=true;
  if(videoPending){if(videoProgress)videoProgress->setLabelText(u("等待当前显示帧结束后取消"));return;}videoEnd();
 }
 void videoEnd(QString error={}){
  if(!error.isEmpty()&&videoError.isEmpty())videoError=error;if(videoEnding)return;videoEnding=true;
  if(videoProgress){videoProgress->setCancelButton(nullptr);videoProgress->setLabelText(u("正在完成文件并恢复导航"));}
  if(videoEncoder)videoEncoder->finish();else videoEncoderDone=true;
  plScope->stop([this]{videoDrained=true;videoComplete();});videoComplete();
 }
 void videoComplete(){
  if(!videoEnding||!videoDrained||!videoEncoderDone)return;
  videoWatchdog.stop();bool ok=videoError.isEmpty()&&!videoCancelled&&videoIndex==videoPlan->total();
  QJsonObject report{{"schema","kv260.navigation_media.v1"},{"status",ok?"completed":videoCancelled?"cancelled":"failed"},{"error",videoError},
   {"scene",scenePath},{"source_result",source},{"input_sha256",scene["input_sha256"]},{"source_sha256",videoSources},
   {"fps",videoFPS},{"speed_mm_per_s",videoSpeed},{"route_length_mm",videoPlan->length},{"expected_route_frames",videoPlan->moving},
   {"expected_hold_frames",videoPlan->hold},{"expected_total_frames",videoPlan->total()},{"encoded_frames",videoIndex},{"completed_PL_frames",videoRendered},
   {"output_size",QJsonArray{videoSize.width(),videoSize.height()}},{"native_PL_size",QJsonArray{640,360}},{"frame_trace",videoTrace},
   {"capture_fit_policy","native_C6_color_FBO_aspect_preserved"},{"wall_seconds",videoClock.elapsed()/1000.},{"Qt_peak_RSS_MiB",peakRSS()},
   {"native_GUI_button",true},{"UI_ticks_during_export",ticks-videoStartTick},{"codec", "libx264"},{"encoder_threads",2},{"one_PL_frame_in_flight",true},{"maximum_encoder_owned_images",1},{"real_time_frame_dropping",false},
   {"PL_cooperative_stop",true},{"additional_PL_resources",0},{"new_bitstream",false},{"saved_view_state",videoSavedCamera},
   {"cancel_requested_while_awaiting_PL",videoCancelledAtPL},{"file_writes_on_encoder_thread",true},
   {"PS",QJsonArray{"timeline","camera","GPU shading/HUD","bounded pipe","H264 encoding"}},
   {"PL",QJsonArray{"C6 wall intersection","target visibility","outline","depth-aware normals"}}};
  try{
   for(auto it=videoSources.begin();it!=videoSources.end();++it)if(videoHash(it.key())!=it.value().toString())throw std::runtime_error("Source changed during video export");
   if(QFileInfo::exists(videoDirectory+"/navigation.mp4"))report["movie_sha256"]=videoHash(videoDirectory+"/navigation.mp4");
   writeJson(videoDirectory+"/report.json",report);
   if(ok){QDir parent=QFileInfo(videoDirectory).dir();if(!parent.rename(QFileInfo(videoDirectory).fileName(),QFileInfo(videoFinalDirectory).fileName()))throw std::runtime_error("Cannot commit video directory");}
  }catch(const std::exception&e){ok=false;videoError=QString::fromUtf8(e.what());report["status"]="failed";report["error"]=videoError;try{writeJson(videoDirectory+"/report.json",report);}catch(...){}}
  videoEncoder.reset();videoPending=videoRunning=videoAwaiting=videoEncoding=false;videoEnding=false;
  if(videoProgress){videoProgress->hide();videoProgress->deleteLater();videoProgress=nullptr;}
  bool restored=scope->restoreScopeViewState(videoSavedCamera);scope->setEnabled(true);scopeQuality->setCurrentIndex(videoSavedQuality);dualCheck->setChecked(videoSavedDual);tabs->setCurrentIndex(videoSavedTab);
  {QSignalBlocker block(cameraSlider);cameraSlider->setValue(scope->cameraForDistance(scope->distance()));}
  busy(false);configureScope();if(videoSavedPlaying&&videoSavedTab==2)navigationToggle();
  message(ok?u("导航视频已保存：")+videoFinalDirectory:videoCancelled?u("已取消导出，导航视角已恢复"):u("视频导出失败：")+videoError);
  if(videoTesting){videoTestTrace.append(QJsonObject{{"status",report["status"]},{"directory",ok?videoFinalDirectory:videoDirectory},
    {"restored",restored},{"restored_camera",scope->scopeViewState()},{"restored_quality",scopeQuality->currentIndex()},{"restored_dual",dualCheck->isChecked()},{"UI_ticks",ticks},{"error",videoError},
    {"cancel_requested_while_awaiting_PL",videoCancelledAtPL}});if(!restored||(!ok&&!videoCancelled&&!(videoTestPhase==3&&report["status"]=="failed"&&videoError.contains("Cannot start FFmpeg")))){videoTestFinish(false,videoError);return;}++videoTestPhase;QTimer::singleShot(300,this,[this]{videoTestAdvance();});}
 }
 void videoTestFinish(bool passed,QString error={}){
  QDir().mkpath(evidence);writeJson(evidence+"/navigation_media_UI.json",{{"status",passed?"passed_actual_GUI_full_route_video_setup_cancel_PL_cancel_codec_failure_camera_restore":"failed"},
    {"error",error},{"exports",videoTestTrace},{"before",videoTestSnapshot},{"after_camera",scope->scopeViewState()},{"presented",scope->presentedScopeFrame()},
    {"peak_UI_RSS_MiB",peakRSS()},{"PL_bitstream_changed",false},{"physical_mouse_verified",false}});
  close();if(!passed)QTimer::singleShot(100,[]{QApplication::exit(1);});
 }
 void videoTestAdvance(){
  if(!videoTesting||videoPending||videoRunning||processing())return;
  if(failed||source.isEmpty()||scope->cameraCount()<2){videoTestFinish(false,u("当前病例未提供导航路径"));return;}
  if(videoTestPhase==0){
   tabs->setCurrentIndex(2);scopeQuality->setCurrentIndex(1);dualCheck->setChecked(true);scope->setAutoAlign(false);scope->setDistance(scope->totalDistance()*.37);
   testDrag(scope,QPoint(100,120),QPoint(160,150));videoTestPhase=1;QTimer::singleShot(1000,this,[this]{videoTestAdvance();});return;
  }
  auto shown=scope->presentedScopeFrame(),request=scope->cameraRequest();
  if(shown.isEmpty()||std::abs(shown["arc_mm"].toDouble()-scope->distance())>.001||shown["requested_camera"].toObject()["manual_yaw_degrees"]!=request["manual_yaw_degrees"]){QTimer::singleShot(200,this,[this]{videoTestAdvance();});return;}
  if(videoTestPhase==1){videoTestSnapshot={{"camera",scope->scopeViewState()},{"request",request},{"playing",playing},{"quality",scopeQuality->currentIndex()},{"dual",dualCheck->isChecked()}};QTest::mouseClick(videoButton,Qt::LeftButton);return;}
  if(scope->scopeViewState()!=videoTestSnapshot["camera"].toObject()||scopeQuality->currentIndex()!=1||!dualCheck->isChecked()){videoTestFinish(false,u("导出未恢复原导航视角或画质"));return;}
  if(videoTestPhase==2){QTest::mouseClick(videoButton,Qt::LeftButton);return;}
  if(videoTestPhase==3){if(!videoTestCancelAwaiting){videoTestFinish(false,u("未覆盖等待 PL 时的取消"));return;}QTest::mouseClick(videoButton,Qt::LeftButton);return;}
  if(videoTestPhase==4)videoTestFinish(true);
 }
