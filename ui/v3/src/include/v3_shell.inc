// 界面 V3 外框（在 MainWindow 类体内包含）。
// 原有控件在构造函数中照常创建并连接信号，但放进隐藏的 legacyHost，作为“状态模型”；
// 影像、三维、镜头等视图移入新的工作区；顶栏、图标栏、检查器、播放条、抽屉由 QML 绘制，经 UiBridge 读写原控件。
UiBridge *bridge=nullptr;
QQmlEngine *qmlEngine=nullptr;
QWidget *legacyHost=nullptr;
QStackedWidget *stage=nullptr;
QQuickWidget *headerQ=nullptr,*railQ=nullptr,*footerQ=nullptr,*inspectorQ=nullptr,*navPanelQ=nullptr,*transportQ=nullptr;
QQuickWidget *ctToolsQ=nullptr,*ctScrubQ=nullptr,*meshToolsQ=nullptr,*overlayQ=nullptr,*navHudQ=nullptr;
QList<QPointer<QQuickWidget>> quickPanes;
QList<QPointer<QWidget>> shellWatched;
QStringList shellErrors;
QString drawerKey;
bool shellReady=false,shellDead=false,shellLayoutQueued=false;
QVariantList pipelineStages;
QStringList pipelineSequence;
QString pipelineModule,pipelineLabel=QString::fromUtf8("尚未处理");
bool pipelineRunning=false;
qint64 pipelineStartMs=0;
int lastPublishedSecond=-1;

struct StageInfo{const char*key;const char*name;const char*shortName;QStringList pl;QStringList rms;const char*module;const char*note;};
static const QList<StageInfo>& stageTable(){
  static const QList<StageInfo> t={
   {"segmentation","CT 分割","分割",{QString::fromUtf8("PL · D6 HU"),QString::fromUtf8("PL · C5 卷积")},{"D6","C5"},"C5 卷积引擎",""},
   {"airway-cleanup","气道清理","清理",{},{},"","PS 四核 · 连通域 / 闭运算 / 填洞"},
   {"reconstruction","三维重建","重建",{QString::fromUtf8("PL · D7 移动立方体"),QString::fromUtf8("PL · D9 网格平滑")},{"D7","D9"},"D7 → D9 网格",""},
   {"navigation","路径规划","规划",{QString::fromUtf8("PL · C8 距离场"),QString::fromUtf8("PL · C4 路径")},{"C8","C4"},"C8 → C4 路径",""}};
  return t;
 }
void resetPipeline(const QString&state,const QJsonObject&record={}){
  QHash<QString,double> seconds;for(auto v:record["stages"].toArray()){auto o=v.toObject();seconds[o["stage"].toString()]=o["wall_seconds"].toDouble();}
  pipelineStages.clear();
  for(auto&s:stageTable()){QString st=state;if(!record.isEmpty())st=seconds.contains(s.key)?"done":"skip";
   pipelineStages<<QVariantMap{{"key",s.key},{"name",QString::fromUtf8(s.name)},{"short",QString::fromUtf8(s.shortName)},{"state",st},{"seconds",seconds.value(s.key,0.)},
    {"pl",s.pl},{"note",QString::fromUtf8(s.note)},{"detail",QString()}};}
 }
void setStage(const QString&key,const QString&state,double seconds=-1,const QString&detail=QString()){
  for(auto&v:pipelineStages){auto m=v.toMap();if(m["key"].toString()!=key)continue;m["state"]=state;if(seconds>=0)m["seconds"]=seconds;if(!detail.isNull())m["detail"]=detail;v=m;}
 }
void publishPipeline(){
  if(!bridge)return;QString elapsedText;
  if(pipelineRunning){qint64 s=(beatClock.elapsed()-pipelineStartMs)/1000;elapsedText=QString::fromUtf8("已用 %1:%2").arg(s/60,2,10,QChar('0')).arg(s%60,2,10,QChar('0'));}
  bridge->set("pipeline",QVariantMap{{"stages",pipelineStages},{"running",pipelineRunning},{"label",pipelineRunning?elapsedText.mid(3):pipelineLabel},{"elapsed",elapsedText},
   {"module",pipelineRunning?pipelineModule:QString()},{"sequence",pipelineSequence}});
 }
// 后台事件 → 流程状态（在 processLines 中调用）
void pipelineEvent(const QJsonObject&o){
  demoProcessEvent(o);
  QString event=o["event"].toString();
  if(event=="started"){resetPipeline("wait");pipelineRunning=true;pipelineStartMs=beatClock.elapsed();pipelineSequence.clear();pipelineModule.clear();lastPublishedSecond=-1;}
  else if(event=="stage"){QString key=o["stage"].toString();
   for(auto&v:pipelineStages){auto m=v.toMap();if(m["state"]=="run"){m["state"]="done";v=m;}}
   setStage(key,"run");for(auto&s:stageTable())if(key==s.key){pipelineModule=QString::fromUtf8(s.module);for(auto&r:s.rms)pipelineSequence<<r;}}
  else if(event=="stage_done")setStage(o["stage"].toString(),"done",o["seconds"].toDouble());
  else if(event=="completed"){bool ok=o["status"]=="passed";for(auto&v:pipelineStages){auto m=v.toMap();if(m["state"]=="run"){m["state"]=ok?"done":"skip";v=m;}}
   pipelineRunning=false;pipelineModule.clear();pipelineLabel=ok?QString::fromUtf8("已完成 · %1 s").arg(o["seconds"].toDouble(),0,'f',0):QString::fromUtf8("已停止");}
  else if(event=="error"){for(auto&v:pipelineStages){auto m=v.toMap();if(m["state"]=="run"){m["state"]="fail";v=m;}}pipelineRunning=false;pipelineModule.clear();pipelineLabel=QString::fromUtf8("失败");}
  else return;
  publishPipeline();
 }
