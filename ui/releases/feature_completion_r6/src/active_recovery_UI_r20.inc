 bool activeRecoveryTesting=qEnvironmentVariableIntValue("KV260_ACTIVE_RECOVERY_UI_TEST")==1;
 int activeRecoveryStage=0,activeRecoveryTarget=-1,activeRecoveryFrameBase=0,activeRecoveryPolls=0;
 int recoverySavedTab=0,recoverySavedTarget=-1;QJsonObject recoverySavedScope,recoverySavedOverview,recoverySavedMini;
 QJsonObject activeRecoveryBefore,activeRecoveryBeforeScope,activeRecoveryBeforeOverview,activeRecoveryFrame;
 QJsonArray activeRecoveryChecks;QTimer activeRecoveryTimer;
 void saveRecoveryView(){recoverySavedScope=scope->scopeViewState();recoverySavedOverview=overview->overviewCamera();recoverySavedMini=miniOverview->overviewCamera();
  recoverySavedTab=tabs->currentIndex();recoverySavedTarget=lesion->value();}
 void restoreRecoveryView(){
  if(!scope->restoreScopeViewState(recoverySavedScope))throw std::runtime_error("Recovery could not restore navigation camera");
  if(!overview->restoreOverviewCamera(recoverySavedOverview)||!miniOverview->restoreOverviewCamera(recoverySavedMini))throw std::runtime_error("Recovery could not restore overview cameras");int index=lesionList->findData(recoverySavedTarget);
  if(index>=0)lesionList->setCurrentIndex(index);updateCandidate();tabs->setCurrentIndex(recoverySavedTab);
 }
 void recoveryCheck(QString name,bool good){activeRecoveryChecks.append(QJsonObject{{"name",name},{"passed",good}});if(!good)failed=true;}
 void finishActiveRecovery(QJsonObject exported={}){
  activeRecoveryTimer.stop();QDir().mkpath(evidence);capture("active_recovery_review");
  writeJson(evidence+"/active_recovery_UI.json",{{"status",failed?"failed":"passed_current_recovery_action_CT_overlays_table_navigation_restore_and_export"},
   {"checks",activeRecoveryChecks},{"before_scene",activeRecoveryBefore},{"scene",scenePath},{"selected_target",lesion->value()},
   {"recovery_binding",scene["distal_recovery_binding"]},{"before_scope",activeRecoveryBeforeScope},{"restored_scope",recoverySavedScope},
   {"before_overview",activeRecoveryBeforeOverview},{"restored_overview",recoverySavedOverview},{"actual_PL_frame",activeRecoveryFrame},
   {"export",exported},{"UI_peak_RSS_MiB",peakRSS()},{"physical_user_review",false}});finishTest();
 }
 void recoveryExported(QJsonObject result){
  recoveryCheck("export_has_current_recovery_binding",QFileInfo::exists(result["path"].toString()+"/active_recovery_binding.json"));
  finishActiveRecovery(result);
 }
 void recoveryAdvance(){
  if(failed){finishActiveRecovery();return;}
  if(activeRecoveryStage==0){
   activeRecoveryBefore=scene;recoveryCheck("current_recovery_button_enabled",recoveryButton->isEnabled());
   activeRecoveryTarget=qEnvironmentVariableIsSet("KV260_RECOVERY_TARGET")?qEnvironmentVariableIntValue("KV260_RECOVERY_TARGET"):lesion->value();
   int index=lesionList->findData(activeRecoveryTarget);recoveryCheck("requested_candidate_present",index>=0);if(failed){finishActiveRecovery();return;}
   lesionList->setCurrentIndex(index);dualCheck->setChecked(true);tabs->setCurrentIndex(2);scope->setDistance(std::min(35.f,scope->totalDistance()*.3f));
   for(auto*c:findChildren<QCheckBox*>())if(c->text()==u("自动对齐路径")&&c->isChecked())QTest::mouseClick(c,Qt::LeftButton);
   testDrag(scope,QPoint(scope->width()/2,scope->height()/2),QPoint(scope->width()/2+24,scope->height()/2+6));
   activeRecoveryFrameBase=plFrames;activeRecoveryPolls=0;activeRecoveryStage=1;tabs->setCurrentIndex(2);configureScope();
   connect(&activeRecoveryTimer,&QTimer::timeout,this,[this]{
    auto shown=scope->presentedScopeFrame();bool ready=plFrames>activeRecoveryFrameBase&&!shown.isEmpty()&&
     shown["sequence"]==plLastFrame["sequence"]&&std::abs(shown["arc_mm"].toDouble()-scope->distance())<.001;
    if(!ready&&++activeRecoveryPolls<360)return;activeRecoveryTimer.stop();recoveryCheck("actual_current_C9_before_and_after_action",ready);
    if(failed){finishActiveRecovery();return;}
    if(activeRecoveryStage==1){activeRecoveryBeforeScope=scope->scopeViewState();activeRecoveryBeforeOverview=overview->overviewCamera();
     activeRecoveryStage=2;QTest::mouseClick(recoveryButton,Qt::LeftButton);return;}
    activeRecoveryFrame=shown;recoveryCheck("restored_PL_keeps_current_revision",shown["revision"]==activeRecoveryBefore["complete_surface"].toObject()["revision"]);
    recoveryCheck("restored_PL_keeps_manual_pose",shown["requested_camera"].toObject()["forward"]==scope->cameraRequest()["forward"]);
    recoveryCheck("linked_reference_tracks_restored_frame",miniOverview->referenceCameraMetrics()["sequence"]==shown["sequence"]);
    if(qEnvironmentVariable("KV260_RECOVERY_KIND")=="other"){finishActiveRecovery();return;}
    activeRecoveryStage=4;QTest::mouseClick(exportButton,Qt::LeftButton);
   });activeRecoveryTimer.start(250);return;
  }
  if(activeRecoveryStage!=2)return;
  recoveryCheck("model_field_path_camera_guidance_unchanged",scene["complete_surface"]==activeRecoveryBefore["complete_surface"]&&scene["navigation"]==activeRecoveryBefore["navigation"]);
  recoveryCheck("current_selected_recovery_candidate_preserved",lesion->value()==activeRecoveryTarget&&scene["distal_recovery"].toObject()["candidate_index_zero_based"].toInt(-1)==activeRecoveryTarget);
  recoveryCheck("manual_camera_and_overview_restored",scope->scopeViewState()==activeRecoveryBeforeScope&&overview->overviewCamera()==activeRecoveryBeforeOverview);
  auto report=scene["distal_recovery"].toObject();auto rows=report["candidates"].toArray();auto summary=report["summary"].toObject();
  recoveryCheck("current_review_controls_available",!report.isEmpty()&&recoveryReviewButton->isEnabled());
  tabs->setCurrentIndex(0);for(int index:{0,3,4,5,0}){airwayOverlay->setCurrentIndex(index);int bit=airwayOverlay->currentData().toInt();
   for(auto*v:slices)recoveryCheck("review_overlay_synchronized_"+QString::number(bit),v->airwayMaskBit()==bit);}
  bool yellow=summary["review_candidates"].toInt()==0;
  for(qint64 k=0;!yellow&&k<qint64(volume->dims[0])*volume->dims[1]*volume->dims[2];++k)if(volume->masks[k]&64){
   int x=k%volume->dims[0],y=(k/volume->dims[0])%volume->dims[1],z=k/(qint64(volume->dims[0])*volume->dims[1]);
   airwayOverlay->setCurrentIndex(4);axialSlider->setValue(z);auto color=slices[0]->sliceImage().pixelColor(x,y);
   yellow=color.red()>color.blue()+25&&color.green()>color.blue()+25;break;}
  recoveryCheck("actual_review_pixel_is_yellow",yellow);QTimer::singleShot(200,this,[this,rows]{
   auto*d=qobject_cast<QDialog*>(QApplication::activeModalWidget());if(!d){failed=true;return;}auto*t=d->findChild<QTableWidget*>();
   recoveryCheck("current_evidence_table_dimensions",t&&t->rowCount()==rows.size()&&t->columnCount()==7);
   d->grab().save(evidence+"/current_recovery_dialog.png");
   if(!t||rows.isEmpty())d->accept();else{t->scrollToItem(t->item(0,0));QTest::mouseClick(t->viewport(),Qt::LeftButton,Qt::NoModifier,t->visualItemRect(t->item(0,0)).center());}
  });showRecoveryReview();
  if(!rows.isEmpty()){auto row=rows.first().toObject();auto q=row["component_point_zyx"].toArray();int bit=row["classification"]=="review"?64:row["classification"]=="high"?32:8;
   recoveryCheck("actual_table_click_locates_CT_voxel",slices[0]->currentSlice()==q[0].toInt()&&slices[1]->currentSlice()==q[1].toInt()&&slices[2]->currentSlice()==q[2].toInt()&&airwayOverlay->currentData().toInt()==bit);}
  airwayOverlay->setCurrentIndex(0);activeRecoveryStage=3;activeRecoveryFrameBase=plFrames;activeRecoveryPolls=0;
  tabs->setCurrentIndex(2);configureScope();activeRecoveryTimer.start(250);
 }
