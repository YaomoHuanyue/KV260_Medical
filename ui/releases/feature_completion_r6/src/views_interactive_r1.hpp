#pragma once
#include <QtWidgets>
#include <QOpenGLWidget>
#include <QOpenGLFunctions>
#include <QOpenGLShaderProgram>
#include <QOpenGLFramebufferObject>
#include <memory>
#include <functional>
#include "navigation_camera.hpp"
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
 void refresh();void paintOverlay(QPainter&);
 struct Mesh{QString file,attributes;int count=0;GLuint vbo=0,attributeVbo=0;QVector3D color,minimum,maximum;bool visible=false,boundsValid=false;};
 Mesh meshes[3]; QOpenGLShaderProgram shader;
 QString lungFullFile,lungPreviewFile;int lungFullCount=0,lungPreviewCount=0;
 QVector<QVector3D> positions,forwards,ups,route;
 QVector<float> arcs; QJsonArray cues,candidates,hud;
 int selectedCandidate=-1,colorMode=0,clipAxis=2;bool clipEnabled=false;float clipFraction=0,lungOpacity=.20f,requiredRadius=.7f,resolutionMargin=0;
 QVector3D originalCenter;float originalRadius=150;
 QVector3D center{0,0,0};float radius=150,yaw=0,pitch=0,zoom=1;
 QPoint previous;bool dragging=false,panning=false,scope=false,drawRoute=true;
 int cameraIndex=0; float cameraDistance=0,scopeYaw=0,scopePitch=0;NavigationCamera navigationCamera;
 bool autoAlign=true,playback=false;float alignYaw=0,alignPitch=0;
 QTimer alignTimer,refineTimer;QElapsedTimer alignClock,motionClock;float alignDuration=800;
 QMatrix4x4 lastMvp;
 bool compositePreview=false;int previewPaints=0,previewSwaps=0;bool lastPaintPreview=false;bool compositeEnabled=false;QImage compositeFrame;QJsonObject compositeInfo;QString compositeStatus;GLuint compositeTexture=0;bool compositeDirty=false;QOpenGLShaderProgram compositeShader;
 QRectF compositeRect()const;bool projectOverview(QVector3D,QPointF&)const;bool drawComposite(int,int);
 QString error, renderer;
 QImage plFrame,plNormals;QJsonObject plInfo;QOpenGLShaderProgram scopeShader,scopeBlitShader;GLuint scopeTexture=0,normalTexture=0;bool plDirty=false;QString scopeStatus,normalPath;QSize scopeUploadedSize,normalUploadedSize;
 std::unique_ptr<QOpenGLFramebufferObject> scopeColor;int scopeShadingPasses=0,scopeCachedBlits=0;
 QElapsedTimer frameClock; QVector<double> frames;
 int paintedPlSequence=0,swappedPlSequence=0,waitingPlPaints=0;bool lastPaintAwaitingPl=false;
 QJsonObject paintedPlInfo,presentedPlInfo,referenceInfo;ScopeReference referenceCamera;bool referenceMode=false;
 void drawMeshes(const QMatrix4x4&,const QMatrix4x4&);
 void notifyPose(bool moving);void beginAutoAlign();
public:
 std::function<void(int)> onCamera;
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
 void setColorMode(int mode){colorMode=mode;refresh();notifyPose(false);}
 void setAnalysisParameters(float diameter,float margin){requiredRadius=diameter*.5f+margin;refresh();notifyPose(false);}
 void setClipping(bool enabled,int axis,float fraction){clipEnabled=enabled;clipAxis=qBound(0,axis,2);clipFraction=qBound(-1.f,fraction,1.f);refresh();notifyPose(false);}
 void setLungOpacity(float value){lungOpacity=qBound(0.f,value,1.f);refresh();notifyPose(false);}
 void focusCandidate(int index);void selectCandidate(int index){selectedCandidate=index;refresh();}
 QJsonObject featureMetrics()const;
 void setPreviewRoute(const QJsonArray&); QJsonObject previewRouteMetrics()const;
 void setScope(bool enabled); void setRoute(bool enabled){drawRoute=enabled;refresh();}
 void setCamera(int index);int cameraCount()const{return positions.size();}
 void setDistance(float mm);
 int cameraForDistance(float mm)const;
 void setAutoAlign(bool enabled);void setPlayback(bool enabled);
 float distance()const{return cameraDistance;}
 float totalDistance()const{return arcs.isEmpty()?0:arcs.last();}
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
 QPointF candidateScreenPoint(int index)const;
 QJsonObject cameraRequest()const;
 QJsonObject presentedScopeFrame()const{return presentedPlInfo;}
 bool setReferenceCamera(QJsonObject frame);
 QJsonObject referenceCameraMetrics()const;
 void setPlFrame(QImage frame,QImage normals,QJsonObject info){plFrame=frame;plNormals=normals;plInfo=info;plDirty=true;scopeStatus.clear();refresh();}
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