// 载入已完成结果时，按结果目录的 pipeline.json 显示各阶段实际耗时
void pipelineFromResult(){
  if(pipelineRunning)return;
  auto record=source.isEmpty()?QJsonObject{}:readJsonQuiet(source+"/pipeline.json");
  // 单项重算（如重新规划）的结果只记录本次阶段；沿 source_result 追溯来源结果，补齐其余阶段的实际耗时
  if(!record.isEmpty()){QJsonArray stages=record["stages"].toArray();QSet<QString> have;for(auto v:stages)have<<v.toObject()["stage"].toString();
   QString from=record["source_result"].toString();
   for(int depth=0;depth<4&&!from.isEmpty();++depth){auto up=readJsonQuiet(from+"/pipeline.json");if(up.isEmpty())break;
    for(auto v:up["stages"].toArray()){auto o=v.toObject();if(!have.contains(o["stage"].toString())){have<<o["stage"].toString();stages<<o;}}
    from=up["source_result"].toString();}
   record["stages"]=stages;}
  if(record.isEmpty()){resetPipeline("wait");pipelineLabel=source.isEmpty()?QString::fromUtf8("尚未处理"):QString::fromUtf8("已载入结果");}
  else{resetPipeline("done",record);bool all=true;for(auto&v:pipelineStages)all=all&&v.toMap()["state"]=="done";pipelineLabel=all?QString::fromUtf8("已完成"):QString::fromUtf8("已载入结果");}
  publishPipeline();
 }
static QJsonObject readJsonQuiet(const QString&path){QFile f(path);if(!f.open(QIODevice::ReadOnly)||f.size()>4*1024*1024)return {};auto d=QJsonDocument::fromJson(f.readAll());return d.isObject()?d.object():QJsonObject{};}

QQuickWidget*pane(const QString&file,bool overlay=false){
  auto*q=new QQuickWidget(qmlEngine,this);q->setObjectName("v3_"+QFileInfo(file).baseName());
  q->setResizeMode(QQuickWidget::SizeRootObjectToView);q->setFocusPolicy(Qt::NoFocus);
  if(overlay){q->setAttribute(Qt::WA_AlwaysStackOnTop);q->setClearColor(Qt::transparent);}else q->setClearColor(QColor("#0B0D10"));
  q->setSource(QUrl("qrc:/qml/"+file));
  for(auto&e:q->errors()){shellErrors<<e.toString();qWarning()<<"QML"<<e.toString();}
  quickPanes<<q;return q;
 }
void watchGeometry(QWidget*w){if(!w)return;w->installEventFilter(this);shellWatched<<w;}
void queueOverlayLayout(){if(shellLayoutQueued||shellDead)return;shellLayoutQueued=true;QTimer::singleShot(0,this,[this]{shellLayoutQueued=false;layoutOverlays();});}
void layoutOverlays(){
  if(!shellReady||shellDead||!stage)return;int page=tabs->currentIndex();
  auto rectOf=[this](QWidget*w){return QRect(w->mapTo(this,QPoint(0,0)),w->size());};
  bool ct=page==0&&slices[0]->isVisible(),mesh=page==1&&overview->isVisible();
  if(ct){QRect a=rectOf(slices[0]);ctToolsQ->setGeometry(a.right()-12-284,a.top()+10,284,40);ctScrubQ->setGeometry(a.left()+14,a.bottom()-12-36,qMax(200,a.width()-28),36);}
  ctToolsQ->setVisible(ct);ctScrubQ->setVisible(ct);
  if(mesh){QRect o=rectOf(overview);meshToolsQ->setGeometry(o.left()+12,o.top()+12,264,40);}
  meshToolsQ->setVisible(mesh);
  overlayQ->setGeometry(rectOf(stage));overlayQ->setVisible(!drawerKey.isEmpty()||overlayQ->property("closing").toBool());
  {QRect st=rectOf(stage);
   if(demoTitleShown()){int w=qMin(760,st.width()-80);demoQ->setGeometry(st.left()+(st.width()-w)/2,st.top()+(st.height()-200)/2,w,200);}
   else if(page==2&&scope->isVisible()){QRect r=rectOf(scope);int w=qMin(760,r.width()-28);demoQ->setGeometry(r.left()+(r.width()-w)/2,r.bottom()-66,w,52);}
   else{int w=qMin(760,st.width()-40);demoQ->setGeometry(st.left()+(st.width()-w)/2,st.bottom()-(page==2?150:118),w,52);}
   demoQ->setVisible(demoActive);}
  {bool nav=page==2&&scope->isVisible()&&scope->cameraCount()>1;if(nav){QRect r=rectOf(scope);navHudQ->setGeometry(r.left()+12,r.top()+40,250,118);}navHudQ->setVisible(nav);}
  for(auto*q:{ctToolsQ,ctScrubQ,meshToolsQ,navHudQ,overlayQ,demoQ})if(q->isVisible())q->raise();
 }
void setDrawer(QString key){
  gamepadSuspend();
  if(key==drawerKey)return;drawerKey=key;bridge->set("drawer",key);
  if(key.isEmpty()){overlayQ->setProperty("closing",true);QTimer::singleShot(Theme_slideMs+60,this,[this]{if(shellDead)return;overlayQ->setProperty("closing",false);if(drawerKey.isEmpty())overlayQ->hide();});}
  layoutOverlays();
 }
