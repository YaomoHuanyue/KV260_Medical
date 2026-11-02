#pragma once
#include <QVector>
#include <QVector3D>
#include <QQuaternion>
#include <algorithm>
#include <cmath>

// Presentation of the verified PL route. Position stays on its original
// polyline; only viewing orientation is smoothed in physical arc distance.
class NavigationCamera {
 QVector<QVector3D> points;
 QVector<float> arcs;
 QVector<QQuaternion> rotations;
 static QVector3D orthogonalUp(QVector3D f,QVector3D u){
  u-=f*QVector3D::dotProduct(f,u);
  if(u.lengthSquared()<1e-10f){QVector3D axis;
   int k=0;if(std::abs(f.y())<std::abs(f[k]))k=1;if(std::abs(f.z())<std::abs(f[k]))k=2;
   axis[k]=1;u=axis-f*QVector3D::dotProduct(axis,f);
  }
  return u.normalized();
 }
public:
 struct Pose{QVector3D position,forward,up;};
 bool load(const QVector<QVector3D>&p,const QVector<QVector3D>&forward,const QVector<QVector3D>&up,const QVector<float>&a){
  points.clear();arcs.clear();rotations.clear();
  if(p.isEmpty()||p.size()!=forward.size()||p.size()!=up.size()||p.size()!=a.size())return false;
  for(int i=0;i<a.size();++i){
   if(!std::isfinite(a[i])||(i&&a[i]<=a[i-1])||forward[i].lengthSquared()<1e-10f)return false;
   for(int j=0;j<3;++j)if(!std::isfinite(p[i][j])||!std::isfinite(forward[i][j])||!std::isfinite(up[i][j]))return false;
  }
  points=p;arcs=a;QVector<QVector3D> raw=forward,smooth;QVector<float> cell(a.size(),1.f);
  for(auto&f:raw)f.normalize();
  // The final PL record changes from an ahead chord to a behind chord.
  // Keep the approaching orientation there to avoid an end-of-route snap.
  if(raw.size()>1)raw.last()=raw[raw.size()-2];
  if(a.size()>1){cell[0]=(a[1]-a[0])*.5f;cell.last()=(a.last()-a[a.size()-2])*.5f;
   for(int i=1;i<a.size()-1;++i)cell[i]=(a[i+1]-a[i-1])*.5f;
  }
  constexpr float sigma=1.2f,extent=3*sigma;
  for(int i=0;i<a.size();++i){
   auto lo=std::lower_bound(a.begin(),a.end(),a[i]-extent),hi=std::upper_bound(a.begin(),a.end(),a[i]+extent);
   QVector3D f;for(auto it=lo;it!=hi;++it){int k=int(it-a.begin());float d=(*it-a[i])/sigma;f+=raw[k]*(cell[k]*std::exp(-.5f*d*d));}
   smooth.append(f.lengthSquared()>1e-10f?f.normalized():raw[i]);
  }
  QVector3D previousUp=orthogonalUp(smooth[0],up[0]);
  for(int i=0;i<a.size();++i){
   auto f=smooth[i];
   if(i){auto prev=smooth[i-1];float dot=QVector3D::dotProduct(prev,f);
    auto turn=dot<-.99999f?QQuaternion::fromAxisAndAngle(previousUp,180):QQuaternion::rotationTo(prev,f);
    previousUp=orthogonalUp(f,turn.rotatedVector(previousUp));
   }
   rotations.append(QQuaternion::fromAxes(QVector3D::crossProduct(previousUp,f).normalized(),previousUp,f).normalized());
  }
  return true;
 }
 Pose at(float distance)const{
  if(points.isEmpty())return {};
  distance=std::isfinite(distance)?qBound(arcs.first(),distance,arcs.last()):arcs.first();
  int high=qMin(int(std::upper_bound(arcs.begin(),arcs.end(),distance)-arcs.begin()),arcs.size()-1),low=qMax(0,high-1);
  float t=high==low?0:qBound(0.f,(distance-arcs[low])/(arcs[high]-arcs[low]),1.f);
  auto q=QQuaternion::slerp(rotations[low],rotations[high],t);
  return {points[low]*(1-t)+points[high]*t,q.rotatedVector(QVector3D(0,0,1)),q.rotatedVector(QVector3D(0,1,0))};
 }
};
