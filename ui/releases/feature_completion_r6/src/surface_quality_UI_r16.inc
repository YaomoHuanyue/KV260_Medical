 QComboBox*surfaceQuality=nullptr;QPushButton*surfaceQualityButton=nullptr;
 bool qualityTesting=qEnvironmentVariableIntValue("KV260_SURFACE_QUALITY_UI_TEST")==1;
 int qualityStage=0,qualityPolls=0,qualityFrames=0,qualityTicks=0;QTimer qualityTimer;
 QJsonObject qualityPrevious;QJsonArray qualityChecks,qualityTrials;
 void qualityBusy(bool value){
  if(surfaceQuality)surfaceQuality->setEnabled(!value);
  if(surfaceQualityButton)surfaceQualityButton->setEnabled(!value&&!source.isEmpty()&&canNavigate());
 }
 void qualityControls(QVBoxLayout*layout){
  auto*row=new QHBoxLayout;row->addWidget(new QLabel(u("气道表面来源 / 精度")));surfaceQuality=new QComboBox;
  surfaceQuality->addItems({u("清理后掩膜 · Q5 标准平滑"),u("清理后掩膜 · Q6 加强平滑"),
   u("网络概率 · Q5 标准平滑"),u("网络概率 · Q6 加强平滑")});
  surfaceQuality->setToolTip(u("两档均为 0.75 mm 采样；Q6 提高标量量化精度并加强平滑。重新提取 PL 网格并审核导航，不是显示分辨率。"));
  row->addWidget(surfaceQuality,1);surfaceQualityButton=new QPushButton(u("重新生成气道表面"));row->addWidget(surfaceQualityButton);
  connect(surfaceQualityButton,&QPushButton::clicked,this,[this]{startSurfaceAction("quality");});layout->addLayout(row);
 }
 void restoreQualityControls(){
  auto q=scene["complete_surface"].toObject()["quality"].toObject();
  if(!q.isEmpty())surfaceQuality->setCurrentIndex((q["source"]=="network_probability"?2:0)+(q["tier"]=="ultra"?1:0));
  bool probability=QFileInfo::exists(source+"/segmentation/airway_logits.json")&&QFileInfo::exists(source+"/segmentation/airway_logits.npy");
  for(int i:{2,3})surfaceQuality->setItemData(i,probability?QVariant():QVariant(0),Qt::UserRole-1);
  if(!probability&&surfaceQuality->currentIndex()>=2)surfaceQuality->setCurrentIndex(0);
  if(!q.isEmpty()&&!scene["complete_surface"].toObject().contains("comparison")){
   auto r=scene["navigation"].toObject()["report"].toObject();
   {QSignalBlocker b(lesion);lesion->setValue(r["target"].toObject()["index"].toInt());}
   {QSignalBlocker b(diameter);diameter->setValue(r["scope_diameter_mm"].toDouble());}
   {QSignalBlocker b(margin);margin->setValue(r["safety_margin_mm"].toDouble());}
   {QSignalBlocker b(minimumBend);minimumBend->setValue(r["minimum_bend_radius_mm"].toDouble());}
   refreshCandidates();updateAnalysis();
  }
 }
 void qualityCheck(QString name,bool good){qualityChecks.append(QJsonObject{{"name",name},{"passed",good}});if(!good)failed=true;}
 void qualityFinish(){
  qualityTimer.stop();QDir().mkpath(evidence);
  writeJson(evidence+"/quality_UI.json",{{"status",failed?"failed":"passed_actual_quality_controls_new_PL_mesh_route_camera_C9_and_linked_view"},
   {"checks",qualityChecks},{"trials",qualityTrials},{"scene",scenePath},{"UI_peak_RSS_MiB",peakRSS()},{"physical_mouse_verified",false}});
  finishTest();
 }
 void qualityWaitFrame(){
  auto shown=scope->presentedScopeFrame(),ref=miniOverview->referenceCameraMetrics();
  bool ready=plFrames>qualityFrames&&!shown.isEmpty()&&shown["sequence"]==plLastFrame["sequence"]&&
   std::abs(shown["arc_mm"].toDouble()-scope->distance())<.001&&plLastFrame["branch_event"].toInt(-1)>=0;
  if(!ready&&++qualityPolls<240)return;qualityTimer.stop();qualityCheck("actual_quality_C9_branch_frame",ready);
  qualityCheck("quality_linked_camera_sequence",ref["valid"].toBool()&&ref["sequence"]==shown["sequence"]);
  capture(QString("quality_navigation_%1").arg(qualityStage));
  qualityTrials.append(QJsonObject{{"scene",scenePath},{"complete_surface",scene["complete_surface"]},
   {"actual_PL_frame",plLastFrame},{"presented_frame",shown},{"linked_reference",ref}});
  if(failed||qualityStage==4){qualityFinish();return;}
  qualityPrevious=scene;qualityStage=3;qualityTicks=ticks;surfaceQuality->setCurrentIndex(2);surfaceQualityButton->click();
 }
 void qualityTestAdvance(){
  if(failed){qualityFinish();return;}
  if(qualityStage==0){
   qualityPrevious=scene;qualityCheck("quality_button_enabled",surfaceQualityButton->isEnabled());
   qualityStage=1;qualityTicks=ticks;tabs->setCurrentIndex(1);surfaceQuality->setCurrentIndex(1);surfaceQualityButton->click();return;
  }
  if(qualityStage!=1&&qualityStage!=3)return;
  auto old=qualityPrevious["complete_surface"].toObject(),now=scene["complete_surface"].toObject();
  auto nav=scene["navigation"].toObject(),r=nav["report"].toObject(),q=now["quality"].toObject();
  qualityCheck("selected_quality_applied",q["source"]==(qualityStage==1?"accepted_binary":"network_probability")&&q["tier"]==(qualityStage==1?"ultra":"high"));
  qualityCheck("new_surface_and_revision",old["revision"]!=now["revision"]&&old["scalar_sha256"]!=now["scalar_sha256"]);
  qualityCheck("same_CT_completed_result",scene["input_sha256"]==qualityPrevious["input_sha256"]&&scene["result"]==qualityPrevious["result"]);
  qualityCheck("old_comparisons_cleared",!now.contains("comparison")&&!nav.contains("whole_alternative_routes")&&!nav.contains("whole_instrument_profiles")&&!comparisonResults->isEnabled());
  qualityCheck("background_quality_heartbeat",ticks-qualityTicks>20);
  qualityCheck("target_and_constraints_retained",r["target"].toObject()["index"].toInt()==4&&std::abs(diameter->value()-1.8)<.001&&std::abs(margin->value()-.3)<.001);
  qualityCheck("route_camera_HUD_paired",nav["points"].toArray().size()==r["point_count"].toInt()&&nav["positions"].toArray().size()==scope->cameraCount()&&nav["hud"].toObject()["samples"].toArray().size()==nav["points"].toArray().size());
  auto events=r["branch_guidance"].toObject()["events"].toArray();qualityCheck("new_surface_branch_guidance",!events.isEmpty());
  if(failed||events.isEmpty()){qualityFinish();return;}
  auto arcs=nav["arc"].toArray();double wanted=events.first().toObject()["junction_arc_mm"].toDouble();int nearest=0;
  for(int i=1;i<arcs.size();++i)if(std::abs(arcs[i].toDouble()-wanted)<std::abs(arcs[nearest].toDouble()-wanted))nearest=i;
  qualityStage=qualityStage==1?2:4;qualityPolls=0;qualityFrames=plFrames;dualCheck->setChecked(true);cameraSlider->setValue(nearest);tabs->setCurrentIndex(2);configureScope();
  disconnect(&qualityTimer,nullptr,this,nullptr);connect(&qualityTimer,&QTimer::timeout,this,[this]{qualityWaitFrame();});qualityTimer.start(250);
 }