static constexpr int Theme_slideMs=180;
void shellAction(const QString&name,const QVariant&argument){
  if(shellDead)return;
  if(name=="page"){int i=argument.toInt();if(i>=0&&i<3)tabs->setCurrentIndex(i);}
  else if(name=="drawer")setDrawer(argument.toString());
  else if(name=="quit"){setDrawer("");close();}
  else if(name=="demo")demoStart();
  else if(name=="demoProcess")demoProcessStart();
 }
// 镜头位置变化：遥测、剩余距离
void shellNavChanged(){
  if(!bridge||shellDead)return;
  bridge->republish("camera");bridge->republish("align");
  bridge->set("hud",scope->hudCurrent().toVariantMap());
  bridge->set("remaining",qMax(0.,double(scope->totalDistance()-scope->distance())));
  // 导航关键数据（分岔级数、下一分岔、进度、到目标距离、前方最窄处、目标信息）
  auto target=scene["navigation"].toObject()["report"].toObject()["target"].toObject();auto c=target["centroid_lps_mm"].toArray();
  bool hasTarget=c.size()==3;QVector3D t=hasTarget?QVector3D(float(c[0].toDouble()),float(c[1].toDouble()),float(c[2].toDouble())):QVector3D();
  auto info=scope->navInfo(t,hasTarget);
  if(hasTarget){int idx=target["index"].toInt(-1);info["target_index"]=idx;
   for(auto v:scene["candidates"].toArray()){auto o=v.toObject();if(o["index"].toInt()==idx){info["target_volume_mm3"]=o["volume_mm3"].toDouble();break;}}}
  bridge->set("navInfo",info.toVariantMap());
 }
// PL 镜头帧：最近 2 s 的实际呈现帧率与单帧往返时间
QVector<qint64> plFrameTimes;
void shellPlFrame(double roundTripMs){
  if(!bridge||shellDead)return;qint64 now=beatClock.elapsed();plFrameTimes<<now;
  while(!plFrameTimes.isEmpty()&&now-plFrameTimes.first()>2000)plFrameTimes.removeFirst();
  double fps=plFrameTimes.size()>1?1000.*(plFrameTimes.size()-1)/qMax<qint64>(1,now-plFrameTimes.first()):0;
  bridge->set("plPerf",QVariantMap{{"fps",fps},{"ms",roundTripMs},{"at",double(now)}});
 }
// 场景载入：分岔刻度、结构状态、流程耗时
void shellSceneLoaded(){
  if(!bridge||shellDead)return;
  QVariantList marks;int last=qMax(1,scope->cameraCount()-1);
  for(double arc:scope->branchArcs()){int i=scope->cameraForDistance(arc);if(i>0&&i<last)marks<<double(i)/last;}
  bridge->set("navMarks",marks);publishStructure();shellNavChanged();pipelineFromResult();
 }
void publishStructure(){if(bridge&&!shellDead)bridge->set("structure",structureMode);}
// 心跳中调用：忙碌状态、计时
void shellTick(){
  if(!bridge||shellDead)return;
  bridge->set("busy",processing());
  {auto p=bridge->get("plPerf").toMap();if(p.value("fps").toDouble()>0&&beatClock.elapsed()-qint64(p.value("at").toDouble())>2500){p["fps"]=0.;bridge->set("plPerf",p);plFrameTimes.clear();}}
  if(pipelineRunning){int s=int((beatClock.elapsed()-pipelineStartMs)/1000);if(s!=lastPublishedSecond){lastPublishedSecond=s;
    for(auto&v:pipelineStages){auto m=v.toMap();if(m["key"]=="segmentation"&&m["state"]=="run"){m["detail"]=segmentationInfo?segmentationInfo->text():QString();v=m;}}
    publishPipeline();}}
  else if(jobProcess.state()==QProcess::NotRunning&&bridge->get("pipeline").toMap()["running"].toBool())publishPipeline();
 }
