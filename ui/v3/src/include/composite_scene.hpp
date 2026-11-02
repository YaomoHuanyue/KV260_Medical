#pragma once
#include <QtCore>
#include <stdexcept>
namespace composite_sampling {
inline QString hash(QString path){
 QFile f(path);if(!f.open(QIODevice::ReadOnly))throw std::runtime_error(("Cannot read scalar binding asset: "+path).toStdString());
 QCryptographicHash h(QCryptographicHash::Sha256);if(!h.addData(&f))throw std::runtime_error("Cannot hash scalar binding asset");
 return QString::fromLatin1(h.result().toHex());
}
}
