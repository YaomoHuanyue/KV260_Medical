 bool missingDataTesting=qEnvironmentVariableIntValue("KV260_MISSING_DATA_TEST")==1;
 int missingDataStage=0;QJsonArray missingDataChecks;
 void missingDataCheck(QString name,bool good){
  missingDataChecks.append(QJsonObject{{"name",name},{"passed",good}});if(!good)failed=true;
 }
 void missingDataAdvance(){
  if(!missingDataTesting)return;
  if(failed){missingDataFinish();return;}
  if(missingDataStage==0){missingDataStage=1;
   prepare(qEnvironmentVariable("KV260_MISSING_NAV_RESULT"));return;}
  if(missingDataStage==1){
   missingDataCheck("partial_reconstruction_without_route_loaded",
    source==qEnvironmentVariable("KV260_MISSING_NAV_RESULT")&&
    !scene["meshes"].toObject().isEmpty()&&scope->cameraCount()==0);
   tabs->setCurrentIndex(2);configureScope();missingDataStage=2;
   QTimer::singleShot(600,this,[this]{missingDataAdvance();});return;
  }
  if(missingDataStage==2){
   missingDataCheck("no_scope_worker_or_frame_for_missing_navigation",!plScope->active()&&plFrames==0);
   missingDataCheck("placeholder_shown_and_scope_hidden",scopeUnavailable->isVisible()&&!scope->isVisible());
   missingDataCheck("playback_disabled_without_route",!playButton->isEnabled());
   capture("partial_without_navigation");missingDataStage=3;
   input=qEnvironmentVariable("KV260_RAW_CT_FIXTURE");source.clear();prepare();return;
  }
  if(missingDataStage==3){
   missingDataCheck("raw_CT_without_model_loaded",scene["source"]=="raw_ct"&&
    scene["meshes"].toObject().isEmpty()&&scope->cameraCount()==0);
   tabs->setCurrentIndex(1);QTest::mouseClick(preciseBlend,Qt::LeftButton);configureScope();
   missingDataCheck("empty_model_composition_disabled",!preciseBlend->isEnabled()&&!preciseBlend->isChecked());
   tabs->setCurrentIndex(2);configureScope();missingDataStage=4;
   QTimer::singleShot(600,this,[this]{missingDataAdvance();});return;
  }
  missingDataCheck("no_scope_or_composite_worker_for_raw_CT",!plScope->active()&&!plComposite->active()&&plFrames==0&&compositeFrames==0);
  missingDataCheck("raw_CT_navigation_placeholder",scopeUnavailable->isVisible()&&!scope->isVisible());
  capture("raw_CT_without_model_or_navigation");missingDataFinish();
 }
 void missingDataFinish(){
  QDir().mkpath(evidence);
  writeJson(evidence+"/missing_data_UI.json",QJsonObject{
   {"status",failed?"failed":"passed_missing_navigation_and_raw_CT_no_spurious_PL_workers"},
   {"checks",missingDataChecks},{"PL_scope_frames",plFrames},{"PL_composite_frames",compositeFrames},
   {"physical_mouse_verified",false},{"new_PL_bitstream",false}});
  close();if(failed)QTimer::singleShot(100,[]{QApplication::exit(1);});
 }
