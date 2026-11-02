// Run against the actual Qt/GLES widget and the own-CT scene on the board.
// Numerical PL composition is checked separately on identical fragment inputs.
void structureInteractionTest(){
 QJsonArray checks;bool passed=true;
 auto check=[&](QString name,bool ok){checks.append(QJsonObject{{"name",name},{"passed",ok}});passed=passed&&ok;};
 tabs->setCurrentIndex(1);preciseBlend->setChecked(false);clipCheck->setChecked(false);
 auto containsBounds=[&](QString name){
  auto request=overview->overviewRequest();auto a=request["center_lps_mm"].toArray();QVector3D c(a[0].toDouble(),a[1].toDouble(),a[2].toDouble());
  QMatrix4x4 view,projection;float r=request["radius_mm"].toDouble(),z=request["zoom"].toDouble();
  view.lookAt(c+QVector3D(0,-r*2.8f/z,0),c,QVector3D(0,0,1));view.translate(c);view.rotate(request["pitch_degrees"].toDouble(),1,0,0);view.rotate(request["yaw_degrees"].toDouble(),0,0,1);view.translate(-c);
  projection.perspective(42,float(overview->width())/qMax(1,overview->height()),.1f,r*12);auto m=projection*view;
  auto o=scene["meshes"].toObject()[name].toObject();auto lo=o["bounds_min"].toArray(),hi=o["bounds_max"].toArray();if(lo.size()!=3||hi.size()!=3)return false;
  for(int i=0;i<8;++i){QVector4D p((i&1?hi:lo)[0].toDouble(),(i&2?hi:lo)[1].toDouble(),(i&4?hi:lo)[2].toDouble(),1);p=m*p;if(p.w()<=0||std::abs(p.x())>p.w()||std::abs(p.y())>p.w()||std::abs(p.z())>p.w())return false;}return true;
 };
 meshLayers[0]->setChecked(true);auto combined=overview->overviewCamera();
 structureButtons[0]->click();auto lung=overview->overviewRequest();auto visible=lung["layers"].toObject();
 check("lung_only_no_candidate_or_route",visible["lung"].toBool()&&!visible["airway"].toBool()&&!visible["nodule"].toBool()&&!routeCheck->isChecked());check("entire_lung_in_view",containsBounds("lung"));
 testDrag(overview,QPoint(150,170),QPoint(210,190));
 QWheelEvent wheel(QPointF(210,190),overview->mapToGlobal(QPoint(210,190)),QPoint(),QPoint(0,240),Qt::NoButton,Qt::NoModifier,Qt::NoScrollPhase,false);QApplication::sendEvent(overview,&wheel);
 auto beforePan=overview->overviewCamera();QMouseEvent down(QEvent::MouseButtonPress,QPoint(120,130),Qt::MiddleButton,Qt::MiddleButton,Qt::NoModifier),move(QEvent::MouseMove,QPoint(185,150),Qt::NoButton,Qt::MiddleButton,Qt::NoModifier),up(QEvent::MouseButtonRelease,QPoint(185,150),Qt::MiddleButton,Qt::NoButton,Qt::NoModifier);for(auto*e:{&down,&move,&up})QApplication::sendEvent(overview,e);
 auto saved=overview->overviewCamera();check("pan_moves_center_without_rotating",saved["center"]!=beforePan["center"]&&saved["yaw"]==beforePan["yaw"]&&saved["pitch"]==beforePan["pitch"]);check("wheel_uses_two_detents",std::abs(saved["zoom"].toDouble()-1.12*1.12)<1e-5);
 capture("structure_lung_only");structureButtons[1]->click();visible=overview->overviewRequest()["layers"].toObject();check("airway_only",!visible["lung"].toBool()&&visible["airway"].toBool()&&!visible["nodule"].toBool());check("entire_airway_in_view",containsBounds("airway"));
 capture("structure_airway_only");structureButtons[0]->click();check("lung_camera_restored",overview->overviewCamera()==saved);
 structureButtons[2]->click();check("combined_camera_restored",overview->overviewCamera()==combined);check("combined_layers_and_route_restored",meshLayers[0]->isChecked()&&meshLayers[1]->isChecked()&&meshLayers[2]->isChecked()&&routeCheck->isChecked());
 structureButtons[1]->click();focusButton->click();check("candidate_focus_checkbox_synchronized",meshLayers[2]->isChecked()&&overview->overviewRequest()["layers"].toObject()["nodule"].toBool());
 meshLayers[0]->setChecked(true);overview->resetView();check("all_visible_structures_fit",containsBounds("lung")&&containsBounds("airway")&&containsBounds("nodule"));capture("structure_all_fitted");
 QJsonObject invalid=overview->overviewCamera();invalid["zoom"]=0;auto prior=overview->overviewCamera();check("invalid_camera_rejected",!overview->restoreOverviewCamera(invalid)&&overview->overviewCamera()==prior);
 QJsonObject report{{"status",passed?"passed":"failed"},{"kind","actual_KV260_Qt_GLES_structure_interaction"},{"checks",checks},{"scene",scenePath},{"camera",overview->overviewCamera()},{"render",overview->metrics()},{"physical_mouse_verified",false},{"PL_composition_comparison","separate same-input acceptance"}};writeJson(evidence+"/structure_interaction.json",report);QApplication::exit(passed?0:1);
}
