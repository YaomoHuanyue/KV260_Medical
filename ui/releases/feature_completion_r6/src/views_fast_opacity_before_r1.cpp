#include "views_fast_opacity_r1.hpp"
#include <algorithm>
#include <cmath>
#include <chrono>
#include <stdexcept>
#include <sys/mman.h>
#include <sys/resource.h>

static QVector3D vec(const QJsonValue&v){auto a=v.toArray();return {float(a[0].toDouble()),float(a[1].toDouble()),float(a[2].toDouble())};}
static void require(bool ok,const char*message){if(!ok)throw std::runtime_error(message);}
Volume::~Volume(){if(data){if(ctLocked)munlock(data,ctFile.size());ctFile.unmap(reinterpret_cast<uchar*>(const_cast<float*>(data)));}if(masks){if(maskLocked)munlock(masks,maskFile.size());maskFile.unmap(const_cast<uchar*>(masks));}}
void Volume::load(const QString&scenePath,const QJsonObject&meta){
 path=scenePath;auto g=meta["geometry"].toObject();auto size=g["size_xyz"].toArray();auto sp=g["spacing_xyz"].toArray();auto d=g["direction"].toArray();
 for(int i=0;i<3;++i){dims[i]=size[i].toInt();spacing[i]=sp[i].toDouble();require(dims[i]>0&&spacing[i]>0,"Invalid CT geometry");}
 for(int i=0;i<9;++i)direction(i/3,i%3)=d[i].toDouble();origin=vec(g["origin_lps_mm"]);
 qint64 vox=qint64(dims[0])*dims[1]*dims[2];require(vox<=256LL*1024*1024,"CT too large");
 QDir root=QFileInfo(scenePath).dir();ctFile.setFileName(root.filePath(meta["volume"].toString()));
 require(ctFile.open(QIODevice::ReadOnly)&&ctFile.size()==vox*4,"CT cache truncated");data=reinterpret_cast<const float*>(ctFile.map(0,ctFile.size()));require(data,"Cannot map CT cache");
 if(meta["masks"].isString()){
  maskFile.setFileName(root.filePath(meta["masks"].toString()));require(maskFile.open(QIODevice::ReadOnly)&&maskFile.size()==vox,"Mask cache truncated");masks=maskFile.map(0,vox);require(masks,"Cannot map masks");
 }
 // Keep active slice pages resident during large CT reads/writes. This costs
 // no second volume copy, and prevents GUI-thread SD-card page faults.
 struct rlimit limit{};if(getrlimit(RLIMIT_MEMLOCK,&limit)==0){limit.rlim_cur=768ULL*1024*1024;if(limit.rlim_max<limit.rlim_cur)limit.rlim_max=limit.rlim_cur;setrlimit(RLIMIT_MEMLOCK,&limit);}
 ctLocked=mlock(data,ctFile.size())==0;if(masks)maskLocked=mlock(masks,maskFile.size())==0;
 qInfo()<<"CT/mask resident pages:"<<ctLocked<<maskLocked;
}
QVector3D Volume::physical(int x,int y,int z)const{float p[3]={x*spacing[0],y*spacing[1],z*spacing[2]};QVector3D out=origin;for(int i=0;i<3;++i)for(int j=0;j<3;++j)out[i]+=direction(i,j)*p[j];return out;}
SliceView::SliceView(int plane,QString title,QWidget*parent):QWidget(parent),axis(plane),planeTitle(title){setMinimumSize(150,130);setMouseTracking(true);}
void SliceView::setVolume(std::shared_ptr<Volume> v){volume=v;slice=v->dims[axis]/2;rebuild();}
void SliceView::setSlice(int value){if(!volume)return;slice=qBound(0,value,volume->dims[axis]-1);rebuild();}
void SliceView::windowLevel(float c,float w){center=c;widthHU=qMax(1.f,w);rebuild();}
void SliceView::setMask(bool enabled){showMask=enabled;rebuild();}
bool SliceView::setAirwayMask(int bit){if(bit!=2&&bit!=8&&bit!=16&&bit!=32&&bit!=64&&bit!=128)return false;airwayBit=bit;rebuild();return true;}
void SliceView::rebuild(){
 if(!volume)return;int a=axis==0?1:0,b=axis==2?1:2;int w=volume->dims[a],h=volume->dims[b];image=QImage(w,h,QImage::Format_RGB32);
 for(int j=0;j<h;++j){auto*out=reinterpret_cast<QRgb*>(image.scanLine(j));for(int i=0;i<w;++i){int p[3]={0,0,0};p[axis]=slice;p[a]=i;p[b]=axis==2?j:h-1-j;
  auto k=volume->index(p[0],p[1],p[2]);int g=qBound(0,int((volume->data[k]-(center-widthHU/2))*255/widthHU),255);int r=g,gr=g,bl=g;
  uchar all=showMask&&volume->masks?volume->masks[k]:0;uchar mask=(all&5)|((all&(airwayBit==64?2:airwayBit))?2:0);bool review=airwayBit==64&&(all&64);QColor c;if(review)c=QColor(255,220,70);else if(mask&4)c=QColor(255,103,97);else if(mask&2)c=QColor(70,227,210);else if(mask&1)c=QColor(96,153,235);
  if(mask||review){r=(r*55+c.red()*45)/100;gr=(gr*55+c.green()*45)/100;bl=(bl*55+c.blue()*45)/100;}out[i]=qRgb(r,gr,bl);
 }}update();
}
void SliceView::paintEvent(QPaintEvent*){
 QPainter p(this);p.fillRect(rect(),QColor("#07121e"));p.setRenderHint(QPainter::SmoothPixmapTransform);
 if(!image.isNull()){
  int a=axis==0?1:0,b=axis==2?1:2;QSizeF physical(image.width()*volume->spacing[a],image.height()*volume->spacing[b]);
  QRectF box=QRectF(rect()).adjusted(8,34,-8,-25);physical.scale(box.size(),Qt::KeepAspectRatio);imageRect=QRectF(box.center()-QPointF(physical.width()/2,physical.height()/2),physical);
  p.drawImage(imageRect,image);
 }else{p.setPen(QColor("#63768b"));p.drawText(rect(),Qt::AlignCenter,QString::fromUtf8("正在准备影像"));}
 p.setPen(QColor("#e3edf9"));p.drawText(12,23,planeTitle);p.setPen(QColor("#7f94ac"));
 if(volume)p.drawText(12,height()-8,QString("%1 / %2  ·  %3 mm").arg(slice+1).arg(volume->dims[axis]).arg(slice*volume->spacing[axis],0,'f',1));
 p.setPen(QColor("#20374d"));p.drawRect(rect().adjusted(0,0,-1,-1));
}
void SliceView::wheelEvent(QWheelEvent*e){if(!volume)return;setSlice(slice+(e->angleDelta().y()>0?1:-1));if(onSlice)onSlice(slice);e->accept();}
void SliceView::mousePressEvent(QMouseEvent*e){
 if(!volume||!imageRect.contains(e->localPos()))return;int a=axis==0?1:0,b=axis==2?1:2;int p[3]={0,0,0};p[axis]=slice;
 p[a]=qBound(0,int((e->x()-imageRect.x())/imageRect.width()*volume->dims[a]),volume->dims[a]-1);
 int j=qBound(0,int((e->y()-imageRect.y())/imageRect.height()*volume->dims[b]),volume->dims[b]-1);p[b]=axis==2?j:volume->dims[b]-1-j;
 auto pos=volume->physical(p[0],p[1],p[2]);if(onPosition)onPosition(QString("LPS %1, %2, %3 mm   |   HU %4").arg(pos.x(),0,'f',1).arg(pos.y(),0,'f',1).arg(pos.z(),0,'f',1).arg(volume->data[volume->index(p[0],p[1],p[2])],0,'f',0));
}

