#include "pl_scope.hpp"
#include <cmath>

// All process I/O, copying and next-frame dispatch run away from EGLFS/vsync.
// There is still one PL operation in flight and only the newest unsent pose.
class PlScopeTransport : public QObject {
 QProcess process;QString root,source,frameFile,module;QByteArray pending;
 bool ready=false,inFlight=false,stopping=false;QJsonObject latest,sentPose;int sequence=0;quint64 intent=0;
 int quality=0;QElapsedTimer roundTrip;
 QVector<std::function<void()>> afterStop;
 void send();void lines();
public:
 quint64 uiIntent=0;
 std::function<void(QImage,QImage,QJsonObject)> onFrame;
 std::function<void(QString)> onStatus;
 std::function<void(bool,quint64)> onActive;
 explicit PlScopeTransport(QString root);
 bool active()const{return process.state()!=QProcess::NotRunning;}
 void start(QString result,QJsonObject pose);
 void request(QJsonObject pose);
 void setQuality(int level){quality=qBound(0,level,2);}
 void stop(std::function<void()> done={});
};

PlScopeTransport::PlScopeTransport(QString project):QObject(nullptr),process(this),root(project){
 module=qEnvironmentVariable("KV260_SCOPE_MODULE","visualization");
 QString frameDir=QDir("/run/kv260-ui-runtime").exists()?"/run/kv260-ui-runtime":root+"/ui/cache";
 frameFile=frameDir+"/pl_scope_"+QString::number(QCoreApplication::applicationPid())+".rgba";
 process.setWorkingDirectory(root);auto env=QProcessEnvironment::systemEnvironment();env.remove("LD_PRELOAD");env.remove("QT_QPA_PLATFORM");env.insert("PYTHONUNBUFFERED","1");env.insert("OPENBLAS_NUM_THREADS","1");process.setProcessEnvironment(env);
 connect(&process,&QProcess::readyReadStandardOutput,this,[this]{lines();});
 connect(&process,&QProcess::readyReadStandardError,this,[this]{auto text=QString::fromUtf8(process.readAllStandardError());qWarning().noquote()<<text;if(onStatus)onStatus(text.right(160));});
 connect(&process,QOverload<int,QProcess::ExitStatus>::of(&QProcess::finished),this,[this](int code,QProcess::ExitStatus){ready=inFlight=stopping=false;latest={};QFile::remove(frameFile);QFile::remove(frameFile+".normal.rgba");if(onActive)onActive(false,uiIntent);if(code&&onStatus)onStatus(QString::fromUtf8("PL 轮廓进程退出，请查看日志"));auto callbacks=std::move(afterStop);afterStop.clear();for(auto&f:callbacks)if(f)f();});
 connect(&process,&QProcess::errorOccurred,this,[this](QProcess::ProcessError e){if(e==QProcess::FailedToStart){ready=inFlight=stopping=false;if(onActive)onActive(false,uiIntent);if(onStatus)onStatus(process.errorString());auto callbacks=std::move(afterStop);afterStop.clear();for(auto&f:callbacks)if(f)f();}});
}
void PlScopeTransport::start(QString result,QJsonObject pose){
 ++intent;
 if(result.isEmpty()){if(onActive)onActive(false,uiIntent);return;}
 if(active()){
  if(source==result&&!stopping){request(pose);return;}
  stop();const quint64 wanted=++intent;
  afterStop.append([this,result,pose,wanted]{if(wanted==intent)start(result,pose);});return;
 }
 if(module!="visualization"&&module!="surface"){if(onActive)onActive(false,uiIntent);if(onStatus)onStatus(QString::fromUtf8("未知 PL 导航模块"));return;}
 QFile manifest(root+"/dfx/"+module+"/release/manifest.json");
 if(!manifest.open(QIODevice::ReadOnly)){if(onActive)onActive(false,uiIntent);if(onStatus)onStatus(QString::fromUtf8("尚未安装 PL 导航可视化模块"));return;}
 auto release=QJsonDocument::fromJson(manifest.readAll()).object();
 if(module=="surface"&&(!release["offline_verified"].toBool()||!release["board_verified"].toBool()||release["schema"].toString()!="kv260.surface.dfx.v1")){if(onActive)onActive(false,uiIntent);if(onStatus)onStatus(QString::fromUtf8("SDF 导航模块尚未通过板端验证"));return;}
 source=result;ready=inFlight=stopping=false;pending.clear();latest=pose;if(onActive)onActive(true,uiIntent);
 if(onStatus)onStatus(QString::fromUtf8("正在准备 PL 管腔与轮廓"));
 process.start(root+"/.venv/bin/python",{root+"/dfx/"+module+"/worker.py","--result",result,"--frame",frameFile});
}
void PlScopeTransport::request(QJsonObject pose){latest=pose;send();}
void PlScopeTransport::send(){
 if(!ready||inFlight||stopping||latest.isEmpty())return;
 auto req=latest;latest={};req["command"]="frame";req["sequence"]=++sequence;
 if(quality>0&&req["interactive"].toBool()){
  int original=req["width"].toInt(),w=qMin(original,quality==1?384:256),h=qMax(4,int(double(req["height"].toInt())*w/original));
  req["width"]=w;req["height"]=h;
 }
 sentPose=req;roundTrip.restart();process.write(QJsonDocument(req).toJson(QJsonDocument::Compact)+'\n');inFlight=true;
}
void PlScopeTransport::stop(std::function<void()> done){
 ++intent;
 if(!active()){if(onActive)onActive(false,uiIntent);if(done)done();return;}
 if(done)afterStop.append(done);
 latest={};if(!stopping){stopping=true;process.write("{\"command\":\"stop\"}\n");if(onStatus)onStatus(QString::fromUtf8("等待当前 PL 帧完成并释放动态区"));}
}
void PlScopeTransport::lines(){
 pending+=process.readAllStandardOutput();
 while(pending.contains('\n')){
  int i=pending.indexOf('\n');auto line=pending.left(i);pending.remove(0,i+1);auto doc=QJsonDocument::fromJson(line);if(!doc.isObject())continue;auto o=doc.object();QString event=o["event"].toString();
  if(event=="ready"){ready=true;send();}
  else if(event=="error"){if(onStatus)onStatus(o["text"].toString());}
  else if(event=="frame"){
   if(o["sequence"].toInt()!=sentPose["sequence"].toInt()){if(onStatus)onStatus(QString::fromUtf8("PL 帧和镜头序号不匹配，未显示"));continue;}
   o["camera_lps"]=sentPose["camera"];o["arc_mm"]=sentPose["arc_mm"];o["requested_camera"]=sentPose;o["pose_source"]="completed_PL_frame";
   o["pl_module"]=module;
   inFlight=false;int w=o["width"].toInt(),h=o["height"].toInt();QFile f(frameFile);
   o["round_trip_ms"]=double(roundTrip.elapsed());
   if(w>=16&&w<=640&&h>=4&&h<=512&&f.open(QIODevice::ReadOnly)&&f.size()==qint64(w)*h*4){
    auto data=f.readAll();QImage frame(reinterpret_cast<const uchar*>(data.constData()),w,h,w*4,QImage::Format_RGBA8888),normal;
    bool paired=o["normal_computation"].toString()=="PL",valid=true;
    if(paired){
     QFile n(frameFile+".normal.rgba");valid=o["normal_frame_path"].toString()==n.fileName()&&n.open(QIODevice::ReadOnly)&&n.size()==qint64(w)*h*4;
     if(valid){auto bytes=n.readAll();normal=QImage(reinterpret_cast<const uchar*>(bytes.constData()),w,h,w*4,QImage::Format_RGBA8888).copy();}
    }
    // Own both images before sending another request: the worker may reuse files.
    if(valid&&!stopping&&onFrame)onFrame(frame.copy(),normal,o);
    else if(!valid&&onStatus)onStatus(QString::fromUtf8("PL 法线帧尺寸/配对异常，未显示"));
   }
   else if(onStatus)onStatus(QString::fromUtf8("PL 帧尺寸/数据异常，未显示"));
   send();
  }
 }
}


