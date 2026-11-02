 bool replanTesting=qEnvironmentVariableIntValue("KV260_REPLAN_UI_TEST")==1;
 int replanStage=0,replanTarget=-1,replanTicks=0,replanFrames=0,replanPolls=0;
 QJsonObject replanOriginal,replanOverview,replanSuccessful,replanAutoPose,replanManualPose,replanPresented,replanLinked;
 QJsonArray replanChecks;QTimer replanTimer;
 void replanCheck(QString name,bool good){replanChecks.append(QJsonObject{{"name",name},{"passed",good}});if(!good)failed=true;}
 void replanFinish(){
  replanTimer.stop();QDir().mkpath(evidence);capture("replan_final_state");
  writeJson(evidence+"/replan_UI.json",{{"status",failed?"failed":"passed_actual_Qt_explicit_replan_same_wall_new_target_constraints_C9_linked_camera_and_unreachable_state"},
   {"checks",replanChecks},{"original_scene",replanOriginal},{"successful_scene",replanSuccessful},
   {"final_scene",scenePath},{"last_successful_navigation",scene["navigation"]},{"unreachable_event",replanBlockedEvent},{"navigation_usable",!replanUnavailable},{"final_complete_surface",scene["complete_surface"]},
   {"saved_overview",replanOverview},{"automatic_pose",replanAutoPose},{"manual_pose",replanManualPose},
   {"successful_presented_frame",replanPresented},{"successful_linked_reference",replanLinked},
   {"UI_peak_RSS_MiB",peakRSS()},{"physical_mouse_review",false}});
  finishTest();
 }
 void replanAdvance(){
  qInfo()<<"R2280 replan stage"<<replanStage<<"failed/processing/navEnabled/canNavigate"<<failed<<processing()<<navButton->isEnabled()<<canNavigate()<<"candidate count/target"<<lesionList->count()<<lesion->value();
  if(failed){replanFinish();return;}
  if(replanStage==0){
   replanOriginal=scene;replanCheck("current_complete_scene_loaded",!scene["complete_surface"].toObject().isEmpty());
   tabs->setCurrentIndex(1);overview->turn(19);replanOverview=overview->overviewCamera();
   structureCameras[structureMode]=replanOverview;
   int before=lesionList->currentIndex();lesionList->setCurrentIndex((before+1)%lesionList->count());replanTarget=lesion->value();
   replanCheck("actual_candidate_combo_changes_target",replanTarget!=scene["navigation"].toObject()["report"].toObject()["target"].toObject()["index"].toInt(-1));
   diameter->setValue(1.8);margin->setValue(.3);minimumBend->setValue(0);replanTicks=ticks;
   replanCheck("replan_button_enabled",navButton->isEnabled());qInfo()<<"R2280 startup checks"<<QJsonDocument(replanChecks).toJson(QJsonDocument::Compact);if(failed){replanFinish();return;}replanStage=1;navButton->click();return;
  }
  if(replanStage==1){
   auto old=replanOriginal["complete_surface"].toObject(),now=scene["complete_surface"].toObject();
   auto nav=scene["navigation"].toObject(),report=nav["report"].toObject();
   replanCheck("fresh_route_revision_same_scalar",now["revision"]!=old["revision"]&&now["scalar_sha256"]==old["scalar_sha256"]);
   replanCheck("replan_descriptor_matches_current_revision",now["explicit_replan"].toObject()["revision"]==now["revision"]);
   replanCheck("masks_candidates_and_overview_mesh_unchanged",scene["masks"]==replanOriginal["masks"]&&scene["candidates"]==replanOriginal["candidates"]&&scene["meshes"].toObject()["lung"]==replanOriginal["meshes"].toObject()["lung"]);
   replanCheck("overview_rotation_zoom_pan_preserved",overview->overviewCamera()==replanOverview&&structureCameras[structureMode]==replanOverview);
   replanCheck("target_and_constraints_applied",report["target"].toObject()["index"].toInt(-1)==replanTarget&&report["scope_diameter_mm"].toDouble()==1.8&&report["safety_margin_mm"].toDouble()==.3&&report["minimum_bend_radius_mm"].toDouble()==0.);
   replanCheck("original_wall_and_bend_policy_retained",report["original_replanning_edge_weight_rule_preserved"].toBool()&&report["bend_constraint_passed"].toBool()&&!report["source_graph_edges_or_mask_changed"].toBool(true));
   replanCheck("background_replan_keeps_UI_heartbeat",ticks-replanTicks>10);
   replanCheck("stale_comparison_removed",!now.contains("comparison")&&!nav.contains("whole_instrument_profiles")&&!comparisonResults->isEnabled());
   replanCheck("new_camera_HUD_columns_paired",nav["points"].toArray().size()==report["point_count"].toInt()&&scope->cameraCount()==nav["positions"].toArray().size()&&nav["hud"].toObject()["samples"].toArray().size()==nav["points"].toArray().size());
   auto events=report["branch_guidance"].toObject()["events"].toArray();QJsonObject event;
   for(auto v:events)if(v.toObject()["available"].toBool()){event=v.toObject();break;}
   replanCheck("current_route_has_available_branch_guidance",!event.isEmpty()&&scope->cameraCount()>1);
   if(failed){replanFinish();return;}
   replanSuccessful=scene;capture("replan_model_same_surface");
   auto arcs=nav["arc"].toArray();double wanted=event["junction_arc_mm"].toDouble();int nearest=0;
   for(int i=1;i<arcs.size();++i)if(std::abs(arcs[i].toDouble()-wanted)<std::abs(arcs[nearest].toDouble()-wanted))nearest=i;
   replanStage=2;replanFrames=plFrames;replanPolls=0;dualCheck->setChecked(true);cameraSlider->setValue(nearest);
   tabs->setCurrentIndex(2);configureScope();
   connect(&replanTimer,&QTimer::timeout,this,[this]{
    auto shown=scope->presentedScopeFrame(),ref=miniOverview->referenceCameraMetrics();
    bool ready=plFrames>replanFrames&&!shown.isEmpty()&&shown["sequence"]==plLastFrame["sequence"]&&
     shown["revision"]==scene["complete_surface"].toObject()["revision"]&&
     std::abs(shown["arc_mm"].toDouble()-scope->distance())<.001&&plLastFrame["branch_event"].toInt(-1)>=0;
    if(replanStage==3)ready=ready&&shown["requested_camera"].toObject()["forward"]==replanManualPose["forward"];
    if(!ready&&++replanPolls<320)return;
    replanCheck(replanStage==2?"automatic_new_route_actual_C9_frame":"manual_new_route_actual_C9_frame",ready);
    replanCheck("linked_reference_uses_presented_sequence",ref["valid"].toBool()&&ref["sequence"]==shown["sequence"]);
    if(replanStage==2&&!failed){
     replanAutoPose=scope->cameraRequest();capture("replan_automatic_navigation");
     replanFrames=plFrames;replanPolls=0;replanStage=3;
     if(navigationAlign->isChecked())navigationAlign->click();
     testDrag(scope,QPoint(scope->width()/2,scope->height()/2),QPoint(scope->width()/2+35,scope->height()/2+10));
     replanManualPose=scope->cameraRequest();replanCheck("manual_direction_differs_from_auto",std::abs(replanManualPose["manual_yaw_degrees"].toDouble())>1.);return;
    }
    replanTimer.stop();replanPresented=shown;replanLinked=ref;
    replanCheck("manual_camera_matches_actual_frame",shown["requested_camera"].toObject()["forward"]==replanManualPose["forward"]);
    replanCheck("current_navigation_actual_GL",scope->metrics()["valid"].toBool()&&scope->metrics()["error"].toString().isEmpty());
    capture("replan_manual_navigation");if(failed){replanFinish();return;}
    replanStage=4;diameter->setValue(10);margin->setValue(5);minimumBend->setValue(100);replanTicks=ticks;
    navButton->click();
   });replanTimer.start(250);return;
  }
  if(replanStage==4){
   auto nav=scene["navigation"].toObject(),report=replanBlockedEvent["report"].toObject();
   replanCheck("unreachable_constraint_report_applied",report["status"]=="unreachable"&&report["scope_diameter_mm"].toDouble()==10.&&report["safety_margin_mm"].toDouble()==5.&&report["minimum_bend_radius_mm"].toDouble()==100.);
   replanCheck("unreachable_has_no_old_camera_or_playback",replanUnavailable&&report["point_count"].toInt(-1)==0&&!playButton->isEnabled()&&!cameraSlider->isEnabled()&&scopeUnavailable->isVisible()&&!scope->isVisible()&&!plScope->active());
   replanCheck("last_successful_scene_not_overwritten",scene==replanSuccessful&&!exportButton->isEnabled()&&!videoButton->isEnabled()&&!batchButton->isEnabled());
   replanCheck("unreachable_keeps_same_surface",scene["complete_surface"].toObject()["scalar_sha256"]==replanOriginal["complete_surface"].toObject()["scalar_sha256"]);
   replanCheck("second_background_replan_keeps_UI_heartbeat",ticks-replanTicks>10);
   replanStage=5;replanFinish();
  }
 }