void buildShell(QPushButton*resetScopeButton,QPushButton*fitButton,QPushButton*resetViewButton,QCheckBox*maskCheck){
  bridge=new UiBridge(this);
  connect(bridge,&UiBridge::actionRequested,this,[this](const QString&n,const QVariant&a){shellAction(n,a);});
  struct B{const char*k;QAbstractButton*b;};
  for(auto&e:std::initializer_list<B>{{"run",runButton},{"stop",stopButton},{"open",openButton},{"dicom",dicomButton},{"import",importButton},{"refresh",refreshButton},
     {"rebuild",rebuildButton},{"nav",navButton},{"focus",focusButton},{"compare",compareButton},{"comparisonResults",comparisonResults},{"export",exportButton},
     {"snapshot",snapshotButton},{"video",videoButton},{"play",playButton},{"navStart",navStart},{"navBack",navBackward},{"navFwd",navForward},{"navEnd",navEnd},
     {"resetScope",resetScopeButton},{"fit",fitButton},{"resetView",resetViewButton},{"preset0",structureButtons[0]},{"preset1",structureButtons[1]},{"preset2",structureButtons[2]},
     {"theme",themeToggle},{"mask",maskCheck},{"layer0",meshLayers[0]},{"layer1",meshLayers[1]},{"layer2",meshLayers[2]},{"route",routeCheck},{"clip",clipCheck},
     {"precise",preciseBlend},{"align",navigationAlign},{"dual",dualCheck},{"exposure",exposureToggle},{"gamepad",gamepadEnable}})bridge->addButton(e.k,e.b);
  bridge->addSpin("gamepadTurn",gamepadTurnSpeed);bridge->addLabel("gamepadStatus",gamepadStatus);
  bridge->addCombo("window",windowPreset);bridge->addCombo("results",results,true);bridge->addCombo("lesion",lesionList);bridge->addCombo("color",colorMode);
  bridge->addCombo("clipAxis",clipAxis);bridge->addCombo("quality",scopeQuality);
  bridge->addSlider("axial",axialSlider);bridge->addSlider("camera",cameraSlider);bridge->addSlider("opacity",opacity);bridge->addSlider("clipOffset",clipOffset);
  bridge->addSpin("minVolume",minimumCandidateVolume);bridge->addSpin("diameter",diameter);bridge->addSpin("margin",margin);bridge->addSpin("speed",navigationSpeed);bridge->addSpin("step",navigationStep);
  struct L{const char*k;QLabel*l;};
  for(auto&e:std::initializer_list<L>{{"case",caseLabel},{"info",info},{"task",task},{"coordinate",coordinate},{"routeInfo",routeInfo},{"elapsed",elapsed},{"candidateInfo",candidateInfo},
     {"legend",legend},{"availability",structureAvailability},{"scopePerf",scopePerf},{"compositePerf",compositePerf},{"segmentationInfo",segmentationInfo},{"navPos",navigationPosition},
     {"exposureStatus",exposureStatus}})bridge->addLabel(e.k,e.l);
  bridge->addProgress("progress",progress);bridge->addText("log",log);
  // C++ 直接发布的值：先插入默认值，QML 绑定才能收到后续更新
  bridge->set("page",tabs->currentIndex());bridge->set("drawer",QString());bridge->set("busy",true);bridge->set("theme","dark");
  bridge->set("hud",QVariantMap{});bridge->set("navInfo",QVariantMap{});bridge->set("plPerf",QVariantMap{});bridge->set("navMarks",QVariantList{});bridge->set("remaining",0.);bridge->set("structure",structureMode);
  bridge->set("disclaimer",QString::fromUtf8("研究原型 · 非临床诊断"));
  bridge->set("demo",QVariantMap{{"active",false},{"step",0},{"total",demoTotal},{"text",QString()},{"title",QString()},{"subtitle",QString()},{"process",false}});
  resetPipeline("wait");publishPipeline();
  connect(themeToggle,&QPushButton::toggled,this,[this](bool light){bridge->set("theme",light?"light":"dark");});

  qmlEngine=new QQmlEngine(this);qmlEngine->rootContext()->setContextProperty("ui",bridge);

  auto*shell=new QVBoxLayout(this);shell->setContentsMargins(0,0,0,0);shell->setSpacing(0);
  headerQ=pane("Header.qml");headerQ->setFixedHeight(48);shell->addWidget(headerQ);
  auto*mid=new QHBoxLayout;mid->setContentsMargins(0,0,0,0);mid->setSpacing(0);shell->addLayout(mid,1);
  railQ=pane("Rail.qml");railQ->setFixedWidth(56);mid->addWidget(railQ);
  stage=new QStackedWidget;stage->setObjectName("v3Stage");mid->addWidget(stage,1);
  footerQ=pane("Footer.qml");footerQ->setFixedHeight(26);shell->addWidget(footerQ);

  auto*ctPage=new QWidget;ctPage->setObjectName("v3Black");auto*grid=new QGridLayout(ctPage);grid->setContentsMargins(0,0,0,0);grid->setSpacing(1);
  grid->addWidget(slices[0],0,0,2,1);grid->addWidget(slices[1],0,1);grid->addWidget(slices[2],1,1);grid->setColumnStretch(0,16);grid->setColumnStretch(1,9);grid->setRowStretch(0,1);grid->setRowStretch(1,1);
  stage->addWidget(ctPage);
  auto*meshPage=new QWidget;meshPage->setObjectName("v3Black");auto*meshRow=new QHBoxLayout(meshPage);meshRow->setContentsMargins(0,0,0,0);meshRow->setSpacing(0);
  meshRow->addWidget(overview,1);inspectorQ=pane("Inspector3D.qml");inspectorQ->setFixedWidth(264);meshRow->addWidget(inspectorQ);
  stage->addWidget(meshPage);
  auto*navPage=new QWidget;navPage->setObjectName("v3Black");auto*navRow=new QHBoxLayout(navPage);navRow->setContentsMargins(0,0,0,0);navRow->setSpacing(0);
  auto*navMain=new QVBoxLayout;navMain->setContentsMargins(0,0,0,0);navMain->setSpacing(0);navMain->addWidget(scopeUnavailable,1);navMain->addWidget(scope,1);
  transportQ=pane("Transport.qml");transportQ->setFixedHeight(64);navMain->addWidget(transportQ);navRow->addLayout(navMain,1);
  auto*navSide=new QWidget;navSide->setFixedWidth(264);auto*sideColumn=new QVBoxLayout(navSide);sideColumn->setContentsMargins(0,0,0,0);sideColumn->setSpacing(0);
  miniOverview->setMinimumWidth(0);miniOverview->setFixedHeight(214);sideColumn->addWidget(miniOverview);navPanelQ=pane("NavPanel.qml");sideColumn->addWidget(navPanelQ,1);
  navRow->addWidget(navSide);stage->addWidget(navPage);
  stage->setCurrentIndex(tabs->currentIndex());

  ctToolsQ=pane("CtTools.qml",true);ctScrubQ=pane("CtScrub.qml",true);meshToolsQ=pane("MeshTools.qml",true);
  overlayQ=pane("Overlay.qml",true);overlayQ->hide();
  demoQ=pane("DemoCaption.qml",true);demoQ->hide();
  navHudQ=pane("NavHud.qml",true);navHudQ->hide();
  auto*demoKey=new QShortcut(QKeySequence(Qt::Key_F5),this);connect(demoKey,&QShortcut::activated,this,[this]{demoStart();});
  auto*processKey=new QShortcut(QKeySequence(Qt::Key_F6),this);connect(processKey,&QShortcut::activated,this,[this]{demoProcessStart();});
  for(QWidget*w:{static_cast<QWidget*>(slices[0]),static_cast<QWidget*>(overview),static_cast<QWidget*>(scope),static_cast<QWidget*>(stage)})watchGeometry(w);

  connect(tabs,&QTabWidget::currentChanged,this,[this](int i){if(shellDead)return;stage->setCurrentIndex(i);bridge->set("page",i);queueOverlayLayout();});
  connect(cameraSlider,&QSlider::valueChanged,this,[this]{shellNavChanged();});
  for(auto*c:meshLayers)connect(c,&QCheckBox::toggled,this,[this]{publishStructure();});
  for(auto*b:structureButtons)connect(b,&QPushButton::clicked,this,[this]{publishStructure();});
  auto*escape=new QShortcut(QKeySequence(Qt::Key_Escape),this);connect(escape,&QShortcut::activated,this,[this]{if(!drawerKey.isEmpty())setDrawer("");});
  shellReady=true;queueOverlayLayout();
 }
