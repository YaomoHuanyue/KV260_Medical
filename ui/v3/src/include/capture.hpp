#pragma once
#include <QtCore>
#include <QtGui>
#include <stdexcept>

namespace medical_capture {
// Removes only this call's named output files; never recursively deletes a parent.
struct PendingCaptureCleanup {
 QDir parent;QString staging;QStringList owned;bool published=false;
 PendingCaptureCleanup(const QDir& p,const QString& s):parent(p),staging(s){}
 ~PendingCaptureCleanup(){
  if(published)return;
  QDir folder(parent.absoluteFilePath(staging));
  if(QFileInfo(folder.absolutePath()).isSymLink())return;
  for(const auto& name:owned)folder.remove(name);
  parent.rmdir(staging);
 }
};

inline QString pixelHash(const QImage& source){
 QImage image=source.convertToFormat(QImage::Format_RGBA8888);
 QCryptographicHash hash(QCryptographicHash::Sha256);
 for(int row=0;row<image.height();++row)
  hash.addData(reinterpret_cast<const char*>(image.constScanLine(row)),image.width()*4);
 return QString::fromLatin1(hash.result().toHex());
}

inline QJsonObject save(const QString& parent,const QMap<QString,QImage>& images,QJsonObject meta){
 if(images.isEmpty())throw std::runtime_error("No completed view to capture");
 QDir dir(parent);if(!dir.exists()&&!QDir().mkpath(parent))throw std::runtime_error("Cannot create snapshot directory");
 QString name=QDateTime::currentDateTimeUtc().toString("yyyyMMdd_HHmmss_zzz")+"_"+
  QUuid::createUuid().toString(QUuid::Id128).left(8);
 QString staging=name+".pending",path=dir.absoluteFilePath(staging);
 if(!dir.mkdir(staging))throw std::runtime_error("Snapshot staging already exists");
 PendingCaptureCleanup cleanup(dir,staging);
 QElapsedTimer clock;clock.start();QJsonObject files;
 for(auto it=images.constBegin();it!=images.constEnd();++it){
  if(it.value().isNull()||!QRegularExpression("^[a-z_]+$").match(it.key()).hasMatch())
   throw std::runtime_error("Invalid snapshot image");
  QString file=it.key()+".png";QImage image=it.value().convertToFormat(QImage::Format_RGBA8888);
  cleanup.owned.append(file);
  QSaveFile output(path+"/"+file);if(!output.open(QIODevice::WriteOnly))throw std::runtime_error("Cannot open PNG");
  QImageWriter writer(&output,"png");writer.setCompression(1);
  if(!writer.write(image)||!output.commit())throw std::runtime_error("PNG save failed");
  QImageReader reader(path+"/"+file,"png");QImage restored=reader.read();
  QString pixels=pixelHash(image);
  if(restored.size()!=image.size()||pixelHash(restored)!=pixels)throw std::runtime_error("PNG roundtrip differs");
  QFile bytes(path+"/"+file);if(!bytes.open(QIODevice::ReadOnly))throw std::runtime_error("Cannot verify saved PNG");
  QCryptographicHash hash(QCryptographicHash::Sha256);if(!hash.addData(&bytes))throw std::runtime_error("Cannot hash PNG");
  files[file]=QJsonObject{{"width",image.width()},{"height",image.height()},
   {"rgba8_pixel_sha256",pixels},{"sha256",QString::fromLatin1(hash.result().toHex())}};
 }
 meta["schema"]="kv260.user_capture.v1";meta["status"]="completed";meta["files"]=files;
 meta["encoding_and_readback_seconds"]=clock.elapsed()/1000.;
 meta["file_serialization_backend"]="PS_worker_thread";meta["additional_PL_resources"]=0;
 cleanup.owned.append("report.json");
 QSaveFile report(path+"/report.json");if(!report.open(QIODevice::WriteOnly))throw std::runtime_error("Cannot open snapshot report");
 QByteArray json=QJsonDocument(meta).toJson(QJsonDocument::Indented);
 if(report.write(json)!=json.size()||!report.commit())throw std::runtime_error("Cannot finish snapshot report");
 if(!dir.rename(staging,name))throw std::runtime_error("Cannot finish snapshot directory");
 cleanup.published=true;
 return {{"path",dir.absoluteFilePath(name)},{"report",meta}};
}
}
