// Cache the opaque background and the nearest opaque scene. Their RGB mix is
// exactly the nearest-shell transparency approximation, without a second lung
// geometry pass. Opacity alone changes only this full-screen GPU composition.
void MeshView::drawNormalOverview(const QMatrix4x4&mvp,const QMatrix4x4&view,int w,int h){
 if(!meshes[0].visible||meshes[0].count==0||lungOpacity<=0.f||lungOpacity>=1.f){drawMeshes(mvp,view);return;}
 GLint framebuffer=0,viewport[4];glGetIntegerv(GL_FRAMEBUFFER_BINDING,&framebuffer);glGetIntegerv(GL_VIEWPORT,viewport);
 auto restore=[&]{glBindFramebuffer(GL_FRAMEBUFFER,framebuffer);glViewport(viewport[0],viewport[1],viewport[2],viewport[3]);};
 if(!normalShellShader.isLinked()){
  const char*vs="attribute vec2 position;varying mediump vec2 uv;void main(){uv=position*.5+.5;gl_Position=vec4(position,0.,1.);}";
  const char*fs="precision mediump float;varying mediump vec2 uv;uniform sampler2D background,nearest;uniform float alpha;void main(){gl_FragColor=vec4(mix(texture2D(background,uv).rgb,texture2D(nearest,uv).rgb,alpha),1.);}";
  if(!normalShellShader.addShaderFromSourceCode(QOpenGLShader::Vertex,vs)||!normalShellShader.addShaderFromSourceCode(QOpenGLShader::Fragment,fs)||!normalShellShader.link()){
   error=normalShellShader.log();restore();drawMeshes(mvp,view);return;
  }
 }
 if(!normalBackground||normalBackground->size()!=QSize(w,h)){
  normalBackground=std::make_unique<QOpenGLFramebufferObject>(QSize(w,h),QOpenGLFramebufferObject::CombinedDepthStencil);
  normalNearest=std::make_unique<QOpenGLFramebufferObject>(QSize(w,h),QOpenGLFramebufferObject::CombinedDepthStencil);
  normalShellKey.clear();
  if(!normalBackground->isValid()||!normalNearest->isValid()){error="Cannot allocate nearest-shell color cache";restore();drawMeshes(mvp,view);return;}
  for(auto*p:{normalBackground.get(),normalNearest.get()}){
   glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,p->texture());
   glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
   glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
  }
 }
 auto state=overviewRequest();state.remove("lung_opacity");state["native_width"]=w;state["native_height"]=h;
 QJsonArray geometry;for(const auto&m:meshes)geometry.append(QJsonObject{{"file",m.file},{"attributes",m.attributes},{"vertices",m.count},{"visible",m.visible}});state["geometry"]=geometry;
 QByteArray key=QJsonDocument(state).toJson(QJsonDocument::Compact)+QByteArray(reinterpret_cast<const char*>(mvp.constData()),16*sizeof(float));
 if(key!=normalShellKey){
  auto begin=[&](QOpenGLFramebufferObject*p){p->bind();glViewport(0,0,w,h);glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);glDepthMask(GL_TRUE);glStencilMask(0xff);glDisable(GL_STENCIL_TEST);glDisable(GL_BLEND);glDisable(GL_CULL_FACE);glEnable(GL_DEPTH_TEST);glDepthFunc(GL_LESS);glClearColor(.025f,.06f,.10f,1.f);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT|GL_STENCIL_BUFFER_BIT);};
  float alpha=lungOpacity;bool visible=meshes[0].visible;
  begin(normalBackground.get());meshes[0].visible=false;drawMeshes(mvp,view);meshes[0].visible=visible;
  begin(normalNearest.get());lungOpacity=1.f;drawMeshes(mvp,view);lungOpacity=alpha;
  normalShellKey=key;++normalShellGeometryBuilds;
 }
 restore();glDisable(GL_DEPTH_TEST);glDepthMask(GL_FALSE);glDisable(GL_STENCIL_TEST);glDisable(GL_BLEND);
 normalShellShader.bind();normalShellShader.setUniformValue("background",0);normalShellShader.setUniformValue("nearest",1);normalShellShader.setUniformValue("alpha",lungOpacity);
 glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,normalBackground->texture());glActiveTexture(GL_TEXTURE1);glBindTexture(GL_TEXTURE_2D,normalNearest->texture());
 const float xy[]={-1,-1,1,-1,-1,1,-1,1,1,-1,1,1};int attr=normalShellShader.attributeLocation("position");
 glBindBuffer(GL_ARRAY_BUFFER,0);glEnableVertexAttribArray(attr);glVertexAttribPointer(attr,2,GL_FLOAT,GL_FALSE,0,xy);glDrawArrays(GL_TRIANGLES,0,6);glDisableVertexAttribArray(attr);normalShellShader.release();
 glBindTexture(GL_TEXTURE_2D,0);glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,0);glDepthMask(GL_TRUE);glEnable(GL_DEPTH_TEST);glDepthFunc(GL_LESS);++normalShellCompositions;
}
