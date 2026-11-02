#include <cstring>
// Regression: real CT triangles in forward/reversed submission order, plus
// the independently established opaque airway draw path as endpoint oracle.
QJsonObject MeshView::fastOpacityRegression(const QString&directory){
 makeCurrent();QDir().mkpath(directory);GLint widgetStencil=0;glGetIntegerv(GL_STENCIL_BITS,&widgetStencil);
 auto oldCamera=overviewCamera();float oldAlpha=lungOpacity;bool oldClip=clipEnabled;int oldAxis=clipAxis;float oldFraction=clipFraction;
 bool oldComposite=compositeEnabled,oldPreview=compositePreview;compositeEnabled=compositePreview=false;
 Mesh originals[3];for(int k=0;k<3;++k)originals[k]=meshes[k];
 QJsonArray cases;bool passed=true;int reproduced=0;GLint stencil=0;
 QOpenGLFramebufferObject target(QSize(512,384),QOpenGLFramebufferObject::CombinedDepthStencil);
 if(!target.isValid())throw std::runtime_error("Opacity regression framebuffer unavailable");
 auto render=[&](bool oracle=false){
  target.bind();glViewport(0,0,512,384);glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);glDepthMask(GL_TRUE);glStencilMask(0xff);
  glDisable(GL_STENCIL_TEST);glDisable(GL_BLEND);glDisable(GL_CULL_FACE);glEnable(GL_DEPTH_TEST);glDepthFunc(GL_LESS);
  glClearColor(.025f,.06f,.10f,1.f);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT|GL_STENCIL_BUFFER_BIT);
  glGetIntegerv(GL_STENCIL_BITS,&stencil);
  QMatrix4x4 v,p;v.lookAt(center+QVector3D(0,-radius*2.8f/zoom,0),center,QVector3D(0,0,1));v.translate(center);v.rotate(pitch,1,0,0);v.rotate(yaw,0,0,1);v.translate(-center);p.perspective(42,512.f/384,.1f,radius*12.f);
  auto start=std::chrono::steady_clock::now();
  if(oracle){
   Mesh saved[3];for(int k=0;k<3;++k)saved[k]=meshes[k];
   // Render lung through the pre-existing opaque shader/depth branch (slot 1),
   // after airway/lesions. No transparency fix is used.
   // Match the application's airway/lesion-before-lung tie priority.
   meshes[0].visible=false;drawMeshes(p*v,v);
   for(int k=0;k<3;++k)meshes[k]=saved[k];
   meshes[1]=saved[0];meshes[1].attributes.clear();meshes[1].attributeVbo=0;
   meshes[0].visible=meshes[2].visible=false;drawMeshes(p*v,v);
   for(int k=0;k<3;++k)meshes[k]=saved[k];
  }else{normalShellKey.clear();drawNormalOverview(p*v,v,512,384);}
  glFinish();double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
  GLenum err=glGetError();if(err!=GL_NO_ERROR)throw std::runtime_error("Opacity regression GL error");
  QImage image=target.toImage().convertToFormat(QImage::Format_RGBA8888);return std::make_pair(image,seconds);
 };
 auto difference=[](const QImage&a,const QImage&b,int threshold){int pixels=0,maximum=0;for(int y=0;y<a.height();++y){auto x=a.constScanLine(y),z=b.constScanLine(y);for(int i=0;i<a.width();++i){int d=0;for(int c=0;c<3;++c)d=qMax(d,std::abs(int(x[4*i+c])-int(z[4*i+c])));maximum=qMax(maximum,d);if(d>threshold)++pixels;}}return std::make_pair(pixels,maximum);};
 for(int detail=0;detail<2;++detail){
  auto&m=meshes[0];if(m.vbo)glDeleteBuffers(1,&m.vbo);m.vbo=0;m.file=detail?lungFullFile:lungPreviewFile;m.count=detail?lungFullCount:lungPreviewCount;
  for(auto&mesh:meshes)mesh.visible=true;lungOpacity=1;render();GLuint forward=meshes[0].vbo;
  QFile file(m.file);if(!file.open(QIODevice::ReadOnly))throw std::runtime_error("Regression mesh unreadable");auto data=file.readAll();file.close();
  if(data.size()!=qint64(m.count)*24||m.count%3)throw std::runtime_error("Regression mesh size");
  char temporary[72];for(qint64 a=0,b=data.size()-72;a<b;a+=72,b-=72){std::memcpy(temporary,data.constData()+a,72);std::memcpy(data.data()+a,data.constData()+b,72);std::memcpy(data.data()+b,temporary,72);}
  GLuint reverse=0;glGenBuffers(1,&reverse);glBindBuffer(GL_ARRAY_BUFFER,reverse);glBufferData(GL_ARRAY_BUFFER,data.size(),data.constData(),GL_STATIC_DRAW);data.clear();glBindBuffer(GL_ARRAY_BUFFER,0);
  for(int pose=0;pose<4;++pose){
   center=vec(oldCamera["center"]);radius=oldCamera["radius"].toDouble();yaw=pose==0?0:pose==1?45:160;pitch=pose==0?0:pose==1?20:-20;zoom=pose==0?1:pose==1?2:3.3;
   clipEnabled=pose==3;clipAxis=2;clipFraction=0;meshes[0].vbo=forward;
   lungOpacity=1;auto opaque=render(true).first;
   meshes[0].visible=false;auto background=render().first;meshes[0].visible=true;
   for(float alpha:{0.f,.2f,.5f,.9f,.99f,1.f}){
    lungOpacity=alpha;meshes[0].vbo=forward;auto a=render();meshes[0].vbo=reverse;auto b=render();meshes[0].vbo=forward;
    auto order=difference(a.first,b.first,3);QImage expected=background.copy();
    for(int y=0;y<expected.height();++y){auto dst=expected.scanLine(y);auto fg=opaque.constScanLine(y),bg=background.constScanLine(y);for(int x=0;x<expected.width();++x)for(int c=0;c<3;++c)dst[x*4+c]=qBound(0,int(std::floor(alpha*fg[x*4+c]+(1-alpha)*bg[x*4+c]+.5f)),255);}
    auto formula=difference(a.first,expected,3);int total=a.first.width()*a.first.height();
    bool opaqueCanvas=true;for(int y=0;y<a.first.height();++y){auto p=a.first.constScanLine(y);for(int x=0;x<a.first.width();++x)opaqueCanvas=opaqueCanvas&&p[4*x+3]==255;}
    bool good=opaqueCanvas&&stencil>=8&&widgetStencil>=8&&order.first<=total*.002&&formula.first<=total*.002;
    if(alpha==1.f)good=good&&formula.first==0;
    if(alpha==0.f)good=good&&difference(a.first,background,0).first==0;
    passed=passed&&good;if(!good)++reproduced;
    QString name=QString("detail_%1_pose_%2_alpha_%3").arg(detail).arg(pose).arg(qRound(alpha*100));
    if(alpha==1.f||alpha==.99f){a.first.save(directory+"/"+name+".png");if(alpha==1.f)opaque.save(directory+"/"+name+"_opaque_oracle.png");}
    cases.append(QJsonObject{{"name",name},{"full_lung",bool(detail)},{"lung_vertices",m.count},{"zoom",zoom},{"clip_enabled",clipEnabled},{"alpha",alpha},{"order_difference_pixels_gt3",order.first},{"order_maximum_byte_difference",order.second},{"opaque_formula_difference_pixels_gt3",formula.first},{"opaque_formula_maximum_byte_difference",formula.second},{"GPU_completed_draw_seconds",a.second},{"reversed_GPU_completed_draw_seconds",b.second},{"framebuffer_alpha_preserved",opaqueCanvas},{"passed",good}});
   }
  }
  glDeleteBuffers(1,&reverse);meshes[0].vbo=forward;
 }
 // Opacity changes reuse geometry; a changed camera must invalidate it.
 normalShellKey.clear();clipEnabled=false;lungOpacity=.2f;render();int firstBuild=normalShellGeometryBuilds;
 QJsonArray cachedOpacity;bool cachePassed=true;
 for(float alpha:{.4f,.9f,.99f,.2f}){
  lungOpacity=alpha;target.bind();glViewport(0,0,512,384);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT|GL_STENCIL_BUFFER_BIT);
  QMatrix4x4 v,p;v.lookAt(center+QVector3D(0,-radius*2.8f/zoom,0),center,QVector3D(0,0,1));v.translate(center);v.rotate(pitch,1,0,0);v.rotate(yaw,0,0,1);v.translate(-center);p.perspective(42,512.f/384,.1f,radius*12.f);
  auto start=std::chrono::steady_clock::now();drawNormalOverview(p*v,v,512,384);glFinish();auto cached=target.toImage().convertToFormat(QImage::Format_RGBA8888);double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
  bool reused=normalShellGeometryBuilds==firstBuild;auto cold=render().first;auto diff=difference(cached,cold,0);
  bool good=reused&&diff.first==0;cachePassed=cachePassed&&good;firstBuild=normalShellGeometryBuilds;
  cachedOpacity.append(QJsonObject{{"alpha",alpha},{"geometry_reused",reused},{"cached_vs_cold_pixel_difference",diff.first},{"GPU_completed_seconds",seconds},{"passed",good}});
 }
 int beforePose=normalShellGeometryBuilds;yaw+=1;target.bind();glViewport(0,0,512,384);
 QMatrix4x4 changedView,changedProjection;changedView.lookAt(center+QVector3D(0,-radius*2.8f/zoom,0),center,QVector3D(0,0,1));changedView.translate(center);changedView.rotate(pitch,1,0,0);changedView.rotate(yaw,0,0,1);changedView.translate(-center);changedProjection.perspective(42,512.f/384,.1f,radius*12.f);
 drawNormalOverview(changedProjection*changedView,changedView,512,384);glFinish();bool cameraInvalidates=normalShellGeometryBuilds>beforePose;passed=passed&&cachePassed&&cameraInvalidates;
 // Original disk meshes are never edited; release temporary VBOs and restore UI.
 if(meshes[0].vbo)glDeleteBuffers(1,&meshes[0].vbo);
 for(int k=0;k<3;++k){if(k==0){originals[k].vbo=0;}else{originals[k].vbo=meshes[k].vbo;originals[k].attributeVbo=meshes[k].attributeVbo;}meshes[k]=originals[k];}
 center=vec(oldCamera["center"]);radius=oldCamera["radius"].toDouble();yaw=oldCamera["yaw"].toDouble();pitch=oldCamera["pitch"].toDouble();zoom=oldCamera["zoom"].toDouble();
 lungOpacity=oldAlpha;clipEnabled=oldClip;clipAxis=oldAxis;clipFraction=oldFraction;compositeEnabled=oldComposite;compositePreview=oldPreview;
 glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);glDepthMask(GL_TRUE);glDepthFunc(GL_LESS);glDisable(GL_STENCIL_TEST);glDisable(GL_BLEND);
 glBindFramebuffer(GL_FRAMEBUFFER,defaultFramebufferObject());doneCurrent();refresh();
 return {{"status",passed?"passed":"failed"},{"cases",cases},{"opacity_cache_checks",cachedOpacity},{"opacity_cache_passed",cachePassed},{"camera_invalidates_cache",cameraInvalidates},{"nearest_shell_geometry_builds",normalShellGeometryBuilds},{"failed_cases",reproduced},{"stencil_bits",stencil},{"widget_stencil_bits",widgetStencil},{"real_CT_meshes_used",true},{"independent_opaque_depth_oracle",true},{"precise_PL_worker_used",false},{"disk_geometry_changed",false},{"renderer",renderer}};
}
