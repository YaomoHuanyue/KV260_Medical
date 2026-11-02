#pragma once
#include <QtWidgets>
#include <thread>
#include <condition_variable>
#include <mutex>
#include <functional>

namespace navigation_media {
// One owned image at a time. Pipe backpressure and encoding never block Qt.
class Encoder {
 QObject*target;std::thread thread;std::mutex mutex;std::condition_variable changed;
 QImage image;QMap<QString,QByteArray> sideFiles;QString referencePNG;bool pending=false,finishing=false;QString path,codec;QSize size;int rate;
 std::function<void(QString)> ready,encoded,finished;
 void deliver(std::function<void(QString)> f,QString text){
  QMetaObject::invokeMethod(target,[f,text]{if(f)f(text);},Qt::QueuedConnection);
 }
 void work(){
  QProcess process;QString error;bool notified=false;
  try{
   auto env=QProcessEnvironment::systemEnvironment();env.remove("LD_PRELOAD");env.remove("QT_QPA_PLATFORM");
   process.setProcessEnvironment(env);process.setProcessChannelMode(QProcess::MergedChannels);
   process.start(codec,{"-nostdin","-hide_banner","-loglevel","error","-n",
    "-f","rawvideo","-pixel_format","rgb24","-video_size",QString("%1x%2").arg(size.width()).arg(size.height()),
    "-framerate",QString::number(rate),"-i","pipe:0","-an","-c:v","libx264","-threads","2",
    "-preset","veryfast","-crf","18","-pix_fmt","yuv420p","-movflags","+faststart",path});
   if(!process.waitForStarted(10000))throw std::runtime_error("Cannot start FFmpeg");
   deliver(ready,{});notified=true;
   while(true){
    QImage next;QMap<QString,QByteArray> extras;QString png;
    {std::unique_lock<std::mutex> lock(mutex);changed.wait(lock,[this]{return pending||finishing;});
     if(!pending)break;next=std::move(image);extras=std::move(sideFiles);png=std::move(referencePNG);pending=false;}
    if(next.size()!=size)throw std::runtime_error("Encoder frame dimensions changed");
    for(auto it=extras.begin();it!=extras.end();++it){
     if(!QRegularExpression("^reference_[0-9]{6}\\.(depth|normal)\\.rgba$").match(it.key()).hasMatch())throw std::runtime_error("Invalid reference filename");
     QSaveFile file(QFileInfo(path).dir().filePath(it.key()));if(!file.open(QIODevice::WriteOnly)||file.write(it.value())!=it.value().size()||!file.commit())throw std::runtime_error("Cannot save raw PL reference");
    }
    if(!png.isEmpty()){
     if(!QRegularExpression("^reference_[0-9]{6}\\.png$").match(png).hasMatch())throw std::runtime_error("Invalid PNG filename");
     QSaveFile file(QFileInfo(path).dir().filePath(png));if(!file.open(QIODevice::WriteOnly))throw std::runtime_error("Cannot save PNG reference");
     QImageWriter writer(&file,"png");writer.setCompression(1);if(!writer.write(next)||!file.commit())throw std::runtime_error("Cannot commit PNG reference");
    }
    next=next.convertToFormat(QImage::Format_RGB888);
    QByteArray packed;packed.reserve(size.width()*size.height()*3);
    for(int y=0;y<size.height();++y)packed.append(reinterpret_cast<const char*>(next.constScanLine(y)),size.width()*3);
    if(process.write(packed)!=packed.size())throw std::runtime_error("FFmpeg pipe rejected a frame");
    while(process.bytesToWrite()){
     if(!process.waitForBytesWritten(30000))throw std::runtime_error("FFmpeg pipe stalled");
     error+=QString::fromUtf8(process.readAll());
    }
    if(process.state()==QProcess::NotRunning)throw std::runtime_error("FFmpeg ended before the complete route");
    deliver(encoded,{});
   }
   process.closeWriteChannel();
   if(!process.waitForFinished(120000))throw std::runtime_error("FFmpeg did not finish");
   error+=QString::fromUtf8(process.readAll());
   if(process.exitStatus()!=QProcess::NormalExit||process.exitCode())throw std::runtime_error(error.toStdString());
   deliver(finished,{});return;
  }catch(const std::exception&e){error+=QString::fromUtf8(e.what());}
  // FFmpeg is a CPU codec, never an XRT/DMA child. First close its input.
  if(process.state()!=QProcess::NotRunning){process.closeWriteChannel();
   if(!process.waitForFinished(5000)){process.terminate();if(!process.waitForFinished(5000)){process.kill();process.waitForFinished();}}}
  if(!notified)deliver(ready,error);else deliver(finished,error);
 }
public:
 Encoder(QObject*t,QString file,QSize dimensions,int fps,std::function<void(QString)> onReady,
         std::function<void(QString)> onEncoded,std::function<void(QString)> onFinished,QString executable="/usr/bin/ffmpeg")
  :target(t),path(file),codec(executable),size(dimensions),rate(fps),ready(onReady),encoded(onEncoded),finished(onFinished){thread=std::thread([this]{work();});}
 ~Encoder(){finish();if(thread.joinable())thread.join();}
 void submit(QImage frame,QMap<QString,QByteArray> extras={},QString png={}){std::lock_guard<std::mutex> lock(mutex);
  if(pending||finishing)throw std::runtime_error("Unbounded or late encoder submission");
  image=std::move(frame);sideFiles=std::move(extras);referencePNG=std::move(png);pending=true;changed.notify_one();}
 void finish(){std::lock_guard<std::mutex> lock(mutex);finishing=true;changed.notify_one();}
};
}
