#include "pl_composite.hpp"
#include <QCryptographicHash>
class PlCompositeTransport : public QObject {
 QProcess process;QString root,source,frameFile;QByteArray sourceHash,pending;
 QJsonObject latest,submitted;bool ready=false,inFlight=false,stopping=false;int sequence=0;quint64 restartIntent=0;
 QVector<std::function<void()>>afterStop;QElapsedTimer roundTrip;
 void send();void lines();bool verifiedWorker(QString&error);
public:
 quint64 uiIntent=0;
 std::function<void(QImage,QJsonObject)>onFrame;
 std::function<void(QString)>onStatus;
 std::function<void(bool,quint64)>onActive;
 explicit PlCompositeTransport(QString project);
 bool active()const{return process.state()!=QProcess::NotRunning;}
 void start(QString scene,QJsonObject state);
 void request(QJsonObject state){latest=state;send();}
 void stop(std::function<void()>done={});
};
static QByteArray compositeFileSHA(QString path){QFile f(path);if(!f.open(QIODevice::ReadOnly))return {};QCryptographicHash hash(QCryptographicHash::Sha256);if(!hash.addData(&f))return {};return hash.result().toHex();}
bool PlCompositeTransport::verifiedWorker(QString&error){
 QString current=root+"/dfx/composite/docs/medical_active_layers_acceptance_r2.json";
 bool activeLayerRelease=QFile::exists(current);QFile receipt(activeLayerRelease?current:root+"/dfx/composite/docs/medical_controls_acceptance_r9.json");
 if(!receipt.open(QIODevice::ReadOnly)){error=QString::fromUtf8("透明合成控件尚未通过板测");return false;}
 auto accepted=QJsonDocument::fromJson(receipt.readAll()).object();
 QString expected=activeLayerRelease?"passed_active_layers_own_CT_structure_controls_exact_PS_PL":"passed_all_controls_original_CT_geometry_palette_composition_and_cache_guards";
 if(accepted["status"].toString()!=expected){
  error=QString::fromUtf8("透明合成控件验收记录无效");return false;}
 QFile metadata(root+"/dfx/composite/medical/interactive/build.json");
 if(!metadata.open(QIODevice::ReadOnly)){error=QString::fromUtf8("缺少透明合成进程的构建记录");return false;}
 auto build=QJsonDocument::fromJson(metadata.readAll()).object();
 if(build!=accepted["build"].toObject()||compositeFileSHA(root+"/dfx/composite/build/medical_composite_worker")!=build["binary_sha256"].toString().toLatin1()){
  error=QString::fromUtf8("透明合成程序与已验收版本不一致");return false;}
 for(const char*group:{"source_sha256","library_sha256"}){
  auto hashes=build[group].toObject();if(hashes.isEmpty()){error=QString::fromUtf8("透明合成版本记录不完整");return false;}
  for(auto i=hashes.begin();i!=hashes.end();++i)if(compositeFileSHA(root+"/"+i.key())!=i.value().toString().toLatin1()){
   error=QString::fromUtf8("透明合成源或库已改变，请重新验证");return false;}
 }
 return true;
}
PlCompositeTransport::PlCompositeTransport(QString project):QObject(nullptr),process(this),root(project){
 QString directory=QDir("/run/kv260-ui-runtime").exists()?"/run/kv260-ui-runtime":root+"/ui/cache";
 frameFile=directory+"/pl_composite_"+QString::number(QCoreApplication::applicationPid())+".rgba";
 process.setWorkingDirectory(root+"/dfx/medical");auto env=QProcessEnvironment::systemEnvironment();env.remove("QT_QPA_PLATFORM");
 env.insert("LD_PRELOAD","/usr/lib/aarch64-linux-gnu/mali/wayland/libMali.so.9.0");process.setProcessEnvironment(env);
 connect(&process,&QProcess::readyReadStandardOutput,this,[this]{lines();});
 connect(&process,&QProcess::readyReadStandardError,this,[this]{qWarning().noquote()<<QString::fromUtf8(process.readAllStandardError());});
 connect(&process,QOverload<int,QProcess::ExitStatus>::of(&QProcess::finished),this,[this](int code,QProcess::ExitStatus){
  ready=inFlight=stopping=false;latest={};QFile::remove(frameFile);if(onActive)onActive(false,uiIntent);
  if(code&&onStatus)onStatus(QString::fromUtf8("透明合成进程退出，保留上一张完成的画面"));
  auto callbacks=std::move(afterStop);afterStop.clear();for(auto&f:callbacks)if(f)f();
 });
 connect(&process,&QProcess::errorOccurred,this,[this](QProcess::ProcessError e){if(e==QProcess::FailedToStart){
  ready=inFlight=stopping=false;if(onActive)onActive(false,uiIntent);if(onStatus)onStatus(process.errorString());
  auto callbacks=std::move(afterStop);afterStop.clear();for(auto&f:callbacks)if(f)f();
 }});
}
void PlCompositeTransport::start(QString scene,QJsonObject state){
 auto digest=compositeFileSHA(scene);++restartIntent;
 if(digest.isEmpty()){stop();if(onStatus)onStatus(QString::fromUtf8("医疗场景文件不可读取"));return;}
 if(active()){
  if(source==scene&&sourceHash==digest&&!stopping){request(state);return;}
  stop();const auto expected=++restartIntent;afterStop.append([this,scene,state,expected]{if(expected==restartIntent)start(scene,state);});return;
 }
 QString error;if(!verifiedWorker(error)){if(onActive)onActive(false,uiIntent);if(onStatus)onStatus(error);return;}
 source=scene;sourceHash=digest;ready=inFlight=stopping=false;pending.clear();latest=state;
 if(onActive)onActive(true,uiIntent);if(onStatus)onStatus(QString::fromUtf8("正在准备 PL 透明合成"));
 process.start(root+"/dfx/composite/build/medical_composite_worker",{scene,frameFile});
}
void PlCompositeTransport::send(){
 if(!ready||inFlight||stopping||latest.isEmpty())return;auto request=latest;latest={};
 request["command"]="frame";request["sequence"]=++sequence;submitted=request;roundTrip.restart();
 if(onStatus)onStatus(QString::fromUtf8("正在计算新视角，保留上一张完成画面"));
 process.write(QJsonDocument(request).toJson(QJsonDocument::Compact)+'\n');inFlight=true;
}
void PlCompositeTransport::stop(std::function<void()>done){
 ++restartIntent;latest={};if(!active()){if(onActive)onActive(false,uiIntent);if(done)done();return;}
 if(done)afterStop.append(done);if(!stopping){stopping=true;process.write("{\"command\":\"stop\"}\n");
  if(onStatus)onStatus(QString::fromUtf8("等待合成完成并释放动态区"));}
}
void PlCompositeTransport::lines(){
 pending+=process.readAllStandardOutput();while(pending.contains('\n')){
  auto end=pending.indexOf('\n');auto line=pending.left(end);pending.remove(0,end+1);auto document=QJsonDocument::fromJson(line);if(!document.isObject())continue;
  auto info=document.object();auto event=info["event"].toString();
  if(event=="ready"){ready=true;send();}
  else if(event=="error"){if(onStatus)onStatus(info["text"].toString());}
  else if(event=="frame"){
   bool expected=inFlight&&info["sequence"].toInt(-1)==sequence;inFlight=false;int w=info["width"].toInt(),h=info["height"].toInt();QFile f(frameFile);
   bool valid=expected&&w==submitted["width"].toInt()&&h==submitted["height"].toInt()&&w>=16&&w<=640&&w%16==0&&h>=4&&h<=512&&info["frame_path"].toString()==frameFile&&info["scene"].toString()==source&&
    info["report"].toObject()["scene_sha256"].toString().toLatin1()==sourceHash&&f.open(QIODevice::ReadOnly)&&f.size()==qint64(w)*h*4;
   if(valid){auto bytes=f.readAll();QImage frame(reinterpret_cast<const uchar*>(bytes.constData()),w,h,w*4,QImage::Format_RGBA8888);
    info["pl_module"]="composite";info["transport_round_trip_ms"]=roundTrip.elapsed();
    if(!stopping&&onFrame)onFrame(frame.copy(),info); // Own pixels before reusing the worker output file.
   }else if(onStatus)onStatus(QString::fromUtf8("透明合成帧/场景配对无效，未显示"));
   send();
  }
 }
}
PlComposite::PlComposite(QString root,QObject*parent):QObject(parent){
 io=new PlCompositeTransport(root);io->moveToThread(&ioThread);connect(&ioThread,&QThread::finished,io,&QObject::deleteLater);
 io->onActive=[this](bool value,quint64 serial){QMetaObject::invokeMethod(this,[this,value,serial]{if(serial==intent)running=value;},Qt::QueuedConnection);};
 io->onStatus=[this](QString text){QMetaObject::invokeMethod(this,[this,text]{if(onStatus)onStatus(text);},Qt::QueuedConnection);};
 io->onFrame=[this](QImage frame,QJsonObject info){QMutexLocker lock(&frameMutex);pendingFrame=std::move(frame);pendingInfo=std::move(info);pendingIntent=io->uiIntent;
  if(queued)return;queued=true;QMetaObject::invokeMethod(this,[this]{QImage frame;QJsonObject info;quint64 serial;
   {QMutexLocker lock(&frameMutex);frame=std::move(pendingFrame);info=std::move(pendingInfo);serial=pendingIntent;queued=false;}
   if(acceptFrames&&serial==intent&&!frame.isNull()&&onFrame)onFrame(frame,info);
  },Qt::QueuedConnection);
 };ioThread.setObjectName("PL composite transport");ioThread.start();
}
PlComposite::~PlComposite(){QEventLoop done;stop([&done]{done.quit();});done.exec();ioThread.quit();ioThread.wait();}
void PlComposite::start(QString scene,QJsonObject state){auto serial=++intent;acceptFrames=running=true;
 QMetaObject::invokeMethod(io,[this,scene,state,serial]{io->uiIntent=serial;io->start(scene,state);},Qt::QueuedConnection);}
void PlComposite::request(QJsonObject state){QMetaObject::invokeMethod(io,[this,state]{io->request(state);},Qt::QueuedConnection);}
void PlComposite::stop(std::function<void()>done){auto serial=++intent;acceptFrames=false;
 {QMutexLocker lock(&frameMutex);pendingFrame={};pendingInfo={};}
 QMetaObject::invokeMethod(io,[this,serial,done]{io->uiIntent=serial;io->stop([this,done]{QMetaObject::invokeMethod(this,[done]{if(done)done();},Qt::QueuedConnection);});},Qt::QueuedConnection);}
