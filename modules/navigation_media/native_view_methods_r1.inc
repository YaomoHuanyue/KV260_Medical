QJsonObject MeshView::scopeViewState()const{
 return {{"distance_mm",cameraDistance},{"manual_yaw_degrees",scopeYaw},{"manual_pitch_degrees",scopePitch},{"auto_align",autoAlign}};
}
bool MeshView::restoreScopeViewState(const QJsonObject&state){
 if(!scope||arcs.isEmpty())return false;
 for(const char*key:{"distance_mm","manual_yaw_degrees","manual_pitch_degrees"})if(!state[key].isDouble()||!std::isfinite(state[key].toDouble()))return false;
 float at=state["distance_mm"].toDouble(),pitchValue=state["manual_pitch_degrees"].toDouble();
 if(at<arcs.first()||at>arcs.last()||std::abs(pitchValue)>75)return false;
 alignTimer.stop();refineTimer.stop();motionClock.invalidate();dragging=false;playback=false;
 cameraDistance=at;cameraIndex=cameraForDistance(at);scopeYaw=state["manual_yaw_degrees"].toDouble();scopePitch=pitchValue;autoAlign=state["auto_align"].toBool();
 refresh();notifyPose(false);return true;
}
QImage MeshView::completedScopeColor(){
 if(!scope||!context()||!isValid()||!scopeColor||plDirty||scopeColor->size()!=QSize(640,360)||
    presentedPlInfo["sequence"]!=plInfo["sequence"]||paintedPlSequence!=swappedPlSequence)
  throw std::runtime_error("Native color framebuffer is not paired with the presented PL frame");
 makeCurrent();GLint previousFbo;glGetIntegerv(GL_FRAMEBUFFER_BINDING,&previousFbo);
 QImage image=scopeColor->toImage(true);glBindFramebuffer(GL_FRAMEBUFFER,previousFbo);auto err=glGetError();doneCurrent();
 if(image.size()!=QSize(640,360)||err!=GL_NO_ERROR)throw std::runtime_error("Native color framebuffer readback failed");
 return image.convertToFormat(QImage::Format_RGBA8888);
}
