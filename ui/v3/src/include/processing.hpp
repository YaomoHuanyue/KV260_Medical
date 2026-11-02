#pragma once
#include "async_exposure.hpp"

namespace endoscope_exposure {
// The same source-bound pixel operation is used by live display and exports.
// Export buffers are completed offscreen GL colors, before captions are drawn.
class Processor {
 using Function=int(*)(const unsigned char*,size_t,unsigned,unsigned,unsigned,size_t,unsigned char*,size_t,unsigned);
 QLibrary library;Function function=nullptr;
public:
 Processor(QString path,QString expected):library(path){
  QFile file(path);QCryptographicHash hash(QCryptographicHash::Sha256);
  if(expected.size()!=64||!file.open(QIODevice::ReadOnly)||!hash.addData(&file)||QString::fromLatin1(hash.result().toHex())!=expected)
   throw std::runtime_error("Exposure library differs from qualified build");
  if(!library.load())throw std::runtime_error(library.errorString().toStdString());
  function=reinterpret_cast<Function>(library.resolve("exposure_full"));if(!function)throw std::runtime_error("Missing exposure_full");
 }
 QImage apply(const QImage& source)const{
  auto input=source.convertToFormat(QImage::Format_RGBA8888);QImage output(input.size(),QImage::Format_RGBA8888);
  if(input.isNull()||output.isNull())throw std::runtime_error("Exposure image allocation failed");
  int rc=function(input.constBits(),size_t(input.sizeInBytes()),unsigned(input.width()),unsigned(input.height()),4,
    size_t(input.bytesPerLine()),output.bits(),size_t(output.sizeInBytes()),4);
  if(rc)throw std::runtime_error(("Original exposure failed: "+QString::number(rc)).toStdString());
  return output;
 }
};
}
