bool transparentFrameMatches(const QJsonObject&meta,const QJsonObject&state)const{
 auto c=meta["report"].toObject()["controls"].toObject();
 if(c["breathing"]!=state["breathing"])return false;
 if(meta["width"]!=state["width"]||meta["height"]!=state["height"])return false;
 for(const char*k:{"full_lung","layers","clipping","center_lps_mm"})if(c[k]!=state[k])return false;
 for(const char*k:{"yaw_degrees","pitch_degrees","zoom","radius_mm","color_mode","required_radius_mm","resolution_margin_mm"}){
  if(!c[k].isDouble()||!state[k].isDouble()||std::abs(c[k].toDouble()-state[k].toDouble())>1e-4)return false;
 }
 return c["lung_opacity_byte"].toInt(-1)==int(std::floor(state["lung_opacity"].toDouble()*255+.5));
}
void transparentTestFinish(bool passed,QString why){
 transparentTestCheck.stop();transparentTestMotion.stop();transparentMoving=false;compositeQuiet.stop();finishingTest=true;
 transparentTestReport["status"]=passed?"passed":"failed";transparentTestReport["detail"]=why;
 transparentTestReport["kind"]="actual_KV260_Qt_preview_and_unchanged_precise_PL_C7";
 transparentTestReport["scene"]=scenePath;transparentTestReport["preview_metrics"]=overview->compositePreviewMetrics();
 transparentTestReport["render_metrics"]=overview->metrics();transparentTestReport["stale_frames_rejected"]=previewStaleFrames;
 transparentTestReport["original_complete_geometry_unchanged"]=true;transparentTestReport["new_PL_core"]=false;
 transparentTestReport["physical_mouse_verified"]=false;transparentTestReport["exact_frames"]=compositeTrace;
 capture("transparent_interaction_final");writeJson(evidence+"/transparent_interaction_UI.json",transparentTestReport);
 releaseGraphics([this,passed]{QApplication::exit(passed?0:1);});
}
void transparentMotionAdvance(){
 if(!transparentMoving)return;
 int ms=transparentMotionClock.elapsed();QPoint p(200+int(65*std::sin(ms*.0014)),190+int(20*std::sin(ms*.0019)));
 QMouseEvent e(QEvent::MouseMove,p,Qt::NoButton,Qt::LeftButton,Qt::NoModifier);QApplication::sendEvent(overview,&e);++transparentMoves;
 if(ms<4000)return;
 QMouseEvent up(QEvent::MouseButtonRelease,p,Qt::LeftButton,Qt::NoButton,Qt::NoModifier);QApplication::sendEvent(overview,&up);
 transparentTestMotion.stop();transparentMoving=false;
 auto current=overview->overviewRequest();transparentTestReport["interactive_last_request"]=current;
 transparentTestReport["preview_swapped_times_ms"]=QJsonArray::fromVariantList([this]{QVariantList a;for(double x:transparentSwapTimes)a.append(x);return a;}());
 double fps=transparentSwapTimes.size()>1?1000.*(transparentSwapTimes.size()-1)/(transparentSwapTimes.last()-transparentSwapTimes.first()):0;
 transparentTestReport["actual_preview_update_fps"]=fps;transparentTestReport["mouse_move_events"]=transparentMoves;
 bool kept=overview->compositePreviewMode()&&current["full_lung"]==transparentBaselineRequest["full_lung"]&&current["layers"]==transparentBaselineRequest["layers"];
 bool coalesced=previewQuietRequests==transparentRequestBase;
 transparentTestReport["no_automatic_mesh_or_layer_reduction"]=kept;transparentTestReport["no_exact_request_during_continuous_mouse_motion"]=coalesced;
 if(!kept||!coalesced||transparentSwapTimes.size()<4||fps<=1./transparentBaselineMeta["round_trip_seconds"].toDouble()){
  transparentTestFinish(false,u("预览响应或连续交互请求合并未通过"));return;
 }
 capture("transparent_interaction_preview");
 auto original=transparentBaselineRequest;QJsonObject camera{{"center",original["center_lps_mm"]},{"radius",original["radius_mm"]},{"yaw",original["yaw_degrees"]},{"pitch",original["pitch_degrees"]},{"zoom",original["zoom"]}};
 transparentTestBase=compositeFrames;overview->restoreOverviewCamera(camera);transparentTestStage=2;transparentTestDeadline.restart();
}
void transparentTestAdvance(){
 if(transparentTestStage>=0&&transparentTestDeadline.elapsed()>120000){transparentTestFinish(false,u("精确透明完成帧等待超时"));return;}
 if(transparentTestStage==-1){
  tabs->setCurrentIndex(1);fastTransparency->setChecked(false);clipCheck->setChecked(false);colorMode->setCurrentIndex(0);
  structureButtons[2]->click();for(auto*p:meshLayers)p->setChecked(true);lungQuality->setCurrentIndex(1);overview->resetView();
  transparentTestBase=compositeFrames;preciseBlend->setChecked(true);transparentBaselineRequest=overview->overviewRequest();
  transparentTestStage=0;transparentTestDeadline.restart();return;
 }
 if(transparentTestStage==0){
  if(compositeFrames<=transparentTestBase||!transparentFrameMatches(overview->completedComposite(),transparentBaselineRequest))return;
  transparentBaselinePixels=transparentLastPixels;transparentBaselineMeta=overview->completedComposite();
  transparentTestReport["baseline_request"]=transparentBaselineRequest;transparentTestReport["baseline_exact_round_trip_seconds"]=transparentBaselineMeta["round_trip_seconds"];
  transparentTestReport["baseline_RGBA_sha256"]=QString(QCryptographicHash::hash(transparentBaselinePixels,QCryptographicHash::Sha256).toHex());
  auto invalid=transparentBaselineMeta;auto report=invalid["report"].toObject();auto controls=report["controls"].toObject();controls["yaw_degrees"]=controls["yaw_degrees"].toDouble()+1;report["controls"]=controls;invalid["report"]=report;
  if(transparentBaselinePixels.isEmpty()||!transparentFrameMatches(transparentBaselineMeta,transparentBaselineRequest)||transparentFrameMatches(invalid,transparentBaselineRequest)){
   transparentTestFinish(false,u("精确帧与当前控制状态绑定检查未通过"));return;
  }
  capture("transparent_interaction_baseline");
  fastTransparency->setChecked(true);transparentRequestBase=previewQuietRequests;transparentSwapBase=overview->compositePreviewMetrics()["swapped"].toInt();
  transparentSwapTimes.clear();transparentMoving=true;transparentMotionClock.restart();
  QMouseEvent down(QEvent::MouseButtonPress,QPoint(200,190),Qt::LeftButton,Qt::LeftButton,Qt::NoModifier);QApplication::sendEvent(overview,&down);
  transparentTestMotion.start(50);transparentTestStage=1;return;
 }
 if(transparentTestStage==2){
  if(compositeFrames<=transparentTestBase||!transparentFrameMatches(overview->completedComposite(),transparentBaselineRequest))return;
  bool same=transparentLastPixels==transparentBaselinePixels&&!overview->compositePreviewMode();
  transparentTestReport["settled_RGBA_sha256"]=QString(QCryptographicHash::hash(transparentLastPixels,QCryptographicHash::Sha256).toHex());
  transparentTestReport["settled_pixels_equal_exact_only_baseline"]=same;
  transparentTestReport["settled_round_trip_seconds"]=overview->completedComposite()["round_trip_seconds"];
  transparentTestReport["quiet_requests"]=previewQuietRequests-transparentRequestBase;
  transparentTestFinish(same&&previewQuietRequests>transparentRequestBase,u("连续拖动预览与停止后完整精确帧已实测"));
 }
}