void shellShutdown(){
  if(shellDead)return;shellDead=true;
  for(auto&w:shellWatched)if(w)w->removeEventFilter(this);
  ++demoToken;demoActive=false;if(demoFilter)qApp->removeEventFilter(demoFilter);
  if(bridge)bridge->shutdown();
  for(auto&q:quickPanes)if(q)delete q.data();
  quickPanes.clear();
  // 与 V2 相同的销毁顺序：视图先于 PL 传输对象销毁（后者析构时会运行嵌套事件循环），并先清空回调
  for(auto*v:{overview,scope,miniOverview})if(v){v->onCamera={};v->onCandidatePicked={};v->onBackend={};}
  if(scope){scope->onPoseChanged={};scope->onPlPresented={};}
  if(overview)overview->onOverviewChanged={};
  for(auto*s:slices)if(s){s->onSlice={};s->onPosition={};}
  if(plScope){plScope->onFrame={};plScope->onStatus={};}
  if(plComposite){plComposite->onFrame={};plComposite->onStatus={};}
  if(stage){delete stage;stage=nullptr;}
 }
bool shellEventFilter(QObject*object,QEvent*event){
  if(!shellReady||shellDead)return false;auto t=event->type();
  if(t==QEvent::Resize||t==QEvent::Move||t==QEvent::Show||t==QEvent::Hide)for(auto&w:shellWatched)if(w.data()==object){queueOverlayLayout();break;}
  return false;
 }

// ── 布局检查模式（KV260_LAYOUT_REVIEW=<目录>）：不启动 PL，依次截图各页面、抽屉和浅色主题后退出 ──
bool layoutReviewMode=qEnvironmentVariableIsSet("KV260_LAYOUT_REVIEW");
int reviewStep=0;bool reviewDemoShot=false;
void layoutReviewStart(){if(layoutReviewMode)QTimer::singleShot(1500,this,[this]{layoutReviewTick();});}
void layoutReviewTick(){
  if(shellDead)return;
  if(processing()||scenePath.isEmpty()){QTimer::singleShot(500,this,[this]{layoutReviewTick();});return;}
  QString dir=qEnvironmentVariable("KV260_LAYOUT_REVIEW");QDir().mkpath(dir);
  struct Step{const char*name;int page;const char*drawer;int light;int dual;};
  static const Step steps[]={{"01_ct",0,"",0,-1},{"02_mesh",1,"",0,-1},{"03_nav",2,"",0,-1},{"04_case",0,"case",0,-1},{"05_plan",1,"plan",0,-1},
   {"06_export",2,"export",0,-1},{"07_system",0,"system",0,-1},{"08_process",0,"process",0,-1},{"09_mesh_light",1,"",1,-1},{"10_ct_light",0,"",1,-1},
   {"11_nav_light_dual",2,"",1,1},{"12_nav_dark_dual",2,"",0,1}};
  const int count=int(sizeof(steps)/sizeof(steps[0]));
  if(reviewStep==count&&!reviewDemoShot){reviewDemoShot=true;themeToggle->setChecked(false);demoStart();
   QTimer::singleShot(2600,this,[this]{if(shellDead)return;grab().save(qEnvironmentVariable("KV260_LAYOUT_REVIEW")+"/13_demo.png");demoStop();layoutReviewTick();});return;}
  if(reviewStep>=count){
   QJsonArray errors;for(auto&e:shellErrors)errors<<e;
   writeJson(dir+"/layout_review.json",QJsonObject{{"steps",count},{"qml_errors",errors},{"passed",shellErrors.isEmpty()},{"pl_started",false}});
   QApplication::exit(shellErrors.isEmpty()?0:1);return;}
  auto&s=steps[reviewStep];
  themeToggle->setChecked(s.light==1);if(s.dual>=0)dualCheck->setChecked(s.dual==1);
  tabs->setCurrentIndex(s.page);setDrawer(QString::fromUtf8(s.drawer));
  QTimer::singleShot(1100,this,[this,name=QString(s.name)]{if(shellDead)return;grab().save(qEnvironmentVariable("KV260_LAYOUT_REVIEW")+"/"+name+".png");++reviewStep;layoutReviewTick();});
 }

