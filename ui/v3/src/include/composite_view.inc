QJsonObject MeshView::overviewRequest()const{
 auto arr=[](QVector3D v){return QJsonArray{v.x(),v.y(),v.z()};};
 int w=qBound(16,(width()/16)*16,640),h=qBound(4,int(double(height())*w/qMax(1,width())),512);
 return {{"width",w},{"height",h},{"yaw_degrees",yaw},{"pitch_degrees",pitch},{"zoom",zoom},
 {"center_lps_mm",arr(center)},{"radius_mm",radius},{"full_lung",meshes[0].file==lungFullFile},
 {"layers",QJsonObject{{"lung",meshes[0].visible},{"airway",meshes[1].visible},{"nodule",meshes[2].visible}}},
 {"breathing",QJsonObject{{"enabled",false},{"phase_radians",0.}}},{"lung_opacity",lungOpacity},{"color_mode",colorMode},{"required_radius_mm",requiredRadius},{"resolution_margin_mm",resolutionMargin},
 {"clipping",QJsonObject{{"enabled",clipEnabled},{"axis",clipAxis},{"value_mm",originalCenter[clipAxis]+clipFraction*originalRadius}}}};
}
QRectF MeshView::compositeRect()const{
 if(compositeFrame.isNull())return rect();qreal d=devicePixelRatioF();QSize fit=compositeFrame.size();
 fit.scale(qRound(width()*d),qRound(height()*d),Qt::KeepAspectRatio);
 int x=(qRound(width()*d)-fit.width())/2,y=(qRound(height()*d)-fit.height())/2;
 return QRectF(x/d,(qRound(height()*d)-y-fit.height())/d,fit.width()/d,fit.height()/d);
}
bool MeshView::setCompositeFrame(QImage image,QJsonObject info){
 auto report=info["report"].toObject();auto vm=report["view_column_major"].toArray(),pm=report["projection_column_major"].toArray();
 if(vm.size()!=16||pm.size()!=16||image.isNull()||image.width()!=info["width"].toInt()||image.height()!=info["height"].toInt())return false;
 QMatrix4x4 v,p;for(int i=0;i<16;++i){if(!vm[i].isDouble()||!pm[i].isDouble()||!std::isfinite(vm[i].toDouble())||!std::isfinite(pm[i].toDouble()))return false;v.data()[i]=vm[i].toDouble();p.data()[i]=pm[i].toDouble();}
 lastMvp=p*v;compositeFrame=std::move(image);compositeInfo=std::move(info);compositeDirty=true;compositeStatus.clear();refresh();return true;
}
bool MeshView::projectOverview(QVector3D v,QPointF&out)const{
 if(compositeEnabled&&!compositePreview&&compositeFrame.isNull())return false;QVector4D c=lastMvp*QVector4D(v,1);
 if(c.w()<=0||c.z() < -c.w()||c.z()>c.w())return false;
 auto box=compositeEnabled&&!compositePreview?compositeRect():QRectF(rect());out={box.x()+(c.x()/c.w()+1)*box.width()/2,box.y()+(1-c.y()/c.w())*box.height()/2};return true;
}
QPointF MeshView::candidateScreenPoint(int index)const{for(auto value:candidates){auto c=value.toObject();if(c["index"].toInt()==index){QPointF p;if(projectOverview(displayPoint(vec(c["centroid_lps_mm"]),2),p))return p;}}return {-1,-1};}
bool MeshView::drawComposite(int vw,int vh){
 if(compositeFrame.isNull())return true;
 if(!compositeShader.isLinked()){
  // Worker files contain GLES bottom-left rows, unlike the C6 top-down image.
  const char*vs="attribute vec2 pos;varying mediump vec2 uv;void main(){uv=(pos+1.0)*.5;gl_Position=vec4(pos,0.,1.);}";
  const char*fs="precision mediump float;varying mediump vec2 uv;uniform sampler2D colorFrame;void main(){gl_FragColor=texture2D(colorFrame,uv);}";
  if(!compositeShader.addShaderFromSourceCode(QOpenGLShader::Vertex,vs)||!compositeShader.addShaderFromSourceCode(QOpenGLShader::Fragment,fs)||!compositeShader.link()){error=compositeShader.log();return false;}
 }
 glDisable(GL_DEPTH_TEST);glDisable(GL_BLEND);glActiveTexture(GL_TEXTURE0);
 if(!compositeTexture)glGenTextures(1,&compositeTexture);glBindTexture(GL_TEXTURE_2D,compositeTexture);
 if(compositeDirty){glPixelStorei(GL_UNPACK_ALIGNMENT,1);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
  glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,compositeFrame.width(),compositeFrame.height(),0,GL_RGBA,GL_UNSIGNED_BYTE,compositeFrame.constBits());compositeDirty=false;}
 QSize fit=compositeFrame.size();fit.scale(vw,vh,Qt::KeepAspectRatio);glViewport((vw-fit.width())/2,(vh-fit.height())/2,fit.width(),fit.height());
 const GLfloat xy[]={-1,-1,1,-1,-1,1,-1,1,1,-1,1,1};compositeShader.bind();compositeShader.setUniformValue("colorFrame",0);
 int a=compositeShader.attributeLocation("pos");glBindBuffer(GL_ARRAY_BUFFER,0);glEnableVertexAttribArray(a);glVertexAttribPointer(a,2,GL_FLOAT,GL_FALSE,0,xy);glDrawArrays(GL_TRIANGLES,0,6);glDisableVertexAttribArray(a);compositeShader.release();glBindTexture(GL_TEXTURE_2D,0);glViewport(0,0,vw,vh);
 GLenum e=glGetError();if(e!=GL_NO_ERROR){error=QString("Composite blit GL error %1").arg(e);return false;}return true;
}
