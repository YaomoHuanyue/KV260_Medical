#pragma once
#include <QtCore>
#include <functional>
#include <memory>
#include <stdexcept>

// Full, streaming SHA256. No timestamp cache or skipped dependency checks.
namespace navigation_media {
namespace integrity_detail {
struct Context;
struct Digest;
struct Engine;
class Crypto {
 QLibrary library{QStringLiteral("libcrypto.so.3")};
 template<class T> T symbol(const char* name) {
  auto p=library.resolve(name);
  if(!p)throw std::runtime_error("OpenSSL streaming SHA256 symbol unavailable");
  return reinterpret_cast<T>(p);
 }
public:
 Context* (*create)();
 void (*destroy)(Context*);
 const Digest* (*digest)(const char*);
 int (*begin)(Context*,const Digest*,Engine*);
 int (*update)(Context*,const void*,size_t);
 int (*finish)(Context*,unsigned char*,unsigned int*);
 Crypto() {
  library.setLoadHints(QLibrary::ResolveAllSymbolsHint|QLibrary::PreventUnloadHint);
  if(!library.load())throw std::runtime_error("OpenSSL streaming SHA256 library unavailable");
  create=symbol<decltype(create)>("EVP_MD_CTX_new");
  destroy=symbol<decltype(destroy)>("EVP_MD_CTX_free");
  digest=symbol<decltype(digest)>("EVP_get_digestbyname");
  begin=symbol<decltype(begin)>("EVP_DigestInit_ex");
  update=symbol<decltype(update)>("EVP_DigestUpdate");
  finish=symbol<decltype(finish)>("EVP_DigestFinal_ex");
 }
};
}
inline QString streamingFileSHA256(const QString& path,
 const std::function<void(qint64)>& progress={}) {
 QFile file(path);
 if(!QFileInfo(path).isFile()||!file.open(QIODevice::ReadOnly))
  throw std::runtime_error("Cannot open streaming SHA256 source");
 static const integrity_detail::Crypto crypto;
 std::unique_ptr<integrity_detail::Context,decltype(crypto.destroy)>
  context(crypto.create(),crypto.destroy);
 auto digest=crypto.digest("SHA256");
 if(!context||!digest||crypto.begin(context.get(),digest,nullptr)!=1)
  throw std::runtime_error("Cannot initialize streaming SHA256");
 QByteArray buffer(1024*1024,Qt::Uninitialized);
 while(true) {
  const qint64 count=file.read(buffer.data(),buffer.size());
  if(count<0)throw std::runtime_error("Cannot read complete streaming SHA256 source");
  if(!count)break;
  if(crypto.update(context.get(),buffer.constData(),size_t(count))!=1)
   throw std::runtime_error("Cannot update streaming SHA256");
  if(progress)progress(count);
 }
 unsigned char result[64];unsigned int bytes=0;
 if(crypto.finish(context.get(),result,&bytes)!=1||bytes!=32)
  throw std::runtime_error("Cannot finish streaming SHA256");
 return QString::fromLatin1(QByteArray(reinterpret_cast<const char*>(result),int(bytes)).toHex());
}
}