// ── 一键演示（F5，约 2 分 55 秒）：在已载入的结果上按固定脚本调用已有功能，PL 功能均为现场运行 ──
//   片头 → 处理记录 → 影像分割 → 三维重建与 C7 透明合成 → 改目标重新规划 + 器械直径 → C6 实时导航 → 终点 → 结尾
// ── 处理演示（F6）：对当前原始 CT 现场执行完整处理，字幕随阶段更新，供单独录制 ──
// 任意按键或鼠标点击立即退出字幕脚本（F6 退出时不会中止正在进行的后台处理，可用“停止”按钮中止）。
QQuickWidget *demoQ=nullptr;
int demoToken=0;bool demoActive=false,demoProcessMode=false;double demoSpeedBackup=0,demoDiameterBackup=0;int demoOpacityBackup=-1,demoColorBackup=-1,demoLungBackup=-1,demoDualBackup=-1,demoMaskBackup=-1;
qint64 demoPlayStart=0,demoStartMs=0;
quint64 plPresentedCount=0;
static constexpr int demoTotal=6;
static constexpr qint64 demoBudgetMs=175000;   // 结尾画面最迟在 2:55 结束
QJsonArray demoMarks;
struct DemoFilter:public QObject{std::function<void()> stop;
  bool eventFilter(QObject*,QEvent*e)override{auto t=e->type();
   if(t==QEvent::MouseButtonPress||(t==QEvent::KeyPress&&static_cast<QKeyEvent*>(e)->key()!=Qt::Key_F5&&static_cast<QKeyEvent*>(e)->key()!=Qt::Key_F6))QTimer::singleShot(0,this,[this]{if(stop)stop();});
   return false;}};
DemoFilter*demoFilter=nullptr;
qint64 demoElapsed()const{return beatClock.elapsed()-demoStartMs;}
void demoMark(const QString&name){demoMarks<<QJsonObject{{"mark",name},{"ms",double(demoElapsed())}};}
void demoPublish(int step,const QString&text,const QString&title=QString(),const QString&subtitle=QString()){
  bridge->set("demo",QVariantMap{{"active",true},{"step",step},{"total",demoTotal},{"text",text},{"title",title},{"subtitle",subtitle},{"process",demoProcessMode}});queueOverlayLayout();}
void demoCaption(int step,const QString&text){demoPublish(step,text);demoMark(QString("caption_%1").arg(step));}
void demoTitle(const QString&title,const QString&subtitle){demoPublish(0,QString(),title,subtitle);demoMark("title");}
bool demoTitleShown()const{return bridge&&!bridge->get("demo").toMap()["title"].toString().isEmpty();}
void demoStop(){
  if(!demoActive)return;demoMark("stop");demoActive=false;++demoToken;
  if(demoFilter)qApp->removeEventFilter(demoFilter);
  if(!demoProcessMode){rotation.stop();if(playing)navigationPause();
   if(demoSpeedBackup>0){navigationSpeed->setValue(demoSpeedBackup);demoSpeedBackup=0;}
   if(demoDiameterBackup>0){diameter->setValue(demoDiameterBackup);demoDiameterBackup=0;}
   demoRestoreView();}
  if(demoMaskBackup>=0){bridge->setChecked("mask",demoMaskBackup==1);demoMaskBackup=-1;}
  demoProcessMode=false;setDrawer("");
  bridge->set("demo",QVariantMap{{"active",false},{"step",0},{"total",demoTotal},{"text",QString()},{"title",QString()},{"subtitle",QString()},{"process",false}});queueOverlayLayout();
  demoCaptureFinish();
 }
// 演示中临时改动的显示设置，结束或中断时恢复
void demoRestoreView(){
  if(preciseBlend->isChecked())preciseBlend->setChecked(false);
  if(demoOpacityBackup>=0){opacity->setValue(demoOpacityBackup);demoOpacityBackup=-1;}
  if(demoLungBackup>=0){meshLayers[0]->setChecked(demoLungBackup==1);demoLungBackup=-1;}
  if(demoColorBackup>=0){colorMode->setCurrentIndex(demoColorBackup);demoColorBackup=-1;}
  if(demoDualBackup>=0){dualCheck->setChecked(demoDualBackup==1);demoDualBackup=-1;}
 }
void demoAt(int token,int ms,std::function<void()> f){QTimer::singleShot(ms,this,[this,token,f]{if(shellDead||!demoActive||token!=demoToken)return;f();});}
// 条件满足（或超时）后继续；用于等待重新规划与场景载入
void demoWhen(int token,std::function<bool()> ready,int timeoutMs,std::function<void(bool)> then,qint64 started=-1){
  if(started<0)started=beatClock.elapsed();
  demoAt(token,250,[this,token,ready,timeoutMs,then,started]{bool ok=ready();if(ok||beatClock.elapsed()-started>timeoutMs){then(ok);return;}demoWhen(token,ready,timeoutMs,then,started);});
 }
void demoBegin(bool process){
  demoActive=true;demoProcessMode=process;demoStartMs=beatClock.elapsed();demoMarks=QJsonArray{};setDrawer("");
  if(!demoFilter){demoFilter=new DemoFilter;demoFilter->setParent(this);demoFilter->stop=[this]{demoStop();};}
  int token=demoToken;demoAt(token,500,[this]{qApp->installEventFilter(demoFilter);});  // 忽略触发演示的那次按键/点击
  demoCaptureBegin(token);
 }