class MeshOverlay : public QWidget {
 MeshView *owner;
protected:
 void paintEvent(QPaintEvent*)override{QPainter p(this);owner->paintOverlay(p);}
public:
 explicit MeshOverlay(MeshView*v):QWidget(v),owner(v){setObjectName("meshOverlay");setAttribute(Qt::WA_TransparentForMouseEvents);setAttribute(Qt::WA_NoSystemBackground);setStyleSheet("QWidget#meshOverlay{background:transparent;}");}
};

MeshView::MeshView(QWidget*parent):QOpenGLWidget(parent){
 overlay=new MeshOverlay(this);overlay->show();setMinimumSize(170,150);setMouseTracking(true);meshes[1].visible=meshes[2].visible=true;
 connect(this,&QOpenGLWidget::frameSwapped,this,[this]{if(lastPaintPreview)++previewSwaps;if(paintedPlSequence&&paintedPlSequence!=swappedPlSequence){swappedPlSequence=paintedPlSequence;presentedPlInfo=paintedPlInfo;if(onPlPresented)onPlPresented(swappedPlSequence);}});
 refineTimer.setSingleShot(true);refineTimer.setTimerType(Qt::PreciseTimer);
 connect(&refineTimer,&QTimer::timeout,this,[this]{
  if(!scope||dragging||playback||alignTimer.isActive())return;
  // Coarse timers can fire before the camera's 250 ms motion window ends.
  // Guard even with PreciseTimer so the one quiet request is always refined.
  if(motionClock.isValid()&&motionClock.elapsed()<260){refineTimer.start(260-int(motionClock.elapsed()));return;}
  if(onPoseChanged)onPoseChanged();
 });
 connect(&alignTimer,&QTimer::timeout,this,[this]{
  float t=qMin(1.f,alignClock.elapsed()/alignDuration),blend=t*t*t*(10+t*(-15+6*t));
  scopeYaw=alignYaw*(1-blend);scopePitch=alignPitch*(1-blend);
  if(t>=1){scopeYaw=scopePitch=0;alignTimer.stop();}
  refresh();notifyPose(true);
 });
}
void MeshView::notifyPose(bool moving){if(!scope){if(onOverviewChanged)onOverviewChanged();return;}if(moving){motionClock.restart();refineTimer.start(260);}if(onPoseChanged)onPoseChanged();}
void MeshView::beginAutoAlign(){if(!autoAlign||dragging||alignTimer.isActive()||std::abs(scopeYaw)+std::abs(scopePitch)<.01f)return;alignYaw=scopeYaw;alignPitch=scopePitch;alignDuration=qMax(800.f,qMax(std::abs(alignYaw),std::abs(alignPitch))*1875.f/45.f);alignClock.restart();alignTimer.start(16);}
void MeshView::setAutoAlign(bool enabled){autoAlign=enabled;if(enabled)beginAutoAlign();else alignTimer.stop();notifyPose(true);}
void MeshView::setPlayback(bool enabled){playback=enabled;if(enabled)beginAutoAlign();notifyPose(true);}
MeshView::~MeshView(){if(context()){makeCurrent();scopeColor.reset();for(auto&m:meshes){if(m.vbo)glDeleteBuffers(1,&m.vbo);if(m.attributeVbo)glDeleteBuffers(1,&m.attributeVbo);}if(compositeTexture)glDeleteTextures(1,&compositeTexture);compositeShader.removeAllShaders();if(scopeTexture)glDeleteTextures(1,&scopeTexture);if(normalTexture)glDeleteTextures(1,&normalTexture);scopeBlitShader.removeAllShaders();scopeShader.removeAllShaders();shader.removeAllShaders();doneCurrent();}}
void MeshView::initializeGL(){
 initializeOpenGLFunctions();renderer=QString::fromLatin1(reinterpret_cast<const char*>(glGetString(GL_RENDERER)));
 if(onBackend)onBackend(renderer);qInfo().noquote()<<"GPU renderer:"<<renderer;
 const char*vs="attribute highp vec3 position;attribute highp vec3 normal;attribute mediump vec4 analysis;uniform highp mat4 mvp;uniform highp mat3 normalMatrix;varying mediump vec3 n;varying highp vec3 world;varying mediump vec4 a;void main(){gl_Position=mvp*vec4(position,1.0);n=normalMatrix*normal;world=position;a=analysis;}";
 const char*fs=R"GLSL(precision mediump float;
varying mediump vec3 n;varying highp vec3 world;varying mediump vec4 a;
uniform vec4 color;uniform float flatLight,analysisMode,requiredRadius,resolutionMargin,clipEnabled,clipValue;uniform vec3 clipNormal;
vec3 hue(float h){return clamp(abs(fract(h+vec3(0.,.6667,.3333))*6.-3.)-1.,0.,1.);}
void main(){if(clipEnabled>.5&&dot(world,clipNormal)>clipValue)discard;vec3 c=color.rgb;
if(analysisMode>.5){if(a.w<.5)c=vec3(.48,.48,.5);else if(analysisMode<1.5)c=hue(mod(max(a.x,0.),12.)/12.);
else if(analysisMode<2.5){float spare=max(0.,a.y-resolutionMargin)-requiredRadius;c=spare<0.?vec3(.95,.15,.15):spare<.4?vec3(1.,.72,.12):vec3(.16,.84,.36);}
else c=a.z<0.?vec3(.5):a.z<.45?vec3(.95,.2,.2):a.z<.70?vec3(1.,.72,.12):a.z<.90?vec3(.2,.8,.65):vec3(.24,.5,1.);}
float light=mix(.26+.74*abs(dot(normalize(n),normalize(vec3(.2,.35,1.)))),1.,flatLight);gl_FragColor=vec4(c*light,color.a);})GLSL";
 if(!shader.addShaderFromSourceCode(QOpenGLShader::Vertex,vs)||!shader.addShaderFromSourceCode(QOpenGLShader::Fragment,fs)||!shader.link())error=shader.log();
 frameClock.start();glEnable(GL_DEPTH_TEST);glDisable(GL_CULL_FACE);
}
QJsonObject MeshView::cameraRequest()const{
 if(positions.isEmpty())return {};
 auto pose=navigationCamera.at(cameraDistance);auto f=pose.forward,u=pose.up;auto right=QVector3D::crossProduct(f,u).normalized();auto q=QQuaternion::fromAxisAndAngle(u,-scopeYaw)*QQuaternion::fromAxisAndAngle(right,scopePitch);f=q.rotatedVector(f);u=q.rotatedVector(u);
 auto arr=[](QVector3D v){return QJsonArray{v.x(),v.y(),v.z()};};
 int w=qBound(16,(width()/16)*16,640),h=qBound(4,int(double(height())*w/qMax(1,width())),512);
 return {{"camera",arr(pose.position)},{"forward",arr(f)},{"up",arr(u)},{"arc_mm",distance()},{"width",w},{"height",h},{"interactive",dragging||playback||alignTimer.isActive()||(motionClock.isValid()&&motionClock.elapsed()<250)},{"auto_align",autoAlign},{"manual_yaw_degrees",scopeYaw},{"manual_pitch_degrees",scopePitch},{"orientation_stabilization","arc Gaussian 1.2mm and rotation-minimizing transport"}};
}
void MeshView::loadScene(const QString&path,const QJsonObject&scene){
 compositeFrame={};compositeInfo={};compositeDirty=true;
 referenceInfo={};referenceCamera={};
 if(context())makeCurrent();for(auto&m:meshes){if(m.vbo&&context())glDeleteBuffers(1,&m.vbo);if(m.attributeVbo&&context())glDeleteBuffers(1,&m.attributeVbo);m.vbo=m.attributeVbo=0;m.count=0;m.file.clear();m.attributes.clear();m.boundsValid=false;}
 auto mo=scene["meshes"].toObject();QStringList names={"lung","airway","nodule"};QVector3D colors[]={{.32f,.55f,.82f},{.18f,.86f,.77f},{1.f,.34f,.30f}};
 QDir root=QFileInfo(path).dir();
 for(int i=0;i<3;++i){auto o=mo[names[i]].toObject();if(o.isEmpty())continue;meshes[i].file=root.filePath(o["file"].toString());meshes[i].count=o["vertices"].toInt();meshes[i].color=colors[i];auto attr=o["attributes"].toObject();if(!attr.isEmpty())meshes[i].attributes=root.filePath(attr["file"].toString());
  auto lo=o["bounds_min"].toArray(),hi=o["bounds_max"].toArray();auto&m=meshes[i];m.boundsValid=lo.size()==3&&hi.size()==3;
  if(m.boundsValid){m.minimum=vec(lo);m.maximum=vec(hi);for(int k=0;k<3;++k)m.boundsValid=m.boundsValid&&std::isfinite(m.minimum[k])&&std::isfinite(m.maximum[k])&&m.minimum[k]<=m.maximum[k];}
  if(i==1&&m.boundsValid){center=(m.minimum+m.maximum)*.5f;radius=qMax(1.f,(m.maximum-m.minimum).length()*.5f);}
 }
 originalCenter=center;originalRadius=radius;candidates=scene["candidates"].toArray();selectedCandidate=candidates.isEmpty()?-1:0;
 lungFullFile=meshes[0].file;lungFullCount=meshes[0].count;auto preview=mo["lung_preview"].toObject();lungPreviewFile=preview.isEmpty()?lungFullFile:root.filePath(preview["file"].toString());lungPreviewCount=preview.isEmpty()?lungFullCount:preview["vertices"].toInt();meshes[0].file=lungPreviewFile;meshes[0].count=lungPreviewCount;
 positions.clear();forwards.clear();ups.clear();route.clear();arcs.clear();cues={};
 auto nav=scene["navigation"].toObject();for(auto v:nav["positions"].toArray())positions.append(vec(v));for(auto v:nav["forward"].toArray())forwards.append(vec(v));for(auto v:nav["up"].toArray())ups.append(vec(v));for(auto v:nav["points"].toArray())route.append(vec(v));for(auto v:nav["arc"].toArray())arcs.append(v.toDouble());
 if(!navigationCamera.load(positions,forwards,ups,arcs)){positions.clear();forwards.clear();ups.clear();arcs.clear();}
 cues=nav["report"].toObject()["branch_guidance"].toObject()["events"].toArray();hud=nav["hud"].toObject()["samples"].toArray();resolutionMargin=float(nav["report"].toObject()["resolution_margin_mm"].toDouble());cameraIndex=0;cameraDistance=arcs.isEmpty()?0:arcs.first();resetView();if(context())doneCurrent();refresh();
}
void MeshView::setLayer(int i,bool enabled){if(i>=0&&i<3)meshes[i].visible=enabled;refresh();notifyPose(false);}
void MeshView::setLungDetail(bool full){if(context())makeCurrent();auto&m=meshes[0];if(m.vbo&&context()){glDeleteBuffers(1,&m.vbo);m.vbo=0;}m.file=full?lungFullFile:lungPreviewFile;m.count=full?lungFullCount:lungPreviewCount;if(context())doneCurrent();refresh();notifyPose(false);}
void MeshView::setScope(bool enabled){scope=enabled;scopeYaw=scopePitch=0;refresh();}
void MeshView::setCamera(int index){if(arcs.isEmpty())return;setDistance(arcs[qBound(0,index,arcs.size()-1)]);}
void MeshView::setDistance(float mm){if(arcs.isEmpty()||!std::isfinite(mm))return;float next=qBound(arcs.first(),mm,arcs.last());if(next==cameraDistance)return;cameraDistance=next;cameraIndex=cameraForDistance(next);beginAutoAlign();refresh();notifyPose(true);}
int MeshView::cameraForDistance(float mm)const{return arcs.isEmpty()?0:qMin(int(std::lower_bound(arcs.begin(),arcs.end(),mm)-arcs.begin()),arcs.size()-1);}
QJsonObject MeshView::overviewCamera()const{return {{"center",QJsonArray{center.x(),center.y(),center.z()}},{"radius",radius},{"yaw",yaw},{"pitch",pitch},{"zoom",zoom}};}
bool MeshView::restoreOverviewCamera(const QJsonObject&camera){
 auto a=camera["center"].toArray();if(scope||a.size()!=3)return false;
 for(auto v:a)if(!v.isDouble()||!std::isfinite(v.toDouble()))return false;
 for(const char*k:{"radius","yaw","pitch","zoom"})if(!camera[k].isDouble()||!std::isfinite(camera[k].toDouble()))return false;
 if(camera["radius"].toDouble()<=0||camera["zoom"].toDouble()<.3||camera["zoom"].toDouble()>6||std::abs(camera["pitch"].toDouble())>85)return false;
 center=vec(a);radius=camera["radius"].toDouble();yaw=camera["yaw"].toDouble();pitch=camera["pitch"].toDouble();zoom=camera["zoom"].toDouble();refresh();notifyPose(false);return true;
}
bool MeshView::fitVisible(){
 if(scope)return false;QVector3D lo,hi;bool found=false;
 for(const auto&m:meshes)if(m.visible&&m.count>0&&m.boundsValid){if(!found){lo=m.minimum;hi=m.maximum;found=true;}else for(int k=0;k<3;++k){lo[k]=qMin(lo[k],m.minimum[k]);hi[k]=qMax(hi[k],m.maximum[k]);}}
 if(!found)return false;center=(lo+hi)*.5f;
 // Fit the enclosing sphere for either landscape or portrait viewports.
 double half=std::atan(std::tan(21.*M_PI/180.)*qMin(1.,double(qMax(1,width()))/qMax(1,height())));
 radius=qMax(1.f,float((hi-lo).length()*.5*1.08/(2.8*std::sin(half))));zoom=1;refresh();notifyPose(false);return true;
}
void MeshView::resetView(){alignTimer.stop();yaw=pitch=scopeYaw=scopePitch=0;zoom=1;if(!scope&&fitVisible())return;center=originalCenter;radius=originalRadius;refresh();notifyPose(true);}
void MeshView::drawMeshes(const QMatrix4x4&mvp,const QMatrix4x4&view){
 shader.bind();shader.setUniformValue("mvp",mvp);shader.setUniformValue("normalMatrix",view.normalMatrix());shader.setUniformValue("flatLight",0.f);QVector3D cn;cn[clipAxis]=1;shader.setUniformValue("clipNormal",cn);shader.setUniformValue("clipValue",originalCenter[clipAxis]+clipFraction*originalRadius);shader.setUniformValue("clipEnabled",clipEnabled?1.f:0.f);shader.setUniformValue("requiredRadius",requiredRadius);shader.setUniformValue("resolutionMargin",resolutionMargin);
 int pos=shader.attributeLocation("position"),nor=shader.attributeLocation("normal"),attribute=shader.attributeLocation("analysis");
 // Opaque airway/lesion first; lung is a contextual transparent surface.
 for(int order:{1,2,0}){auto&m=meshes[order];if(!m.visible||m.count==0||(scope&&order!=1))continue;
  if(!m.vbo){QFile f(m.file);if(!f.open(QIODevice::ReadOnly)||f.size()!=qint64(m.count)*24){error="Mesh file size mismatch";continue;}uchar*p=f.map(0,f.size());if(!p){error="Mesh map failed";continue;}glGenBuffers(1,&m.vbo);glBindBuffer(GL_ARRAY_BUFFER,m.vbo);glBufferData(GL_ARRAY_BUFFER,f.size(),p,GL_STATIC_DRAW);f.unmap(p);}
  glBindBuffer(GL_ARRAY_BUFFER,m.vbo);glEnableVertexAttribArray(pos);glEnableVertexAttribArray(nor);glVertexAttribPointer(pos,3,GL_FLOAT,GL_FALSE,24,nullptr);glVertexAttribPointer(nor,3,GL_FLOAT,GL_FALSE,24,reinterpret_cast<void*>(12));
  shader.setUniformValue("analysisMode",order==1&&!m.attributes.isEmpty()?float(colorMode):0.f);
  if(order==1&&!m.attributes.isEmpty()){
   if(!m.attributeVbo){QFile f(m.attributes);if(!f.open(QIODevice::ReadOnly)||f.size()!=qint64(m.count)*16){error="Surface attribute size mismatch";continue;}auto data=f.readAll();glGenBuffers(1,&m.attributeVbo);glBindBuffer(GL_ARRAY_BUFFER,m.attributeVbo);glBufferData(GL_ARRAY_BUFFER,data.size(),data.constData(),GL_STATIC_DRAW);}
   glBindBuffer(GL_ARRAY_BUFFER,m.attributeVbo);glEnableVertexAttribArray(attribute);glVertexAttribPointer(attribute,4,GL_FLOAT,GL_FALSE,16,nullptr);
  }else{glDisableVertexAttribArray(attribute);glVertexAttrib4f(attribute,0,0,-1,0);}
  QVector3D col=scope?QVector3D(.79f,.47f,.32f):m.color;float alpha=order==0?lungOpacity:1.f;shader.setUniformValue("color",QVector4D(col,alpha));
  if(order==0){glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);glDepthMask(GL_FALSE);}else{glDisable(GL_BLEND);glDepthMask(GL_TRUE);}
  glDrawArrays(GL_TRIANGLES,0,m.count);
 }
 glDepthMask(GL_TRUE);glDisable(GL_BLEND);glDisableVertexAttribArray(pos);glDisableVertexAttribArray(nor);glDisableVertexAttribArray(attribute);glBindBuffer(GL_ARRAY_BUFFER,0);shader.release();
}
#include "composite_view_interactive_r1.inc"
void MeshView::paintGL(){
 auto begin=std::chrono::steady_clock::now();int viewportWidth=qRound(width()*devicePixelRatioF()),viewportHeight=qRound(height()*devicePixelRatioF());glViewport(0,0,viewportWidth,viewportHeight);glClearColor(.025f,.06f,.10f,1.f);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);glEnable(GL_DEPTH_TEST);glDisable(GL_CULL_FACE);
 lastPaintPreview=compositeEnabled&&compositePreview&&!scope;if(lastPaintPreview)++previewPaints;
 if(compositeEnabled&&!compositePreview&&!scope){drawComposite(viewportWidth,viewportHeight);frames.append(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count());if(frames.size()>2000)frames.remove(0,1000);return;}
 // Never substitute the smoothed mesh for the PL mask-derived surface.
 // A navigation view without a PL frame remains a labelled preparation screen.
 lastPaintAwaitingPl=scope&&plFrame.isNull();
 if(lastPaintAwaitingPl){++waitingPlPaints;paintedPlSequence=0;frames.append(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count());if(frames.size()>2000)frames.remove(0,1000);return;}
 if(scope&&!plFrame.isNull()){
  if(!scopeShader.isLinked()){
   const char*vs="attribute vec2 pos;varying mediump vec2 uv;void main(){uv=vec2((pos.x+1.0)*0.5,(1.0-pos.y)*0.5);gl_Position=vec4(pos,0.0,1.0);}";
   const char*fs=R"GLSL(#extension GL_OES_standard_derivatives : enable
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
varying mediump vec2 uv;uniform sampler2D frame,normalAtlas;uniform float field,aspect,depthScale,atlasColumns,plNormalFrame;uniform vec2 frameSize,atlasSize;uniform vec3 volumeShape,rayOrigin,ray00,rayDx,rayDy,worldForward,worldRight,worldUp;
vec3 normalAt(vec3 q){q=clamp(q,vec3(0.0),volumeShape-vec3(1.0));float z=floor(q.z),z1=min(z+1.0,volumeShape.z-1.0);vec2 tile=vec2(mod(z,atlasColumns),floor(z/atlasColumns)),tile1=vec2(mod(z1,atlasColumns),floor(z1/atlasColumns));vec2 a=(tile*(volumeShape.xy+2.0)+q.xy+1.5)/atlasSize,b=(tile1*(volumeShape.xy+2.0)+q.xy+1.5)/atlasSize;return mix(texture2D(normalAtlas,a).rgb,texture2D(normalAtlas,b).rgb,fract(q.z))*2.0-1.0;}
void main(){vec4 v=texture2D(frame,uv);float d=(v.r+v.g*256.0)/257.0;
vec3 p=vec3((uv.x*2.0-1.0)*aspect*field,(1.0-uv.y*2.0)*field,1.0)*d*depthScale;
vec2 pixel=floor(uv*frameSize);vec3 indexRay=ray00+pixel.x*rayDx+pixel.y*rayDy;
#ifdef PL_NORMAL_FRAME
vec3 n=(texture2D(normalAtlas,uv).rgb*255.0-128.0)/63.5;
#else
vec3 n=normalAt(rayOrigin+indexRay*d*(65535.0/64.0));
#endif
float norm=max(length(n),0.00001);
vec3 worldRay=worldForward+(uv.x*2.0-1.0)*aspect*field*worldRight+(1.0-uv.y*2.0)*field*worldUp;
float light=0.30+0.70*abs(dot(n/norm,normalize(worldRay)));
vec3 color=vec3(0.91,0.57,0.43)*light/(1.0+0.015*length(p));
if(v.r>0.999&&v.g>0.999)color=vec3(0.045,0.075,0.11);
color=mix(color,vec3(0.035,1.0,0.38),v.b*0.28);
if(v.a>0.75)color=vec3(1.0,0.92,0.08);else if(v.a>0.25)color=vec3(0.015,0.035,0.03);
gl_FragColor=vec4(color,1.0);})GLSL";
   QByteArray fragment=(plNormals.isNull()?QByteArray():QByteArray("#define PL_NORMAL_FRAME\n"))+fs;
   if(!scopeShader.addShaderFromSourceCode(QOpenGLShader::Vertex,vs)||!scopeShader.addShaderFromSourceCode(QOpenGLShader::Fragment,fragment)||!scopeShader.link()){error=scopeShader.log();qWarning()<<error;}
  }
  if(!scopeBlitShader.isLinked()){
   // The shading pass flips CPU image rows. FBO textures already have GL's
   // bottom-left origin, so the cached-color blit must not flip them again.
   const char*vs="attribute vec2 pos;varying mediump vec2 uv;void main(){uv=pos*0.5+0.5;gl_Position=vec4(pos,0.0,1.0);}";
   const char*fs="precision mediump float;varying mediump vec2 uv;uniform sampler2D colorFrame;void main(){gl_FragColor=texture2D(colorFrame,uv);}";
   if(!scopeBlitShader.addShaderFromSourceCode(QOpenGLShader::Vertex,vs)||!scopeBlitShader.addShaderFromSourceCode(QOpenGLShader::Fragment,fs)||!scopeBlitShader.link()){error=scopeBlitShader.log();qWarning()<<error;}
  }
  bool shade=plDirty||!scopeColor||scopeColor->size()!=plFrame.size();
  if(!scopeColor||scopeColor->size()!=plFrame.size()){
   scopeColor=std::make_unique<QOpenGLFramebufferObject>(plFrame.size(),QOpenGLFramebufferObject::NoAttachment);
   if(!scopeColor->isValid())error="Cannot allocate PL color framebuffer";
   glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,scopeColor->texture());glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
  }
  const float xy[]={-1,-1,1,-1,-1,1,-1,1,1,-1,1,1};
  glDisable(GL_DEPTH_TEST);glDisable(GL_BLEND);
  if(shade&&scopeShader.isLinked()&&scopeColor->isValid()){
   GLint viewport[4];glGetIntegerv(GL_VIEWPORT,viewport);scopeColor->bind();glViewport(0,0,plFrame.width(),plFrame.height());
   glDisable(GL_DEPTH_TEST);glDisable(GL_BLEND);glActiveTexture(GL_TEXTURE0);
   if(!scopeTexture){glGenTextures(1,&scopeTexture);glBindTexture(GL_TEXTURE_2D,scopeTexture);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);}else glBindTexture(GL_TEXTURE_2D,scopeTexture);
   bool fresh=plDirty;
   if(plDirty){if(scopeUploadedSize!=plFrame.size()){glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,plFrame.width(),plFrame.height(),0,GL_RGBA,GL_UNSIGNED_BYTE,plFrame.constBits());scopeUploadedSize=plFrame.size();}else glTexSubImage2D(GL_TEXTURE_2D,0,0,0,plFrame.width(),plFrame.height(),GL_RGBA,GL_UNSIGNED_BYTE,plFrame.constBits());plDirty=false;}
   auto atlas=plInfo["normal_atlas"].toObject();QString atlasPath=atlas["path"].toString();
   if(!normalTexture)glGenTextures(1,&normalTexture);glActiveTexture(GL_TEXTURE1);glBindTexture(GL_TEXTURE_2D,normalTexture);
   if(!plNormals.isNull()){
    if(fresh||normalPath!="PL"){
     glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
     if(normalPath!="PL"||normalUploadedSize!=plNormals.size()){glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,plNormals.width(),plNormals.height(),0,GL_RGBA,GL_UNSIGNED_BYTE,plNormals.constBits());normalUploadedSize=plNormals.size();}
     else glTexSubImage2D(GL_TEXTURE_2D,0,0,0,plNormals.width(),plNormals.height(),GL_RGBA,GL_UNSIGNED_BYTE,plNormals.constBits());
     normalPath="PL";
    }
   }else if(normalPath!=atlasPath){QFile f(atlasPath);int aw=atlas["width"].toInt(),ah=atlas["height"].toInt();GLint limit=0;glGetIntegerv(GL_MAX_TEXTURE_SIZE,&limit);if(aw>0&&ah>0&&aw<=limit&&ah<=limit&&f.open(QIODevice::ReadOnly)&&f.size()==qint64(aw)*ah*4){auto data=f.readAll();glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,aw,ah,0,GL_RGBA,GL_UNSIGNED_BYTE,data.constData());normalPath=atlasPath;}else error="PL shading atlas missing or oversized";}
   scopeShader.bind();scopeShader.setUniformValue("plNormalFrame",plNormals.isNull()?0.f:1.f);scopeShader.setUniformValue("normalAtlas",1);scopeShader.setUniformValue("atlasSize",QVector2D(atlas["width"].toInt(),atlas["height"].toInt()));scopeShader.setUniformValue("atlasColumns",float(atlas["columns"].toInt()));scopeShader.setUniformValue("volumeShape",vec(atlas["shape_xyz"]));scopeShader.setUniformValue("frameSize",QVector2D(plFrame.width(),plFrame.height()));
   scopeShader.setUniformValue("rayOrigin",vec(plInfo["ray_origin_index"]));scopeShader.setUniformValue("ray00",vec(plInfo["ray00_index"]));scopeShader.setUniformValue("rayDx",vec(plInfo["raydx_index"]));scopeShader.setUniformValue("rayDy",vec(plInfo["raydy_index"]));scopeShader.setUniformValue("worldForward",vec(plInfo["forward_lps"]));scopeShader.setUniformValue("worldRight",vec(plInfo["right_lps"]));scopeShader.setUniformValue("worldUp",vec(plInfo["up_lps"]));
   glActiveTexture(GL_TEXTURE0);scopeShader.setUniformValue("frame",0);scopeShader.setUniformValue("field",float(plInfo["field"].toDouble()));scopeShader.setUniformValue("aspect",float(plFrame.width())/plFrame.height());scopeShader.setUniformValue("depthScale",float(plInfo["step_mm"].toDouble()*65535/64));
   int attr=scopeShader.attributeLocation("pos");glBindBuffer(GL_ARRAY_BUFFER,0);glEnableVertexAttribArray(attr);glVertexAttribPointer(attr,2,GL_FLOAT,GL_FALSE,0,xy);glDrawArrays(GL_TRIANGLES,0,6);glDisableVertexAttribArray(attr);scopeShader.release();glBindTexture(GL_TEXTURE_2D,0);++scopeShadingPasses;
   // QOpenGLWidget owns its default FBO; binding framebuffer zero is wrong.
   glBindFramebuffer(GL_FRAMEBUFFER,defaultFramebufferObject());glViewport(viewport[0],viewport[1],viewport[2],viewport[3]);
  }
  if(scopeColor->isValid()&&scopeBlitShader.isLinked()){
   // Keep the completed frame's camera aspect while a resized request is in flight.
   QSize fit=plFrame.size();fit.scale(viewportWidth,viewportHeight,Qt::KeepAspectRatio);glViewport((viewportWidth-fit.width())/2,(viewportHeight-fit.height())/2,fit.width(),fit.height());
   glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,scopeColor->texture());scopeBlitShader.bind();scopeBlitShader.setUniformValue("colorFrame",0);
   int attr=scopeBlitShader.attributeLocation("pos");glBindBuffer(GL_ARRAY_BUFFER,0);glEnableVertexAttribArray(attr);glVertexAttribPointer(attr,2,GL_FLOAT,GL_FALSE,0,xy);glDrawArrays(GL_TRIANGLES,0,6);glDisableVertexAttribArray(attr);scopeBlitShader.release();glBindTexture(GL_TEXTURE_2D,0);++scopeCachedBlits;paintedPlSequence=plInfo["sequence"].toInt();glViewport(0,0,viewportWidth,viewportHeight);
   paintedPlInfo=plInfo;GLenum glError=glGetError();if(glError!=GL_NO_ERROR)error=QString("PL color framebuffer GL error %1").arg(glError);
  }
  frames.append(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count());if(frames.size()>2000)frames.remove(0,1000);return;
 }
 QMatrix4x4 view,projection;
 view.lookAt(center+QVector3D(0,-radius*2.8f/zoom,0),center,QVector3D(0,0,1));view.translate(center);view.rotate(pitch,1,0,0);view.rotate(yaw,0,0,1);view.translate(-center);
 projection.perspective(42,float(width())/qMax(1,height()),.1f,radius*12.f);
 lastMvp=projection*view;if(error.isEmpty())drawMeshes(lastMvp,view);
 frames.append(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count());if(frames.size()>2000)frames.remove(0,1000);
}
void MeshView::mousePressEvent(QMouseEvent*e){if(!scope&&meshes[2].visible&&e->button()==Qt::RightButton){int selected=-1;float best=24;for(auto v:candidates){auto c=v.toObject();QPointF q;if(!projectOverview(vec(c["centroid_lps_mm"]),q))continue;float d=QLineF(q,e->pos()).length();if(d<best){best=d;selected=c["index"].toInt();}}if(selected>=0){selectCandidate(selected);if(onCandidatePicked)onCandidatePicked(selected);e->accept();return;}}if(e->button()!=Qt::LeftButton&&e->button()!=Qt::MiddleButton&&e->button()!=Qt::RightButton)return;previous=e->pos();dragging=true;panning=!scope&&e->button()!=Qt::LeftButton;alignTimer.stop();e->accept();}
void MeshView::mouseMoveEvent(QMouseEvent*e){if(!dragging)return;auto delta=e->pos()-previous;previous=e->pos();if(scope){scopeYaw+=delta.x()*.22f;scopePitch=qBound(-75.f,scopePitch+delta.y()*.22f,75.f);}else if(panning){QMatrix4x4 rotation;rotation.rotate(pitch,1,0,0);rotation.rotate(yaw,0,0,1);auto inverse=rotation.inverted();float mm=2.f*radius*2.8f/zoom*std::tan(21.f*M_PI/180.f)/qMax(1,height());center-=inverse.mapVector(QVector3D(delta.x(),0,-delta.y()))*mm;}else{yaw+=delta.x()*.45f;pitch=qBound(-85.f,pitch+delta.y()*.45f,85.f);}refresh();notifyPose(true);}
void MeshView::mouseReleaseEvent(QMouseEvent*e){dragging=false;beginAutoAlign();notifyPose(true);e->accept();}
void MeshView::mouseDoubleClickEvent(QMouseEvent*){resetView();}
void MeshView::wheelEvent(QWheelEvent*e){if(e->angleDelta().y()==0){e->ignore();return;}if(scope){setCamera(cameraIndex+(e->angleDelta().y()>0?4:-4));if(onCamera)onCamera(cameraIndex);}else{zoom=qBound(.3f,zoom*float(std::pow(1.12,e->angleDelta().y()/120.)),6.f);refresh();notifyPose(false);}e->accept();}
QJsonObject MeshView::metrics()const{QVector<double> v=frames;std::sort(v.begin(),v.end());return {{"renderer",renderer},{"shader_linked",shader.isLinked()},{"error",error},{"valid",isValid()},{"frames",v.size()},{"scope_shading_passes",scopeShadingPasses},{"scope_cached_blits",scopeCachedBlits},{"paint_submit_median_ms",v.isEmpty()?0:v[v.size()/2]},{"paint_submit_max_ms",v.isEmpty()?0:v.last()},{"note","paintGL CPU submission duration, not complete GPU frame latency"}};}

