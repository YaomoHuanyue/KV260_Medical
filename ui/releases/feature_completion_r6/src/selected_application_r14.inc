 int selectedGroup=-1,selectedCandidate=-1,selectedTestStage=0,selectedFrameBase=0;
 bool selectedTaskPending=false;QJsonArray selectedChecks;QTimer selectedWait;int selectedPolls=0;
 void startSelectedPath(int group,int candidate){
  if(scene.contains("complete_surface")){startSurfaceAction("selected-path",group,candidate);return;}
  if(processing()||source.isEmpty())return;
  if((plScope&&plScope->active())||(plComposite&&plComposite->active())){
   releaseGraphics([this,group,candidate]{startSelectedPath(group,candidate);});return;
  }
  play.stop();playing=false;playButton->setText(u("沿路径播放"));scope->setPlayback(false);
  selectedGroup=group;selectedCandidate=candidate;selectedTaskPending=true;
  runOutput.clear();failed=false;errors.clear();jobPending.clear();taskClock.restart();
  stopFile.clear();QStringList args={root+"/ui/releases/feature_completion_r6/backend_selected_r1.py",
   "selected-path","--input",input,"--result",source,"--group",QString::number(group),"--candidate",QString::number(candidate)};
  jobProcess.start(root+"/.venv/bin/python",args);busy(true);stopButton->setEnabled(false);
  progress->setRange(0,0);message(u("正在审核所选路径；完成后更新实际导航"));record("selected_path_started");
 }
 void selectedPathPrepared(){
  if(!selectedTaskPending)return;selectedTaskPending=false;
  auto report=scene["navigation"].toObject()["report"].toObject();auto binding=report["selection"].toObject();
  bool valid=binding["group_index"].toInt(-1)==selectedGroup&&binding["candidate_id"].toInt(-1)==selectedCandidate&&
   !report["branch_guidance_application_pending"].toBool(true)&&!report["automatic_route_replanning"].toBool(true);
  if(!valid){failed=true;message(u("所选路径与完成结果配对失败"));return;}
  tabs->setCurrentIndex(2);message(u("已应用所选路径 · 导航只使用审核通过的前缀"));record("selected_path_applied");
 }
 void selectedCheck(QString name,bool pass){selectedChecks.append(QJsonObject{{"name",name},{"passed",pass}});if(!pass)failed=true;}
 void selectedTestAdvance(){
  if(selectedTestStage==0){
   if(failed){finishTest();return;}selectedTestStage=1;tabs->setCurrentIndex(1);showComparisons();return;
  }
  if(selectedTestStage!=1)return;selectedTestStage=2;
  auto nav=scene["navigation"].toObject(),r=nav["report"].toObject();
  auto b=r["selection"].toObject();selectedCheck("actual_selected_identity",b["group_index"].toInt(-1)==selectedGroup&&b["candidate_id"].toInt(-1)==selectedCandidate);
  selectedCheck("complete_data_loaded",nav["points"].toArray().size()==r["point_count"].toInt()&&scope->cameraCount()==nav["positions"].toArray().size());
  selectedCheck("original_path_not_replanned",!r["automatic_route_replanning"].toBool(true));
  auto events=r["branch_guidance"].toObject()["events"].toArray();
  selectedCheck("anatomical_branch_cues",events.size()==(selectedGroup<4?3:0));
  selectedCheck("fresh_self_contained_result",source.contains("/selected_")&&QFileInfo::exists(source+"/selected_pipeline.json"));
  selectedFrameBase=plFrames;selectedPolls=0;
  auto arcs=nav["arc"].toArray();double wanted=events.isEmpty()?0:(events.first().toObject()["show_from_mm"].toDouble()+events.first().toObject()["hide_after_mm"].toDouble())*.5;
  int nearest=0;for(int i=1;i<arcs.size();++i)if(std::abs(arcs[i].toDouble()-wanted)<std::abs(arcs[nearest].toDouble()-wanted))nearest=i;
  cameraSlider->setValue(nearest);tabs->setCurrentIndex(2);configureScope();
  connect(&selectedWait,&QTimer::timeout,this,[this]{
   bool newFrame=plFrames>selectedFrameBase;
   if(!newFrame&&++selectedPolls<100)return;
   selectedWait.stop();selectedCheck("actual_PL_navigation_frame",newFrame);
   if(selectedGroup<4)selectedCheck("selected_fork_marker_in_PL_frame",plLastFrame["branch_event"].toInt(-1)>=0);
   dualCheck->setChecked(true);QApplication::processEvents();QTest::qWait(150);
   selectedCheck("linked_selected_target_matches_route",miniOverview->featureMetrics()["selected_candidate"].toInt(-1)==scene["navigation"].toObject()["report"].toObject()["target"].toObject()["index"].toInt(-2));
   selectedCheck("position_readout_matches_camera",navigationPosition->text()==QString(u("位置 %1 / %2 mm")).arg(scope->distance(),0,'f',1).arg(scope->totalDistance(),0,'f',1));
   auto shown=scope->presentedScopeFrame(),ref=miniOverview->referenceCameraMetrics();
   selectedCheck("linked_reference_tracks_presented_PL_camera",ref["valid"].toBool()&&ref["sequence"]==shown["sequence"]&&std::abs(ref["arc_mm"].toDouble()-shown["arc_mm"].toDouble())<.001);
   selectedCheck("completed_frame_matches_requested_arc",std::abs(plLastFrame["arc_mm"].toDouble()-scope->distance())<.001);

   auto m=scope->metrics();selectedCheck("actual_GL_display",m["valid"].toBool()&&m["error"].toString().isEmpty());
   QDir().mkpath(evidence);capture("selected_navigation");
   writeJson(evidence+"/selected_application_UI.json",QJsonObject{{"status",failed?"failed":"actual_Qt_selection_audit_navigation_camera_and_branch_frame_passed"},
    {"checks",selectedChecks},{"source_result",source},{"scene",scenePath},{"report",scene["navigation"].toObject()["report"]},
    {"actual_PL_frame",plLastFrame},{"scope_GL",m},{"physical_mouse_verified",false}});
   finishTest();
  });selectedWait.start(700);
 }