void demoStart(){
  gamepadSuspend();
  if(demoActive){demoStop();return;}
  if(shellDead||processing()||scenePath.isEmpty())return;
  ++demoToken;int token=demoToken;demoBegin(false);
  // 1. 片头（6 s）
  tabs->setCurrentIndex(0);
  demoTitle(u("KV260 支气管导航工作站"),u("原始 CT → 分割 → 三维重建 → 路径规划 → 实时虚拟支气管镜"));
  // 2. 处理记录（14 s）：本结果目录 pipeline.json 中的实际阶段与耗时
  demoAt(token,5000,[this]{setDrawer("process");demoCaption(1,u("一键处理：HU 预处理 → 卷积分割 → 三维重建 → 距离场与路径，6 个 PL 模块按阶段动态装入"));});
  // 3. 影像（20 s）
  demoAt(token,16000,[this,token]{setDrawer("");tabs->setCurrentIndex(0);demoCaption(2,u("影像：PL INT8 卷积网络（C5）分割的肺、气道与病灶，叠加在 CT 三个切面上"));
   int lo=axialSlider->minimum(),hi=axialSlider->maximum(),start=axialSlider->value(),span=qMax(1,qMin(36,(hi-lo)/4));
   for(int i=0;i<96;++i){int phase=i<24?i:(i<72?48-i:i-96);demoAt(token,300+i*150,[this,lo,hi,start,span,phase]{axialSlider->setValue(qBound(lo,start+phase*span/24,hi));});}});
  // 4. 三维（12 s）+ C7 精确透明合成（13 s）
  demoAt(token,32000,[this]{tabs->setCurrentIndex(1);showStructure(2);rotation.start(30);demoCaption(3,u("三维：PL 移动立方体（D7）与网格平滑（D9）重建的肺、气道与病灶"));});
  // C7 只在画面静止时合成：打开肺、设一次不透明度后保持不动
  demoAt(token,41000,[this]{rotation.stop();demoLungBackup=meshLayers[0]->isChecked()?1:0;meshLayers[0]->setChecked(true);
   demoOpacityBackup=opacity->value();opacity->setValue(35);if(preciseBlend->isEnabled())preciseBlend->setChecked(true);
   demoCaption(3,u("PL 精确透明合成（C7）：肺表面半透明，内部气道与病灶的空间关系清晰可见"));});
  // 5. 规划（约 35 s）：改选下一处病灶并在 PL 上重新规划；再演示器械直径约束
  // 关闭 C7 会先释放 PL 显示帧（短暂忙碌）；等界面空闲后演示器械直径，再重新规划
  demoAt(token,53000,[this,token]{demoRestoreView();demoWhen(token,[this]{return !processing();},10000,[this,token](bool){demoDiameter(token);});});
 }
void demoDiameter(int token){
  tabs->setCurrentIndex(1);showStructure(2);
  int reach=colorMode->findText(u("按器械可达性"));if(reach>=0){demoColorBackup=colorMode->currentIndex();colorMode->setCurrentIndex(reach);}
  demoCaption(4,u("可达性着色：按当前器械直径与安全余量，标出可通过与受限的气道"));
  demoAt(token,4000,[this,token]{demoDiameterBackup=diameter->value();diameter->setValue(qMin(diameter->maximum(),3.0));demoMark("diameter_3mm");
   demoCaption(4,u("器械直径改为 3 mm：可通过范围即时缩小，受限分支随之变色"));
   demoAt(token,6000,[this,token]{if(demoDiameterBackup>0){diameter->setValue(demoDiameterBackup);demoDiameterBackup=0;}
    if(demoColorBackup>=0){colorMode->setCurrentIndex(demoColorBackup);demoColorBackup=-1;}demoReplan(token);});});
 }
void demoReplan(int token){
  bool canSwitch=lesionList->count()>1&&lesionList->isEnabled()&&navButton->isEnabled();
  demoMarks<<QJsonObject{{"mark","replan_check"},{"ms",double(demoElapsed())},{"lesions",lesionList->count()},{"lesion_enabled",lesionList->isEnabled()},
   {"nav_enabled",navButton->isEnabled()},{"processing",processing()},{"replan_unavailable",replanUnavailable}};
  if(!canSwitch){demoNavigate(token,u("导航：PL（C6）实时渲染虚拟支气管镜，沿规划路径前进；右上小图同步显示镜头位置"));return;}
  lesionList->setCurrentIndex((lesionList->currentIndex()+1)%lesionList->count());bridge->click("fit");
  demoCaption(5,u("改选另一处病灶：PL 重新计算距离场（C8）与路径（C4），完成后自动载入"));demoMark("replan_start");
  demoAt(token,1200,[this,token]{navButton->click();setDrawer("process");
   demoWhen(token,[this]{return !processing()&&!scenePath.isEmpty();},60000,[this,token](bool ok){demoMark(ok?"replan_done":"replan_timeout");setDrawer("");
    demoNavigate(token,!ok?u("重新规划仍在进行，继续演示导航"):replanUnavailable?u("新目标在器械约束下不可达，已保留上次结果"):
     u("新路径已生成（右上小图）；净空不足的末段会截止并提示。PL 正在装入 C6 导航渲染"));});});
 }
void demoNavigate(int token,const QString&intro){
  tabs->setCurrentIndex(2);if(navStart->isEnabled())navStart->click();
  if(dualCheck->isEnabled()){demoDualBackup=dualCheck->isChecked()?1:0;dualCheck->setChecked(true);}
  demoCaption(5,intro);
  // 等 C6 画出首帧再开始前进（新载入场景时 PL 需先装入 C6 并上传场景）
  demoWhen(token,[this]{return scope->hasPlFrame();},20000,[this,token](bool ok){demoMark(ok?"scope_ready":"scope_timeout");
   demoCaption(5,u("导航：PL（C6）实时渲染虚拟支气管镜，沿规划路径前进；右上小图同步显示镜头位置"));
   // 导航时长按剩余预算决定：留出终点 12 s 与结尾 8 s；速度按剩余路程计算，使镜头恰好在窗口内走到终点
   qint64 window=qBound<qint64>(20000,demoBudgetMs-20000-demoElapsed()-1000,50000);
   demoAt(token,1000,[this,token,window]{demoSpeedBackup=navigationSpeed->value();
    double remaining=qMax(1.,double(scope->totalDistance()-scope->distance()));
    navigationSpeed->setValue(qBound(qMax(navigationSpeed->minimum(),3.),remaining/(window/1000.)*1.08,navigationSpeed->maximum()));
    if(!playing)navigationToggle();demoPlayStart=beatClock.elapsed();demoMark("navigation_play");demoWaitEnd(token,window);});});
 }