void MeshView::focusCandidate(int index){for(auto v:candidates){auto c=v.toObject();if(c["index"].toInt()==index){selectedCandidate=index;center=vec(c["centroid_lps_mm"]);radius=qMax(12.f,(vec(c["bounds_max"])-vec(c["bounds_min"])).length()*1.2f);yaw=pitch=0;zoom=1;refresh();notifyPose(false);return;}}}
bool MeshView::setReferenceCamera(QJsonObject frame){
 referenceMode=true;auto next=ScopeReference::fromFrame(frame);
 if(!frame.isEmpty()&&!next.valid)return false;
 if(next.valid&&referenceCamera.valid&&next.sequence<referenceCamera.sequence)return false;
 referenceInfo=frame;referenceCamera=next;refresh();return true;
}
QJsonObject MeshView::referenceCameraMetrics()const{
 QJsonObject out{{"enabled",referenceMode},{"valid",referenceCamera.valid}};if(!referenceCamera.valid)return out;
 auto array=[](QVector3D v){return QJsonArray{v.x(),v.y(),v.z()};};QJsonArray corners;for(auto v:referenceCamera.corners())corners.append(array(v));
 out["sequence"]=referenceCamera.sequence;out["camera_lps"]=array(referenceCamera.eye);out["forward_lps"]=array(referenceCamera.forward);out["right_lps"]=array(referenceCamera.right);out["up_lps"]=array(referenceCamera.up);
 out["field"]=referenceCamera.field;out["aspect"]=referenceCamera.aspect;out["arc_mm"]=referenceCamera.arc;out["frustum_depth_mm"]=15;out["corners_lps"]=corners;out["pose_source"]="presented_PL_frame";return out;
}
QJsonObject MeshView::featureMetrics()const{return {{"color_mode",colorMode},{"candidate_count",candidates.size()},{"selected_candidate",selectedCandidate},{"clip_enabled",clipEnabled},{"lung_opacity",lungOpacity},{"hud_samples",hud.size()},{"overlay_paints",overlayPaints},{"waiting_pl_paints",waitingPlPaints},{"last_paint_awaiting_pl",lastPaintAwaitingPl}};}

