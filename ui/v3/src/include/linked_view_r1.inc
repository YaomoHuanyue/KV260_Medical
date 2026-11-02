// Capture the linked overview at its own native size, independently of the
// HDMI widget layout. The route/frustum painter is the same as the live UI.
QImage MeshView::linkedOverviewColor(QSize dimensions,const QJsonObject&frame,QJsonObject&proof){
 if(scope||compositeEnabled||dimensions!=QSize(640,360)||!context()||!isValid()||!error.isEmpty())
  throw std::runtime_error("Linked overview is not ready for native capture");
 if(!setReferenceCamera(frame))throw std::runtime_error("Linked overview rejected completed camera");
 auto cameraBefore=overviewCamera();auto matrixBefore=lastMvp;
 makeCurrent();GLint previousFbo=0,previousViewport[4];
 glGetIntegerv(GL_FRAMEBUFFER_BINDING,&previousFbo);glGetIntegerv(GL_VIEWPORT,previousViewport);
 auto restore=[&]{lastMvp=matrixBefore;glBindFramebuffer(GL_FRAMEBUFFER,previousFbo);
  glViewport(previousViewport[0],previousViewport[1],previousViewport[2],previousViewport[3]);doneCurrent();};
 QImage image;int buildsBefore=normalShellGeometryBuilds;
 try{
  if(!linkedColor||linkedColor->size()!=dimensions)
   linkedColor=std::make_unique<QOpenGLFramebufferObject>(dimensions,QOpenGLFramebufferObject::CombinedDepthStencil);
  if(!linkedColor->isValid()||!linkedColor->bind())throw std::runtime_error("Cannot bind linked overview framebuffer");
  glViewport(0,0,dimensions.width(),dimensions.height());glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);
  glDepthMask(GL_TRUE);glStencilMask(0xff);glDisable(GL_STENCIL_TEST);glDisable(GL_BLEND);
  glDisable(GL_CULL_FACE);glEnable(GL_DEPTH_TEST);glDepthFunc(GL_LESS);
  glClearColor(.025f,.06f,.10f,1.f);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT|GL_STENCIL_BUFFER_BIT);
  QMatrix4x4 view,projection;
  view.lookAt(center+QVector3D(0,-radius*2.8f/zoom,0),center,QVector3D(0,0,1));
  view.translate(center);view.rotate(pitch,1,0,0);view.rotate(yaw,0,0,1);view.translate(-center);
  projection.perspective(42,float(dimensions.width())/dimensions.height(),.1f,radius*12.f);
  lastMvp=projection*view;drawNormalOverview(lastMvp,view,dimensions.width(),dimensions.height());
  image=linkedColor->toImage(true).convertToFormat(QImage::Format_RGBA8888);
  if(glGetError()!=GL_NO_ERROR||image.size()!=dimensions||!error.isEmpty())
   throw std::runtime_error("Linked overview native rendering failed");
  QPainter painter(&image);QFont font("Noto Sans CJK SC");font.setPixelSize(12);painter.setFont(font);
  paintOverlay(painter,dimensions);painter.end();
  proof=referenceCameraMetrics();proof["overview_camera"]=cameraBefore;
  QJsonArray mvp;for(int i=0;i<16;++i)mvp.append(lastMvp.constData()[i]);proof["mvp_column_major"]=mvp;
  proof["native_size"]=QJsonArray{dimensions.width(),dimensions.height()};
  proof["widget_size"]=QJsonArray{width(),height()};
  proof["renderer"]=renderer;proof["geometry_cache_builds_this_capture"]=normalShellGeometryBuilds-buildsBefore;
  proof["same_live_route_frustum_painter"]=true;proof["ordinary_opacity_renderer"]="accepted_R4_nearest_shell_cache";
  if(overviewCamera()!=cameraBefore)throw std::runtime_error("Linked capture changed the overview camera");
 }catch(...){restore();throw;}
 restore();return image;
}
