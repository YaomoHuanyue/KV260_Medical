#pragma once
#include <QJsonArray>
#include <QJsonObject>
#include <QQuaternion>
#include <QVector3D>
#include <algorithm>
#include <cmath>

namespace medical_gamepad {
class ManualCamera {
 bool active_=false;QVector3D forward_{0,0,-1},up_{0,1,0};float yaw_=0,pitch_=0;
 static bool finite(QVector3D v){return std::isfinite(v.x())&&std::isfinite(v.y())&&std::isfinite(v.z());}
 static QJsonArray array(QVector3D v){return {v.x(),v.y(),v.z()};}
public:
 bool active()const{return active_;}float yaw()const{return yaw_;}float pitch()const{return pitch_;}
 void disable(){active_=false;yaw_=pitch_=0;}
 bool enter(QVector3D forward,QVector3D up){
  if(!finite(forward)||!finite(up)||forward.lengthSquared()<1e-8)return false;
  forward.normalize();up-=forward*QVector3D::dotProduct(forward,up);
  if(up.lengthSquared()<1e-8)return false;
  forward_=forward;up_=up.normalized();yaw_=pitch_=0;active_=true;return true;
 }
 bool turn(float yaw,float pitch){
  if(!active_||!std::isfinite(yaw)||!std::isfinite(pitch))return false;
  float nextYaw=std::remainder(yaw_+yaw,360.f),nextPitch=std::clamp(pitch_+pitch,-75.f,75.f);
  if(nextYaw==yaw_&&nextPitch==pitch_)return false;
  yaw_=nextYaw;pitch_=nextPitch;return true;
 }
 std::pair<QVector3D,QVector3D> basis()const{
  auto yaw=QQuaternion::fromAxisAndAngle(up_,-yaw_);auto f=yaw.rotatedVector(forward_);
  auto right=QVector3D::crossProduct(f,up_).normalized();auto pitch=QQuaternion::fromAxisAndAngle(right,pitch_);
  return {pitch.rotatedVector(f).normalized(),pitch.rotatedVector(up_).normalized()};
 }
 QJsonObject state()const{return {{"active",active_},{"base_forward",array(forward_)},{"base_up",array(up_)},{"yaw",yaw_},{"pitch",pitch_}};}
 bool restore(QJsonObject state){
  if(!state["active"].isBool())return false;
  if(!state["active"].toBool()){disable();return true;}
  auto f=state["base_forward"].toArray(),u=state["base_up"].toArray();
  if(f.size()!=3||u.size()!=3||!state["yaw"].isDouble()||!state["pitch"].isDouble())return false;
  for(auto a:{f,u})for(auto v:a)if(!v.isDouble()||!std::isfinite(v.toDouble()))return false;
  double yaw=state["yaw"].toDouble(),pitch=state["pitch"].toDouble();
  if(!std::isfinite(yaw)||!std::isfinite(pitch)||std::abs(pitch)>75||std::abs(yaw)>180.001)return false;
  ManualCamera next;
  if(!next.enter({float(f[0].toDouble()),float(f[1].toDouble()),float(f[2].toDouble())},{float(u[0].toDouble()),float(u[1].toDouble()),float(u[2].toDouble())}))return false;
  next.yaw_=yaw;next.pitch_=pitch;*this=next;return true;
 }
};
}