void MeshView::refresh(){QOpenGLWidget::update();if(overlay)overlay->update();}
void MeshView::resizeEvent(QResizeEvent*e){QOpenGLWidget::resizeEvent(e);if(overlay){overlay->setGeometry(rect());overlay->raise();}notifyPose(false);}
void MeshView::paintOverlay(QPainter &p){
 ++overlayPaints;
 if(compositeEnabled&&!compositePreview&&!scope&&compositeFrame.isNull()){p.setPen(QColor("#dce8f5"));p.drawText(rect().adjusted(20,0,-20,0),Qt::AlignCenter|Qt::TextWordWrap,compositeStatus.isEmpty()?QString::fromUtf8("正在准备 PL 合成总览"):compositeStatus);return;}
 if(scope&&plFrame.isNull()){
  p.setPen(QColor("#dce8f5"));QString heading=positions.isEmpty()?QString::fromUtf8("尚无 PL 导航画面"):QString::fromUtf8("正在准备 PL 导航画面");
  p.drawText(rect().adjusted(24,0,-24,-42),Qt::AlignCenter,heading);
  QString detail=!error.isEmpty()?error:!scopeStatus.isEmpty()?scopeStatus:positions.isEmpty()?QString::fromUtf8("请先完成分割、重建和导航规划"):QString::fromUtf8("首帧完成后显示；导航始终使用同一气道数据");
  p.setPen(error.isEmpty()?QColor("#8296ae"):QColor("#ff6262"));p.drawText(rect().adjusted(24,42,-24,0),Qt::AlignCenter|Qt::TextWordWrap,detail);return;
 }
 if(scope&&!plFrame.isNull()){
  auto &painter=p;painter.setPen(QColor("#fff0aa"));painter.drawText(14,25,QString::fromUtf8("PL 气镜 · 可见通道与贴合轮廓"));painter.drawText(14,height()-14,QString::fromUtf8("%1 × %2 · 帧处理 %3 ms").arg(plFrame.width()).arg(plFrame.height()).arg(plInfo["total_seconds"].toDouble()*1000,0,'f',1));
  if(cameraIndex<hud.size()){auto h=hud[cameraIndex].toObject();QString state=h["state"].toString();painter.fillRect(QRect(8,34,qMax(100,width()-16),52),QColor(7,18,28,215));painter.setPen(state=="blocked"?QColor("#ff6262"):state=="caution"?QColor("#ffdc79"):QColor("#5bf3ab"));painter.drawText(14,54,QString::fromUtf8("当前管径 %1 mm · 前方 10 mm 保守管径 %2 mm").arg(h["current_diameter_mm"].toDouble(),0,'f',2).arg(h["forward_adjusted_diameter_mm"].toDouble(),0,'f',2));painter.drawText(14,75,QString::fromUtf8("模型余量 %1 mm · %2（图像几何估算）").arg(h["spare_radius_mm"].toDouble(),0,'f',2).arg(state=="blocked"?QString::fromUtf8("受约束"):state=="caution"?QString::fromUtf8("余量较小"):QString::fromUtf8("满足当前几何约束")));}
  if(!scopeStatus.isEmpty())painter.drawText(14,106,scopeStatus);if(!error.isEmpty()){painter.setPen(Qt::red);painter.drawText(rect().adjusted(12,65,-12,-12),Qt::TextWordWrap,error);}

  return;
 }
 if(compositeEnabled&&compositePreview&&!scope){p.setPen(QColor("#fff0aa"));p.drawText(14,height()-14,QString::fromUtf8("交互预览 · 近似透明 · 停止操作后生成精确画面"));}
 if(compositeEnabled&&!compositePreview&&!scope){p.setPen(QColor("#fff0aa"));p.drawText(14,height()-14,QString::fromUtf8("PL 透明合成 · %1 × %2 · %3").arg(compositeFrame.width()).arg(compositeFrame.height()).arg(compositeStatus.isEmpty()?QString::fromUtf8("已完成"):compositeStatus));}
 p.setRenderHint(QPainter::Antialiasing);p.setPen(QColor("#e3edf9"));p.drawText(14,25,referenceMode?QString::fromUtf8("联动总览 · 当前气镜方向"):QString::fromUtf8("三维总览  ·  拖动旋转 / 滚轮缩放"));
 auto project=[&](QVector3D v,QPointF&out){return projectOverview(v,out);};
 if(!scope&&meshes[2].visible){for(auto value:candidates){auto candidate=value.toObject();QPointF q;if(project(vec(candidate["centroid_lps_mm"]),q)){bool selected=candidate["index"].toInt()==selectedCandidate;p.setPen(QPen(selected?QColor("#ffdc79"):QColor("#ff7979"),selected?3:1));p.setBrush(Qt::NoBrush);p.drawEllipse(q,selected?12:6,selected?12:6);if(selected)p.drawText(q+QPointF(16,-8),QString::fromUtf8("候选 #%1").arg(selectedCandidate));}}}
 if(drawRoute&&!scope&&route.size()>1){QPainterPath path;bool started=false;for(auto v:route){QPointF q;if(project(v,q)){if(started)path.lineTo(q);else{path.moveTo(q);started=true;}}else started=false;}p.setPen(QPen(QColor("#ffe17a"),2));p.drawPath(path);}
 if(drawRoute&&!scope&&referenceMode&&referenceCamera.valid){
  auto &r=referenceCamera;QPointF apex,front;if(project(r.eye,apex)){p.setPen(QPen(QColor("#68e9ff"),2));p.setBrush(QColor("#68e9ff"));p.drawEllipse(apex,5,5);QPointF corners[4];auto world=r.corners();bool visible=true;for(int k=0;k<4;++k)visible=project(world[k],corners[k])&&visible;if(visible)for(int k=0;k<4;++k){p.drawLine(apex,corners[k]);p.drawLine(corners[k],corners[(k+1)%4]);}if(project(r.eye+r.forward*15.f,front)){p.setPen(QPen(QColor("#ffe17a"),3));p.drawLine(apex,front);auto d=front-apex;double length=std::hypot(d.x(),d.y());if(length>1){d/=length;QPointF side(-d.y(),d.x());p.setBrush(QColor("#ffe17a"));QPolygonF tip;tip<<front<<front-d*8+side*4<<front-d*8-side*4;p.drawPolygon(tip);}}p.setPen(QColor("#68e9ff"));p.drawText(apex+QPointF(8,-8),QString::fromUtf8("当前镜头"));}
 }else if(drawRoute&&!scope&&!referenceMode&&cameraIndex<positions.size()){
  auto pose=navigationCamera.at(cameraDistance);QVector3D eye=pose.position,f=pose.forward,up=pose.up,right=QVector3D::crossProduct(f,up).normalized();QPointF apex;
  if(project(eye,apex)){p.setPen(QPen(QColor("#68e9ff"),2));p.setBrush(QColor("#68e9ff"));p.drawEllipse(apex,5,5);QVector3D far=eye+f*15.f;QPointF corners[4];bool visible=true;for(int k=0;k<4;++k)visible=project(far+right*(k==0||k==3?6.f:-6.f)+up*(k<2?4.f:-4.f),corners[k])&&visible;if(visible)for(int k=0;k<4;++k){p.drawLine(apex,corners[k]);p.drawLine(corners[k],corners[(k+1)%4]);}}
 }
 if(!error.isEmpty()){p.setPen(Qt::red);p.drawText(rect().adjusted(12,45,-12,-12),Qt::TextWordWrap,error);}
 if(meshes[1].count==0){p.setPen(QColor("#8197ae"));p.drawText(rect(),Qt::AlignCenter,QString::fromUtf8("运行重建后显示模型"));}

}

void MeshView::setPreviewRoute(const QJsonArray&points){
 QVector<QVector3D> next;for(auto v:points){auto a=v.toArray();if(a.size()!=3)throw std::runtime_error("Invalid preview route coordinate");double x=a[0].toDouble(),y=a[1].toDouble(),z=a[2].toDouble();if(!std::isfinite(x)||!std::isfinite(y)||!std::isfinite(z))throw std::runtime_error("Nonfinite preview route coordinate");next.append(QVector3D(x,y,z));}if(next.isEmpty())throw std::runtime_error("Empty preview route");route=next;refresh();
}
QJsonObject MeshView::previewRouteMetrics()const{
 auto array=[](QVector3D v){return QJsonArray{v.x(),v.y(),v.z()};};return {{"point_count",route.size()},{"start_lps_mm",route.isEmpty()?QJsonArray():array(route.first())},{"end_lps_mm",route.isEmpty()?QJsonArray():array(route.last())}};
}

#include "fast_opacity_regression_r1.inc"