PlScope::PlScope(QString root,QObject*parent):QObject(parent){
 io=new PlScopeTransport(root);io->moveToThread(&ioThread);
 connect(&ioThread,&QThread::finished,io,&QObject::deleteLater);
 io->onActive=[this](bool value,quint64 serial){QMetaObject::invokeMethod(this,[this,value,serial]{if(serial==intent)running=value;},Qt::QueuedConnection);};
 io->onStatus=[this](QString text){QMetaObject::invokeMethod(this,[this,text]{if(onStatus)onStatus(text);},Qt::QueuedConnection);};
 io->onFrame=[this](QImage frame,QImage normal,QJsonObject info){
  // Never accumulate completed images while Qt waits for a display flip.
  QMutexLocker lock(&frameMutex);pendingFrame=std::move(frame);pendingNormal=std::move(normal);pendingInfo=std::move(info);pendingFrameIntent=io->uiIntent;
  if(frameDeliveryQueued)return;frameDeliveryQueued=true;
  QMetaObject::invokeMethod(this,[this]{
   QImage frame,normal;QJsonObject info;quint64 serial;{QMutexLocker lock(&frameMutex);frame=std::move(pendingFrame);normal=std::move(pendingNormal);info=std::move(pendingInfo);serial=pendingFrameIntent;frameDeliveryQueued=false;}
   if(acceptFrames&&serial==intent&&!frame.isNull()&&onFrame)onFrame(frame,normal,info);
  },Qt::QueuedConnection);
 };
 ioThread.setObjectName("PL frame transport");ioThread.start();
}
PlScope::~PlScope(){
 // The normal window-close path already stops safely. Also make destruction
 // cooperative for standalone clients: do not kill an in-flight DMA process.
 QEventLoop done;stop([&done]{done.quit();});done.exec();ioThread.quit();ioThread.wait();
}
void PlScope::start(QString result,QJsonObject pose){
 const auto serial=++intent;running=true;acceptFrames=true;
 QMetaObject::invokeMethod(io,[this,result,pose,serial]{io->uiIntent=serial;io->start(result,pose);},Qt::QueuedConnection);
}
void PlScope::request(QJsonObject pose){QMetaObject::invokeMethod(io,[this,pose]{io->request(pose);},Qt::QueuedConnection);}
void PlScope::setQuality(int level){QMetaObject::invokeMethod(io,[this,level]{io->setQuality(level);},Qt::QueuedConnection);}
void PlScope::stop(std::function<void()> done){
 const auto serial=++intent;acceptFrames=false;{QMutexLocker lock(&frameMutex);pendingFrame={};pendingNormal={};pendingInfo={};}
 QMetaObject::invokeMethod(io,[this,done,serial]{io->uiIntent=serial;io->stop([this,done]{QMetaObject::invokeMethod(this,[done]{if(done)done();},Qt::QueuedConnection);});},Qt::QueuedConnection);
}
