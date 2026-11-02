#pragma once
#include <QJsonObject>
#include <QJsonArray>
#include <QVector3D>
#include <array>
#include <cmath>

// The pose of a completed PL image, including the worker's normalized axes
// and the actual viewport/FOV. It is independent of the next requested pose.
struct ScopeReference {
 bool valid=false;int sequence=0;float arc=0,field=0,aspect=1;
 QVector3D eye,forward,right,up;
 static bool vector(QJsonValue value,QVector3D&out){
  auto a=value.toArray();if(a.size()!=3)return false;
  for(int i=0;i<3;++i){if(!a[i].isDouble()||!std::isfinite(a[i].toDouble()))return false;out[i]=float(a[i].toDouble());if(!std::isfinite(out[i]))return false;}
  return true;
 }
 static ScopeReference fromFrame(const QJsonObject&frame){
  ScopeReference p;int w=frame["width"].toInt(),h=frame["height"].toInt();
  p.sequence=frame["sequence"].toInt();p.arc=float(frame["arc_mm"].toDouble());p.field=float(frame["field"].toDouble());
  if(frame["pose_source"].toString()!="completed_PL_frame"||p.sequence<=0||w<16||h<4||!std::isfinite(p.arc)||!std::isfinite(p.field)||p.field<=0||p.field>10)return p;
  if(!vector(frame["camera_lps"],p.eye)||!vector(frame["forward_lps"],p.forward)||!vector(frame["right_lps"],p.right)||!vector(frame["up_lps"],p.up))return p;
  for(auto v:{p.forward,p.right,p.up})if(std::abs(v.lengthSquared()-1)>1e-3f)return p;
  if((QVector3D::crossProduct(p.forward,p.up)-p.right).length()>1e-3f)return p;
  if(std::abs(QVector3D::dotProduct(p.forward,p.up))>1e-3f)return p;
  p.aspect=float(w)/h;p.valid=true;return p;
 }
 std::array<QVector3D,4> corners(float depth=15.f)const{
  auto c=eye+forward*depth;float vertical=depth*field,horizontal=vertical*aspect;
  return {{c+right*horizontal+up*vertical,c-right*horizontal+up*vertical,
           c-right*horizontal-up*vertical,c+right*horizontal-up*vertical}};
 }
};
