#pragma once
#include "frame_r1.hpp"

namespace navigation_media {
inline QImage linkedVideoFrame(const QImage&overview,const QImage&native,QSize pane,
                              QJsonObject pose,QJsonObject hud,double total){
 if(overview.size()!=QSize(640,360))throw std::runtime_error("Linked overview native size changed");
 QImage scope=videoFrame(native,pane,pose,hud,total);
 QImage output(QSize(pane.width()*2,pane.height()),QImage::Format_RGBA8888);output.fill(QColor("#07121e"));
 QPainter painter(&output);
 painter.drawImage(QRect(QPoint(0,0),pane),overview);
 painter.drawImage(QPoint(pane.width(),0),scope);painter.end();return output;
}
}
