#pragma once
#include <QMatrix4x4>
#include <QtWidgets>
#include <QOpenGLWidget>
#include <QOpenGLFunctions>
#include <QOpenGLShaderProgram>
#include <QOpenGLFramebufferObject>
#include <memory>
#include <cmath>
#include <functional>
#include "navigation_camera.hpp"
#include "gamepad_camera.hpp"
#include "scope_reference.hpp"

struct Volume {
 QFile ctFile, maskFile;
 const float* data=nullptr; const uchar* masks=nullptr;
 int dims[3]={0,0,0}; float spacing[3]={1,1,1};
 QVector3D origin; QMatrix3x3 direction;
 QString path;
 bool ctLocked=false,maskLocked=false;
 ~Volume();
 void load(const QString& scenePath,const QJsonObject& meta);
 qint64 index(int x,int y,int z)const{return (qint64(z)*dims[1]+y)*dims[0]+x;}
 QVector3D physical(int x,int y,int z) const;
};

class SliceView : public QWidget {
 std::shared_ptr<Volume> volume;
 int axis=2, slice=0, airwayBit=2; float center=-600,widthHU=1500; bool showMask=true;
 QImage image; QRectF imageRect; QString planeTitle;
 void rebuild();
public:
 std::function<void(int)> onSlice;
 std::function<void(QString)> onPosition;
 SliceView(int plane,QString title,QWidget*parent=nullptr);
 void setVolume(std::shared_ptr<Volume> v);
 void setSlice(int value); int currentSlice()const{return slice;}
 void windowLevel(float c,float w); void setMask(bool enabled);
 bool setAirwayMask(int bit); int airwayMaskBit()const{return airwayBit;}
 QImage sliceImage()const{return image;}
protected:
 void paintEvent(QPaintEvent*)override;
 void wheelEvent(QWheelEvent*)override;
 void mousePressEvent(QMouseEvent*)override;
};

class MeshOverlay;
class MeshView : public QOpenGLWidget,protected QOpenGLFunctions {
 friend class MeshOverlay;QWidget*overlay=nullptr;int overlayPaints=0;
 void refresh();void paintOverlay(QPainter&,QSize captureSize={});
 struct Mesh{QString file,attributes;int count=0;GLuint vbo=0,attributeVbo=0;QVector3D color,minimum,maximum;bool visible=false,boundsValid=false;};
 QMatrix4x4 displayModel(unsigned)const;QVector3D displayPoint(QVector3D,unsigned)const;
 Mesh meshes[3]; QOpenGLShaderProgram shader;
 QString lungFullFile,lungPreviewFile;int lungFullCount=0,lungPreviewCount=0;
 QVector<QVector3D> positions,forwards,ups,route;
 QVector<float> arcs; QJsonArray cues,candidates,hud;
 QString nearestAnalysisFile,displayAnalysisFile,analysisSamplingPolicy="nearest";bool analysisConfidenceAvailable=false;
 int selectedCandidate=-1,colorMode=0,clipAxis=2;bool clipEnabled=false;float clipFraction=0,lungOpacity=.20f,requiredRadius=.7f,resolutionMargin=0;
 QVector3D originalCenter;float originalRadius=150;
 QVector3D center{0,0,0};float radius=150,yaw=0,pitch=0,zoom=1;
 QPoint previous;bool dragging=false,panning=false,scope=false,drawRoute=true;
 int cameraIndex=0; float cameraDistance=0,scopeYaw=0,scopePitch=0;NavigationCamera navigationCamera;
 medical_gamepad::ManualCamera manualCamera;
 bool autoAlign=true,playback=false;float alignYaw=0,alignPitch=0;
 QTimer alignTimer,refineTimer;QElapsedTimer alignClock,motionClock;float alignDuration=800;
 QMatrix4x4 lastMvp;
 bool compositePreview=false;int previewPaints=0,previewSwaps=0;bool lastPaintPreview=false;bool compositeEnabled=false;QImage compositeFrame;QJsonObject compositeInfo;QString compositeStatus;GLuint compositeTexture=0;bool compositeDirty=false;QOpenGLShaderProgram compositeShader;
 QRectF compositeRect()const;bool projectOverview(QVector3D,QPointF&)const;bool drawComposite(int,int);
 QString error, renderer;
 QImage plFrame,plNormals;QJsonObject plInfo;QOpenGLShaderProgram scopeShader,scopeBlitShader;GLuint scopeTexture=0,normalTexture=0;bool plDirty=false;QString scopeStatus,normalPath;QSize scopeUploadedSize,normalUploadedSize;
 std::unique_ptr<QOpenGLFramebufferObject> linkedColor,scopeColor;int scopeShadingPasses=0,scopeCachedBlits=0;
 QElapsedTimer frameClock; QVector<double> frames;
 int paintedPlSequence=0,swappedPlSequence=0,waitingPlPaints=0;bool lastPaintAwaitingPl=false;
 QJsonObject paintedPlInfo,presentedPlInfo,referenceInfo;ScopeReference referenceCamera;bool referenceMode=false;
 std::unique_ptr<QOpenGLFramebufferObject> normalBackground,normalNearest;QOpenGLShaderProgram normalShellShader;QByteArray normalShellKey;int normalShellGeometryBuilds=0,normalShellCompositions=0;
 void drawNormalOverview(const QMatrix4x4&,const QMatrix4x4&,int,int);
 void drawMeshes(const QMatrix4x4&,const QMatrix4x4&);
 void notifyPose(bool moving);void beginAutoAlign();
public:
 std::function<void(int)> onCamera;
 QJsonObject hudCurrent()const{return cameraIndex>=0&&cameraIndex<hud.size()?hud[cameraIndex].toObject():QJsonObject{};}
 QVector<double> branchArcs()const{QVector<double> r;for(auto e:cues){auto o=e.toObject();if(o.contains("junction_arc_mm"))r<<o["junction_arc_mm"].toDouble();}return r;}
 std::function<void(int)> onCandidatePicked;
 std::function<void(QString)> onBackend;
 std::function<void()> onPoseChanged;
 std::function<void()> onOverviewChanged;
 std::function<void(int)> onPlPresented;
 MeshView(QWidget*parent=nullptr);
 ~MeshView();
 void loadScene(const QString&path,const QJsonObject&scene);
 void setLayer(int i,bool enabled);
 void setLungDetail(bool full);
 bool setAirwayAttributeFile(const QString&path){
  auto&m=meshes[1];if(!m.count)return true;if(m.attributes==path)return true;
  if(QFileInfo(path).size()!=qint64(m.count)*16)return false;
  if(m.attributeVbo&&context()){makeCurrent();glDeleteBuffers(1,&m.attributeVbo);doneCurrent();}
  m.attributeVbo=0;m.attributes=path;invalidateCompositeFrame();notifyPose(false);return true;
 }
 QString airwayAttributeFile()const{return meshes[1].attributes;}
 void setAttributeSamplingSources(QString nearest,QString display,bool available,QString policy){
  nearestAnalysisFile=nearest;displayAnalysisFile=display;analysisConfidenceAvailable=available;analysisSamplingPolicy=policy;
 }
 QJsonObject attributeSamplingMetrics()const{return {{"nearest_file",nearestAnalysisFile},{"display_file",displayAnalysisFile},
  {"confidence_available",analysisConfidenceAvailable},{"policy",analysisSamplingPolicy}};}

