#pragma once
#include <QtWidgets>
#include <QOpenGLWidget>
#include <QCryptographicHash>
#include <QLibrary>
#include <condition_variable>
#include <functional>
#include <memory>
#include <mutex>
#include <thread>
#include <stdexcept>

namespace live_exposure {
inline QString pixels(const QImage& source){
 const QImage image=source.convertToFormat(QImage::Format_RGBA8888);QCryptographicHash h(QCryptographicHash::Sha256);
 for(int y=0;y<image.height();++y)h.addData(reinterpret_cast<const char*>(image.constScanLine(y)),image.width()*4);
 return QString::fromLatin1(h.result().toHex());
}

// One running input, one latest pending input and one coalesced result.
// No FIFO of obsolete camera frames, no hardware/PS fallback selection.
class Worker:public QObject {
 using Function=int(*)(const unsigned char*,size_t,unsigned,unsigned,unsigned,size_t,unsigned char*,size_t,unsigned);
 struct Request{quint64 id;QImage image;};
 struct Result{quint64 id;QImage input,output;QString error;double seconds=0;};
 QLibrary library;Function function=nullptr;std::thread thread;mutable std::mutex mutex;std::condition_variable condition;
 std::unique_ptr<Request> pending;std::unique_ptr<Result> completed;
 bool stopping=false,computing=false,scheduled=false,enabled=true;quint64 epoch=0;
 quint64 submitted=0,replaced=0,computed=0,delivered=0,stale=0;
 void drain(){
  std::unique_ptr<Result> r;{std::lock_guard<std::mutex> lock(mutex);r=std::move(completed);scheduled=false;}
  if(!r)return;
  if(!enabled||r->id!=epoch){++stale;return;}
  ++delivered;if(onDone)onDone(r->id,r->input,r->output,r->error,r->seconds);
 }
 void run(){
  for(;;){
   std::unique_ptr<Request> request;
   {std::unique_lock<std::mutex> lock(mutex);condition.wait(lock,[this]{return stopping||pending;});if(stopping)return;request=std::move(pending);computing=true;}
   auto result=std::make_unique<Result>();result->id=request->id;result->input=std::move(request->image);
   QElapsedTimer timer;timer.start();result->output=QImage(result->input.size(),QImage::Format_RGBA8888);
   int rc=result->output.isNull()?-3:function(result->input.constBits(),size_t(result->input.sizeInBytes()),unsigned(result->input.width()),unsigned(result->input.height()),4,
      size_t(result->input.bytesPerLine()),result->output.bits(),size_t(result->output.sizeInBytes()),4);
   result->seconds=timer.nsecsElapsed()*1e-9;
   if(rc){result->error=QString("PS exposure error %1").arg(rc);result->output=QImage();}
   bool queue=false;
   {std::lock_guard<std::mutex> lock(mutex);computing=false;++computed;if(stopping)return;if(completed)++replaced;completed=std::move(result);if(!scheduled){scheduled=true;queue=true;}}
   if(queue)QMetaObject::invokeMethod(this,[this]{drain();},Qt::QueuedConnection);
  }
 }
public:
 std::function<void(quint64,const QImage&,const QImage&,QString,double)> onDone;
 Worker(QString path,QString expected,QObject*parent=nullptr):QObject(parent),library(path){
  QFile f(path);QCryptographicHash h(QCryptographicHash::Sha256);
  if(expected.size()!=64||!f.open(QIODevice::ReadOnly)||!h.addData(&f)||QString::fromLatin1(h.result().toHex())!=expected)
   throw std::runtime_error("Exposure library differs from qualified build");
  if(!library.load())throw std::runtime_error(library.errorString().toStdString());
  function=reinterpret_cast<Function>(library.resolve("exposure_full"));if(!function)throw std::runtime_error("Missing exposure_full");
  thread=std::thread([this]{run();});
 }
 ~Worker()override{stop();}
 void stop(){
  {std::lock_guard<std::mutex> lock(mutex);stopping=true;pending.reset();completed.reset();}condition.notify_one();
  if(thread.joinable())thread.join();
 }
 void invalidate(){++epoch;std::lock_guard<std::mutex> lock(mutex);if(pending)++replaced;pending.reset();completed.reset();}
 void setEnabled(bool value){enabled=value;invalidate();}
 quint64 submit(const QImage& source){
  if(!enabled)throw std::runtime_error("Disabled exposure queue");
  if(source.width()<1||source.width()>1024||source.height()<1||source.height()>768)throw std::runtime_error("Exposure viewport must be 1..1024 by 1..768; no automatic resizing");
  auto p=std::make_unique<Request>();p->id=++epoch;p->image=source.convertToFormat(QImage::Format_RGBA8888).copy();
  if(p->image.isNull())throw std::runtime_error("Cannot copy exposure input");quint64 id=p->id;
  {std::lock_guard<std::mutex> lock(mutex);if(stopping)throw std::runtime_error("Closed exposure queue");if(pending)++replaced;pending=std::move(p);++submitted;}
  condition.notify_one();return id;
 }
 QJsonObject stats()const{
  std::lock_guard<std::mutex> lock(mutex);
  return {{"submitted",double(submitted)},{"computed",double(computed)},{"delivered",double(delivered)},{"replaced",double(replaced)},{"stale",double(stale)},
   {"pending",bool(pending)},{"computing",computing},{"completed_slot",bool(completed)},
   {"pending_capacity",1},{"completed_capacity",1},{"PS_threads",4},{"backend","explicit_PS4_original_exposure"}};
 }
};

class Overlay:public QObject {
 QPointer<QOpenGLWidget>view;QPointer<QLabel>layer;std::unique_ptr<Worker>worker;QTimer quiet;bool active=false,capturing=false;
 QString lastKey;QImage input,output;quint64 ticket=0;double seconds=0;QString lastError;
 void capture(){
  if(!view||!layer||!active||!view->isVisible()||capturing)return;capturing=true;QImage source=view->grabFramebuffer();capturing=false;
  if(source.isNull())return;
  QString key=QString("%1x%2:").arg(source.width()).arg(source.height())+pixels(source);
  if(key==lastKey)return;layer->hide();input=QImage();output=QImage();lastKey=key;
  try{ticket=worker->submit(source);}
  catch(const std::exception&e){lastKey.clear();lastError=QString::fromUtf8(e.what());if(onStatus)onStatus(false,lastError);}
 }
protected:
 bool eventFilter(QObject*,QEvent*event)override{
  bool moving=event->type()==QEvent::MouseButtonPress||event->type()==QEvent::Wheel||event->type()==QEvent::Resize;
  if(event->type()==QEvent::MouseMove)moving=static_cast<QMouseEvent*>(event)->buttons()!=Qt::NoButton;
  if(event->type()==QEvent::Hide){invalidate();quiet.stop();}
  else if(event->type()==QEvent::Show||moving)invalidate();
  return false;
 }
public:
 std::function<void(bool,QString)>onStatus;
 Overlay(QOpenGLWidget*target,QString library,QString expected):QObject(target),view(target){
  worker=std::make_unique<Worker>(library,expected);layer=new QLabel(view);layer->setAttribute(Qt::WA_TransparentForMouseEvents);layer->setFocusPolicy(Qt::NoFocus);
  layer->setStyleSheet("background:transparent;");layer->hide();layer->lower();
  quiet.setSingleShot(true);quiet.setInterval(50);connect(&quiet,&QTimer::timeout,this,[this]{capture();});
  worker->onDone=[this](quint64 id,const QImage& source,const QImage& result,QString error,double elapsed){
   if(!view||!layer||!active||id!=ticket||!view->isVisible())return;seconds=elapsed;lastError=error;
   if(!error.isEmpty()){layer->hide();lastKey.clear();if(onStatus)onStatus(false,error);return;}
   input=source;output=result;QPixmap pixmap=QPixmap::fromImage(result);pixmap.setDevicePixelRatio(view->devicePixelRatioF());
   layer->setGeometry(view->rect());layer->setPixmap(pixmap);layer->lower();layer->show();if(onStatus)onStatus(true,QString("PS exposure %1 ms").arg(elapsed*1000,0,'f',1));
  };
  view->installEventFilter(this);connect(view,&QOpenGLWidget::frameSwapped,this,[this]{if(active&&!capturing&&!quiet.isActive())quiet.start();});
 }
 ~Overlay()override{if(view)view->removeEventFilter(this);quiet.stop();worker->stop();if(layer)delete layer;}
 void invalidate(){worker->invalidate();ticket=0;lastKey.clear();input=QImage();output=QImage();layer->hide();if(active&&view->isVisible())quiet.start();}
 void setEnabled(bool enabled){active=enabled;worker->setEnabled(enabled);invalidate();}
 bool enabled()const{return active;}
 bool ready()const{return active&&layer->isVisible()&&!output.isNull();}
 const QImage& sourceFrame()const{return input;}
 const QImage& completedFrame()const{return output;}
 QJsonObject stats()const{auto r=worker->stats();r["enabled"]=active;r["visible_completed_frame"]=ready();r["source_pixel_SHA256"]=input.isNull()?QString():pixels(input);r["output_pixel_SHA256"]=output.isNull()?QString():pixels(output);r["compute_seconds"]=seconds;r["error"]=lastError;return r;}
};
}