void demoWaitEnd(int token,qint64 window){
  demoAt(token,500,[this,token,window]{
   if(playing&&beatClock.elapsed()-demoPlayStart<window){demoWaitEnd(token,window);return;}
   if(playing)navigationPause();if(navEnd->isEnabled())navEnd->click();
   demoCaption(6,u("路径终点：右侧给出当前管径、器械余量与到目标的剩余距离（图像几何估算）"));
   demoAt(token,12000,[this,token]{demoTitle(u("KV260 支气管导航工作站"),u("研究原型 · 非临床诊断"));demoAt(token,8000,[this]{demoStop();});});});
 }
// 处理演示：字幕跟随后台阶段事件（pipelineEvent 中调用）
void demoProcessStart(){
  if(demoActive){demoStop();return;}
  if(shellDead||processing()||input.isEmpty()||!runButton->isEnabled())return;
  ++demoToken;int token=demoToken;demoBegin(true);
  tabs->setCurrentIndex(0);setDrawer("process");
  // 先只显示原始 CT（关闭已有结果的分割叠加），处理完成后再叠加本次结果
  demoMaskBackup=bridge->get("mask").toMap()["checked"].toBool()?1:0;bridge->setChecked("mask",false);
  demoCaption(1,u("现场完整处理：从原始 CT 开始，各阶段的 PL 模块按顺序动态装入"));
  demoAt(token,1500,[this]{runButton->click();demoMark("run_clicked");});
 }
void demoProcessEvent(const QJsonObject&o){
  if(!demoActive||!demoProcessMode)return;QString e=o["event"].toString(),k=o["stage"].toString();
  if(e=="stage"){static const QHash<QString,QPair<int,const char*>> text={
    {"segmentation",{2,"CT 分割：PL HU 预处理（D6）→ PL INT8 卷积网络（C5）逐层推理"}},
    {"airway-cleanup",{3,"气道清理：PS 四核执行连通域、闭运算与填洞"}},
    {"reconstruction",{4,"三维重建：PL 移动立方体（D7）→ PL 网格平滑（D9）"}},
    {"navigation",{5,"路径规划：PL 体距离场（C8）→ PL 路径与镜头审核（C4）"}}};
   if(text.contains(k))demoCaption(text[k].first,QString::fromUtf8(text[k].second));}
  else if(e=="completed"){bool ok=o["status"]=="passed";demoCaption(6,ok?QString(u("处理完成 · 后台用时 %1 s，正在载入新结果")).arg(o["seconds"].toDouble(),0,'f',0):u("处理已停止"));
   int token=demoToken;
   if(ok)demoWhen(token,[this]{return !processing()&&!scenePath.isEmpty();},60000,[this,token](bool){setDrawer("");tabs->setCurrentIndex(0);bridge->setChecked("mask",true);
     demoCaption(6,u("新结果：本次现场分割得到的肺、气道与病灶"));
     demoAt(token,6000,[this,token]{tabs->setCurrentIndex(1);showStructure(2);rotation.start(30);
      demoCaption(6,u("新结果：本次现场重建的三维模型与规划路径"));demoAt(token,8000,[this]{demoStop();});});});
   else demoAt(token,5000,[this]{demoStop();});}
  else if(e=="error"){demoCaption(6,u("处理失败，详见日志"));int token=demoToken;demoAt(token,5000,[this]{demoStop();});}
 }
// ── 演示录制检查（KV260_DEMO_CAPTURE=<目录>[,process]）：自动开始演示，每 5 s 截图，结束后写时间记录并退出 ──
bool demoCaptureMode=qEnvironmentVariableIsSet("KV260_DEMO_CAPTURE");
QString demoCaptureDir()const{return qEnvironmentVariable("KV260_DEMO_CAPTURE").section(',',0,0);}
bool demoCaptureProcess()const{return qEnvironmentVariable("KV260_DEMO_CAPTURE").section(',',1,1)=="process";}
int demoShot=0;
void demoCaptureStart(){if(demoCaptureMode)QTimer::singleShot(3000,this,[this]{demoCaptureTry();});}
void demoCaptureTry(){if(shellDead)return;
  bool ready=demoCaptureProcess()?(!processing()&&!input.isEmpty()&&runButton->isEnabled()):(!processing()&&!scenePath.isEmpty());
  if(!ready){QTimer::singleShot(500,this,[this]{demoCaptureTry();});return;}
  QDir().mkpath(demoCaptureDir());if(demoCaptureProcess())demoProcessStart();else demoStart();
  if(!demoActive){writeJson(demoCaptureDir()+"/demo_capture.json",QJsonObject{{"started",false}});QApplication::exit(2);}}
void demoCaptureBegin(int token){if(!demoCaptureMode)return;demoShot=0;demoCaptureShot(token);}
void demoCaptureShot(int token){QTimer::singleShot(demoShot==0?800:5000,this,[this,token]{if(shellDead||!demoActive||token!=demoToken)return;
  grab().save(QString("%1/%2_%3s.png").arg(demoCaptureDir()).arg(demoShot,3,10,QChar('0')).arg(demoElapsed()/1000));++demoShot;demoCaptureShot(token);});}
void demoCaptureFinish(){if(!demoCaptureMode)return;
  writeJson(demoCaptureDir()+"/demo_capture.json",QJsonObject{{"started",true},{"process",demoCaptureProcess()},{"total_ms",double(demoElapsed())},{"marks",demoMarks},{"shots",demoShot},{"qml_errors",QJsonArray::fromStringList(shellErrors)},{"result",source}});
  QTimer::singleShot(1500,this,[]{QApplication::exit(0);});}