 void setColorMode(int mode){colorMode=mode;refresh();notifyPose(false);}
 void setAnalysisParameters(float diameter,float margin){requiredRadius=diameter*.5f+margin;refresh();notifyPose(false);}
 void setClipping(bool enabled,int axis,float fraction){clipEnabled=enabled;clipAxis=qBound(0,axis,2);clipFraction=qBound(-1.f,fraction,1.f);refresh();notifyPose(false);}
 void setLungOpacity(float value){lungOpacity=qBound(0.f,value,1.f);refresh();notifyPose(false);}
 void focusCandidate(int index);void selectCandidate(int index){selectedCandidate=index;refresh();}
 QJsonObject featureMetrics()const;
 void setScope(bool enabled); void setRoute(bool enabled){drawRoute=enabled;refresh();}
 void setCamera(int index);int cameraCount()const{return positions.size();}
 void setDistance(float mm);
 int cameraForDistance(float mm)const;
 void setAutoAlign(bool enabled);void setPlayback(bool enabled);
 void setManualNavigation(bool enabled);bool manualNavigation()const{return manualCamera.active();}
 bool manualMotion(float millimeters,float yawDegrees,float pitchDegrees);
 float distance()const{return cameraDistance;}
 float totalDistance()const{return arcs.isEmpty()?0:arcs.last();}
 // 导航关键数据：分岔级数、下一分岔距离与转向、路径进度、到目标距离、前方最窄处（全部取自已载入的路径/HUD/分岔事件，不新增计算后端）
 QJsonObject navInfo(const QVector3D&target,bool hasTarget)const{
  QJsonObject o;if(positions.isEmpty()||arcs.size()!=positions.size())return o;
  int ci=qBound(0,cameraIndex,positions.size()-1);float cur=cameraDistance,total=arcs.last();
  o["arc_mm"]=cur;o["total_mm"]=total;o["progress"]=total>0?double(qBound(0.f,cur/total,1.f)):0.;
  int passed=0,events=0;double nextArc=-1;int nextId=-1;
  for(auto v:cues){auto e=v.toObject();if(!e.contains("junction_arc_mm"))continue;++events;double ja=e["junction_arc_mm"].toDouble();
   if(ja<=cur+0.05)++passed;else if(nextArc<0||ja<nextArc){nextArc=ja;nextId=e["id"].toInt();}}
  o["junctions_passed"]=passed;o["junctions_total"]=events;
  if(nextArc>=0){
   int j=cameraForDistance(float(nextArc)),b=cameraForDistance(float(qMin(double(total),nextArc+10.)));
   QVector3D f=forwards[j].normalized(),u=ups[j].normalized(),r=QVector3D::crossProduct(f,u).normalized(),d=(positions[b]-positions[j]);
   QString dir=u8"直行";double angle=0;
   if(d.length()>1e-3){d.normalize();double lat=QVector3D::dotProduct(d,r),ver=QVector3D::dotProduct(d,u),al=QVector3D::dotProduct(d,f);
    angle=qRadiansToDegrees(std::atan2(std::sqrt(lat*lat+ver*ver),al));
    if(angle>=12)dir=std::abs(lat)>=std::abs(ver)?(lat>0?u8"向右":u8"向左"):(ver>0?u8"向上":u8"向下");}
   o["next_junction_mm"]=nextArc-cur;o["next_direction"]=dir;o["next_angle_deg"]=angle;o["next_junction_id"]=nextId;}
  if(hasTarget)o["target_distance_mm"]=double((positions[ci]-target).length());
  double minD=-1,minArc=0;
  for(int i=ci;i<hud.size()&&i<arcs.size();++i){double v=hud[i].toObject()["current_diameter_mm"].toDouble(-1);if(v>0&&(minD<0||v<minD)){minD=v;minArc=arcs[i];}}
  if(minD>0){o["narrowest_diameter_mm"]=minD;o["narrowest_ahead_mm"]=minArc-cur;}
  return o;}
 void resetView();void turn(float degrees){yaw+=degrees;refresh();notifyPose(false);}
 bool fitVisible();bool restoreOverviewCamera(const QJsonObject&);
 QJsonObject overviewCamera()const;
 QJsonObject overviewRequest()const;
 void setCompositeEnabled(bool enabled){if(enabled&&!compositeEnabled){compositeFrame={};compositeInfo={};compositeDirty=true;}compositeEnabled=enabled;if(!enabled)compositePreview=false;refresh();}
 bool compositeMode()const{return compositeEnabled;}
 void setCompositePreview(bool value){compositePreview=value&&compositeEnabled;refresh();}
 bool compositePreviewMode()const{return compositeEnabled&&compositePreview;}
 QJsonObject compositePreviewMetrics()const{return {{"painted",previewPaints},{"swapped",previewSwaps},{"active",compositePreviewMode()}};}
 bool setCompositeFrame(QImage,QJsonObject);
 void setCompositeStatus(QString text){compositeStatus=text;refresh();}
 QJsonObject completedComposite()const{return compositeInfo;}
 QImage completedCompositeImage()const{return compositeFrame;}
 void invalidateCompositeFrame(){compositeFrame={};compositeInfo={};compositeDirty=true;refresh();}
 QPointF candidateScreenPoint(int index)const;
 QJsonObject cameraRequest()const;
 QJsonObject scopeViewState()const;bool restoreScopeViewState(const QJsonObject&);QImage completedScopeColor();
 QImage linkedOverviewColor(QSize,const QJsonObject&,QJsonObject&);
 QJsonObject presentedScopeFrame()const{return presentedPlInfo;}
 bool setReferenceCamera(QJsonObject frame);
 QJsonObject referenceCameraMetrics()const;
 void setPlFrame(QImage frame,QImage normals,QJsonObject info){plFrame=frame;plNormals=normals;plInfo=info;plDirty=true;scopeStatus.clear();refresh();}
 bool hasPlFrame()const{return !plFrame.isNull();}
 void clearPlFrame(QString message=QString()){plFrame=QImage();plNormals=QImage();plInfo={};paintedPlInfo={};presentedPlInfo={};paintedPlSequence=swappedPlSequence=0;scopeStatus=message;refresh();}
 void setScopeStatus(QString message){scopeStatus=message;refresh();}
 QString backend()const{return renderer;}
 QJsonObject metrics()const;
protected:
 void resizeEvent(QResizeEvent*)override;
 void initializeGL()override;void paintGL()override;
 void mousePressEvent(QMouseEvent*)override;void mouseMoveEvent(QMouseEvent*)override;
 void mouseReleaseEvent(QMouseEvent*)override;void mouseDoubleClickEvent(QMouseEvent*)override;
 void wheelEvent(QWheelEvent*)override;
};
