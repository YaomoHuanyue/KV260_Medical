 int surfaceTestStage=0,surfaceFrameBase=0,surfacePolls=0,surfaceTickBase=0,surfaceTarget=-1;
 QTimer surfaceTestTimer;QJsonArray surfaceChecks;QJsonObject surfaceOriginal,surfaceAutoPose,surfaceManualPose;
 void surfaceCheck(QString name,bool good){surfaceChecks.append(QJsonObject{{"name",name},{"passed",good}});if(!good)failed=true;}
 void surfaceTestFinish(){
  surfaceTestTimer.stop();QDir().mkpath(evidence);capture("active_selected_navigation");
  writeJson(evidence+"/active_surface_UI.json",{{"status",failed?"failed":"passed_actual_Qt_active_comparison_selected_path_C9_manual_camera_and_linked_reference"},
   {"checks",surfaceChecks},{"scene",scenePath},{"complete_surface",scene["complete_surface"]},
   {"selection",scene["navigation"].toObject()["report"].toObject()["selection"]},
   {"actual_PL_frame",plLastFrame},{"presented_frame",scope->presentedScopeFrame()},
   {"linked_reference",miniOverview->referenceCameraMetrics()},{"automatic_pose",surfaceAutoPose},{"manual_pose",surfaceManualPose},
   {"scope_GL",scope->metrics()},{"UI_peak_RSS_MiB",peakRSS()},{"physical_mouse_verified",false}});
  finishTest();
 }
 void surfaceTestAdvance(){
  qInfo()<<"R14b surface stage"<<surfaceTestStage<<"failed"<<failed<<"scene"<<scenePath<<"compare enabled/visible"<<compareButton->isEnabled()<<compareButton->isVisible()<<"compare geometry"<<compareButton->geometry();
  if(failed){surfaceTestFinish();return;}
  if(surfaceTestStage==0){
   surfaceOriginal=scene;surfaceCheck("current_complete_scene_loaded",(!scene.value("complete_surface").toObject().isEmpty()));
   surfaceCheck("current_surface_compare_enabled",compareButton->isEnabled());
   int previous=lesionList->currentIndex();lesionList->setCurrentIndex((previous+1)%lesionList->count());surfaceTarget=lesion->value();
   surfaceCheck("selected_another_target_with_actual_combo",surfaceTarget!=scene["navigation"].toObject()["report"].toObject()["target"].toObject()["index"].toInt(-1));
   diameter->setValue(1.8);margin->setValue(.3);minimumBend->setValue(0);surfaceTickBase=ticks;
   surfaceTestStage=1;compareButton->click();return;
  }
  if(surfaceTestStage==1){
   auto old=surfaceOriginal["complete_surface"].toObject(),now=scene["complete_surface"].toObject();
   surfaceCheck("comparison_keeps_scalar_and_route_revision",old["revision"]==now["revision"]&&old["scalar_sha256"]==now["scalar_sha256"]);
   surfaceCheck("comparison_keeps_actual_navigation_path",surfaceOriginal["navigation"].toObject()["points"]==scene["navigation"].toObject()["points"]);
   surfaceCheck("background_comparison_keeps_UI_heartbeat",ticks-surfaceTickBase>10);
   surfaceCheck("new_comparison_target_preserved_in_controls",lesion->value()==surfaceTarget&&scene["navigation"].toObject()["whole_instrument_profiles"].toObject()["binding"].toObject()["target"].toObject()["index"].toInt(-1)==surfaceTarget);
   surfaceCheck("current_results_button_enabled",comparisonResults->isEnabled());
   surfaceTestStage=2;tabs->setCurrentIndex(1);comparisonResults->click();return;
  }
  if(surfaceTestStage!=2)return;surfaceTestStage=3;
  auto nav=scene["navigation"].toObject(),report=nav["report"].toObject(),identity=report["selection"].toObject();
  surfaceCheck("selected_group_and_candidate_applied",identity["group_index"].toInt(-1)==selectedGroup&&identity["candidate_id"].toInt(-1)==selectedCandidate);
  surfaceCheck("fresh_route_revision_same_surface",scene["complete_surface"].toObject()["revision"]!=surfaceOriginal["complete_surface"].toObject()["revision"]&&scene["complete_surface"].toObject()["scalar_sha256"]==surfaceOriginal["complete_surface"].toObject()["scalar_sha256"]);
  surfaceCheck("route_camera_HUD_columns_paired",nav["points"].toArray().size()==report["point_count"].toInt()&&scope->cameraCount()==nav["positions"].toArray().size()&&nav["hud"].toObject()["samples"].toArray().size()==nav["points"].toArray().size());
  surfaceCheck("selected_curve_no_branch_substitution",!report["automatic_route_replanning"].toBool(true)&&!report["branch_guidance_application_pending"].toBool(true));
  surfaceCheck("selected_route_targets_current_candidate",report["target"].toObject()["index"].toInt(-1)==surfaceTarget);
  auto events=report["branch_guidance"].toObject()["events"].toArray();surfaceCheck("nonempty_current_surface_branch_cues",!events.isEmpty());
  if(failed||events.isEmpty()){surfaceTestFinish();return;}
  auto arcs=nav["arc"].toArray();double wanted=events.first().toObject()["junction_arc_mm"].toDouble();int nearest=0;
  for(int i=1;i<arcs.size();++i)if(std::abs(arcs[i].toDouble()-wanted)<std::abs(arcs[nearest].toDouble()-wanted))nearest=i;
  surfaceFrameBase=plFrames;surfacePolls=0;dualCheck->setChecked(true);cameraSlider->setValue(nearest);tabs->setCurrentIndex(2);configureScope();
  connect(&surfaceTestTimer,&QTimer::timeout,this,[this]{
   auto requested=scope->cameraRequest(),shown=scope->presentedScopeFrame(),ref=miniOverview->referenceCameraMetrics();
   bool ready=plFrames>surfaceFrameBase&&!shown.isEmpty()&&shown["sequence"]==plLastFrame["sequence"]&&
    std::abs(shown["arc_mm"].toDouble()-scope->distance())<.001&&plLastFrame["branch_event"].toInt(-1)>=0;
   if(surfaceTestStage==4)ready=ready&&shown["requested_camera"].toObject()["forward"]==surfaceManualPose["forward"];
   if(!ready&&++surfacePolls<320)return;
   surfaceCheck(surfaceTestStage==3?"selected_route_actual_C9_frame":"manual_route_actual_C9_frame",ready);
   surfaceCheck("reference_camera_tracks_presented_sequence",ref["valid"].toBool()&&ref["sequence"]==shown["sequence"]);
   if(surfaceTestStage==3&&!failed){
    surfaceAutoPose=requested;surfaceFrameBase=plFrames;surfacePolls=0;surfaceTestStage=4;
    bool alignFound=false;for(auto*c:findChildren<QCheckBox*>())if(c->text()==u("自动对齐路径")){alignFound=true;if(c->isChecked())c->click();}
    surfaceCheck("manual_test_uses_alignment_checkbox",alignFound);
    testDrag(scope,QPoint(scope->width()/2,scope->height()/2),QPoint(scope->width()/2+35,scope->height()/2+10));
    surfaceManualPose=scope->cameraRequest();surfaceCheck("manual_pose_differs_from_auto",std::abs(surfaceManualPose["manual_yaw_degrees"].toDouble())>1.);
    return;
   }
   auto actualRequest=shown["requested_camera"].toObject();
   surfaceCheck("completed_PL_pose_keeps_manual_direction",actualRequest["forward"]==surfaceManualPose["forward"]&&actualRequest["camera"]==surfaceManualPose["camera"]);
   surfaceCheck("selected_navigation_actual_GL",scope->metrics()["valid"].toBool()&&scope->metrics()["error"].toString().isEmpty());
   surfaceTestFinish();
  });surfaceTestTimer.start(250);
 }
