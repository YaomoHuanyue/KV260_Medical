#pragma once
#include <QtWidgets>
#include <stdexcept>

namespace navigation_media {
inline QByteArray rgbaBytes(const QImage& source){
 QImage image=source.convertToFormat(QImage::Format_RGBA8888);QByteArray bytes;
 bytes.reserve(image.width()*image.height()*4);
 for(int y=0;y<image.height();++y)bytes.append(reinterpret_cast<const char*>(image.constScanLine(y)),image.width()*4);
 return bytes;
}
// Export the native C6 shading framebuffer directly, independent of UI layout.
inline QImage videoFrame(const QImage& native,QSize output,QJsonObject pose,QJsonObject hud,double total){
 if(native.size()!=QSize(640,360)||output.width()*9!=output.height()*16)throw std::runtime_error("Video frame aspect or native dimensions changed");
 QImage image=native.scaled(output,Qt::KeepAspectRatio,Qt::SmoothTransformation).convertToFormat(QImage::Format_RGBA8888);
 QPainter p(&image);double scale=output.width()/640.;p.scale(scale,scale);
 p.fillRect(QRectF(0,0,640,hud.isEmpty()?30:76),QColor(7,18,30,210));QFont font("Noto Sans CJK SC");font.setPixelSize(12);p.setFont(font);
 p.setPen(QColor("#fff0aa"));p.drawText(12,20,QString::fromUtf8("导航路径 · %1 / %2 mm").arg(pose["arc_mm"].toDouble(),0,'f',1).arg(total,0,'f',1));
 if(!hud.isEmpty()){
  QString state=hud["state"].toString();p.setPen(state=="blocked"?QColor("#ff6262"):state=="caution"?QColor("#ffdc79"):QColor("#5bf3ab"));
  p.drawText(12,42,QString::fromUtf8("当前管径 %1 mm · 前方 10 mm 保守管径 %2 mm").arg(hud["current_diameter_mm"].toDouble(),0,'f',2).arg(hud["forward_adjusted_diameter_mm"].toDouble(),0,'f',2));
  p.drawText(12,64,QString::fromUtf8("模型余量 %1 mm · 图像几何估算").arg(hud["spare_radius_mm"].toDouble(),0,'f',2));
 }
 p.end();return image;
}
}
