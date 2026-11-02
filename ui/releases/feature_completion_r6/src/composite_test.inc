bool compositeControlsMatch()const{
 auto meta=overview->completedComposite(),c=meta["report"].toObject()["controls"].toObject();
 if(compositeFrames<=compositeBase||meta["width"]!=compositeExpected["width"]||meta["height"]!=compositeExpected["height"])return false;
 for(const char*k:{"full_lung","layers","clipping"})if(c[k]!=compositeExpected[k])return false;
 for(const char*k:{"yaw_degrees","pitch_degrees","zoom","radius_mm","color_mode","required_radius_mm","resolution_margin_mm"})if(std::abs(c[k].toDouble()-compositeExpected[k].toDouble())>1e-4)return false;
 if(c["center_lps_mm"]!=compositeExpected["center_lps_mm"])return false;
 return c["lung_opacity_byte"].toInt()==int(std::floor(compositeExpected["lung_opacity"].toDouble()*255+.5));
}
void compositeAdvance(){
 if(compositeStage>=0){
  bool ready=compositeStage==5?plFrames>compositeBase&&!graphicsTransition&&!plComposite->active():
   compositeStage>=7?!processing()&&!plScope->active()&&!plComposite->active():compositeControlsMatch();
  if(!ready){if(compositeDeadline.elapsed()>60000){compositeCheck.stop();failed=true;record("composite_UI_timeout_stage_"+QString::number(compositeStage));finishTest();}return;}
  if(compositeStage==3){auto p=overview->candidateScreenPoint(lesion->value());
   if(p.x()<0||QLineF(p,overview->rect().center()).length()>3)failed=true;
   int before=lesion->value();QMouseEvent click(QEvent::MouseButtonPress,p,Qt::RightButton,Qt::RightButton,Qt::NoModifier);QApplication::sendEvent(overview,&click);
   if(lesion->value()!=before)failed=true;record("completed_frame_candidate_pick");
  }
  capture("composite_"+QString::number(compositeStage));record("composite_UI_stage_"+QString::number(compositeStage)+"_completed");
  if(compositeStage==8){if(overview->compositeMode()||!overview->metrics()["error"].toString().isEmpty())failed=true;record("fast_GPU_overview_restored_after_C7_stop");compositeCheck.stop();finishTest();return;}
 }
 ++compositeStage;compositeBase=compositeStage==5?plFrames:compositeFrames;compositeDeadline.restart();
 switch(compositeStage){
  case 0:preciseBlend->setChecked(true);tabs->setCurrentIndex(1);overview->resetView();break;
  case 1:structureButtons[0]->click();lungQuality->setCurrentIndex(0);opacity->setValue(40);colorMode->setCurrentIndex(1);break;
  case 2:structureButtons[2]->click();meshLayers[0]->setChecked(true);lungQuality->setCurrentIndex(1);colorMode->setCurrentIndex(0);break;
  case 3:QTest::mouseClick(meshLayers[0],Qt::LeftButton);focusButton->click();colorMode->setCurrentIndex(2);break;
  case 4:{auto point=overview->candidateScreenPoint(lesion->value());overview->resetView();for(int i=0;i<64;++i)overview->turn(1.2f);
   if(QLineF(point,overview->candidateScreenPoint(lesion->value())).length()>1e-5)failed=true;
   record("retained_frame_projection_during_64_pose_burst");resize(940,720);break;}
  case 5:tabs->setCurrentIndex(2);firstBranchPose();break;
  case 6:tabs->setCurrentIndex(1);overview->resetView();colorMode->setCurrentIndex(3);clipAxis->setCurrentIndex(0);clipCheck->setChecked(true);break;
  case 7:tabs->setCurrentIndex(0);return;
  case 8:preciseBlend->setChecked(false);tabs->setCurrentIndex(1);overview->turn(10);return;
 }
 QCoreApplication::processEvents();compositeExpected=overview->overviewRequest();
 if(compositeStage!=5&&plComposite->active()&&!processing())plComposite->request(compositeExpected);
}
