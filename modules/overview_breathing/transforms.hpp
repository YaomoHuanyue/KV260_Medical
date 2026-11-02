#pragma once
// Display-only transforms. Mask data, reconstructed vertices and navigation
// coordinates remain immutable. The pivot follows the legacy mask-content box.
#include <QFile>
#include <QFileInfo>
#include <QDir>
#include <QJsonArray>
#include <QJsonObject>
#include <QMatrix4x4>
#include <QCryptographicHash>
#include <array>
#include <algorithm>
#include <climits>
#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>

namespace overview_breathing {
inline void require(bool ok,const char*message){if(!ok)throw std::invalid_argument(message);}
inline double number(const QJsonObject&o,const char*key,double fallback,double lo,double hi){
 if(!o.contains(key))return fallback;
 require(o[key].isDouble(),"Breathing number required");double v=o[key].toDouble();
 require(std::isfinite(v)&&v>=lo&&v<=hi,"Breathing number out of range");return v;
}
struct State {
 bool enabled=false;double phase=0;
 static State parse(const QJsonValue&value){
  if(value.isUndefined())return {};
  require(value.isObject(),"Breathing controls must be an object");auto o=value.toObject();
  for(auto it=o.begin();it!=o.end();++it)require(it.key()=="enabled"||it.key()=="phase_radians","Unknown breathing field");
  require(!o.contains("enabled")||o["enabled"].isBool(),"Breathing enabled must be boolean");
  return {o["enabled"].toBool(false),number(o,"phase_radians",0,-1e6,1e6)};
 }
 QJsonObject json()const{return {{"enabled",enabled},{"phase_radians",enabled?phase:0.}};}
};
using Point=std::array<double,3>;
inline QJsonArray jsonPoint(const Point&p){return {p[0],p[1],p[2]};}
struct Transform {
 double scale=1;Point shift{{0,0,0}},pivot{{0,0,0}};
 Point map(const Point&p)const {Point out{};for(int k=0;k<3;++k)out[k]=pivot[k]+scale*(p[k]-pivot[k])+shift[k];return out;}
 QMatrix4x4 matrix()const {
  // Form the affine offset in double before narrowing once to GLES floats.
  // Identity stays exactly identity, including very large patient origins.
  QMatrix4x4 m;for(int k=0;k<3;++k){m(k,k)=float(scale);m(k,3)=float((1.-scale)*pivot[k]+shift[k]);}return m;
 }
 QJsonObject json()const {QJsonArray m;auto a=matrix();for(int k=0;k<16;++k)m.append(a.constData()[k]);
  return {{"scale",scale},{"translation_lps_mm",jsonPoint(shift)},{"pivot_lps_mm",jsonPoint(pivot)},{"matrix_column_major",m}};}
};
// Slots match the semantic order lung, airway, lesion (called nodule in the UI).
inline Transform transform(unsigned slot,const Point&pivot,State state){
 require(slot<3,"Unknown breathing layer");require(std::isfinite(state.phase)&&std::abs(state.phase)<=1e6,"Invalid breathing phase");
 double wave=state.enabled?std::sin(state.phase):0.;const double scales[3]={.018,.005,0},shifts[3]={-2.,-.8,-1.2};
 return {1.+scales[slot]*wave,{{0,0,shifts[slot]*wave}},pivot};
}
struct Bounds {
 uint64_t count=0;std::array<int,3>lo{{INT_MAX,INT_MAX,INT_MAX}},hi{{-1,-1,-1}};Point center{{0,0,0}};
};
struct Pivots {
 std::array<Bounds,3>layers;QString maskPath,maskSHA;QJsonObject geometry;
 std::array<Transform,3>transforms(State state)const {
  std::array<Transform,3>out;for(unsigned i=0;i<3;++i)out[i]=transform(i,layers[i].center,layers[i].count?state:State{});return out;
 }
 QJsonObject json(State state)const {QJsonObject objects;const char*names[3]={"lung","airway","nodule"};
  for(unsigned i=0;i<3;++i){auto o=transform(i,layers[i].center,layers[i].count?state:State{}).json();o["foreground_voxels"]=double(layers[i].count);
   o["empty"]=!layers[i].count;o["mask_bit"]=int(1u<<i);o["index_min_xyz"]=QJsonArray{layers[i].lo[0],layers[i].lo[1],layers[i].lo[2]};
   o["index_max_xyz"]=QJsonArray{layers[i].hi[0],layers[i].hi[1],layers[i].hi[2]};objects[names[i]]=o;}
  return {{"controls",state.json()},{"layers",objects},{"mask_path",maskPath},{"mask_sha256",maskSHA},
   {"geometry",geometry},{"pivot_policy","physical center of mask-content voxel-center bounding box"},
   {"display_only",true},{"navigation_geometry_modified",false}};
 }
 static Pivots load(const QJsonObject&scene,const QString&scenePath){
  Pivots out;out.geometry=scene["geometry"].toObject();require(!out.geometry.isEmpty(),"Missing breathing geometry");
  auto dims=out.geometry["size_xyz"].toArray(),spacing=out.geometry["spacing_xyz"].toArray(),origin=out.geometry["origin_lps_mm"].toArray(),direction=out.geometry["direction"].toArray();
  require(dims.size()==3&&spacing.size()==3&&origin.size()==3&&direction.size()==9,"Invalid breathing geometry dimensions");
  std::array<int,3>size{};Point step{},offset{};uint64_t count=1;
  for(int i=0;i<3;++i){double n=dims[i].toDouble(-1);require(dims[i].isDouble()&&std::isfinite(n)&&n>=1&&n<=4096&&n==std::floor(n),"Invalid mask dimension");size[i]=int(n);count*=size[i];
   step[i]=spacing[i].toDouble(-1);offset[i]=origin[i].toDouble(std::numeric_limits<double>::quiet_NaN());
   require(spacing[i].isDouble()&&std::isfinite(step[i])&&step[i]>0&&step[i]<=100&&origin[i].isDouble()&&std::isfinite(offset[i]),"Invalid mask spacing/origin");}
  require(count<=uint64_t(2)*1024*1024*1024,"Mask size exceeds breathing scan bound");
  std::array<double,9>d{};for(int i=0;i<9;++i){d[i]=direction[i].toDouble(std::numeric_limits<double>::quiet_NaN());require(direction[i].isDouble()&&std::isfinite(d[i])&&std::abs(d[i])<=1.000001,"Invalid mask direction");}
  for(int i=0;i<3;++i)for(int j=0;j<3;++j){double dot=0;for(int k=0;k<3;++k)dot+=d[k*3+i]*d[k*3+j];require(std::abs(dot-(i==j?1:0))<1e-5,"Nonorthogonal mask direction");}
  require(scene["masks"].isString()&&!scene["masks"].toString().isEmpty(),"Missing breathing mask source");
  out.maskPath=QDir(QFileInfo(scenePath).absolutePath()).absoluteFilePath(scene["masks"].toString());
  QFile f(out.maskPath);require(f.open(QIODevice::ReadOnly)&&f.size()==qint64(count),"Breathing mask size mismatch");
  auto*bytes=f.map(0,f.size());require(bytes,"Cannot map breathing mask");
  QCryptographicHash hash(QCryptographicHash::Sha256);for(qint64 start=0;start<f.size();start+=1024*1024)hash.addData(reinterpret_cast<const char*>(bytes)+start,int(std::min(qint64(1024*1024),f.size()-start)));out.maskSHA=hash.result().toHex();
  uint64_t idx=0;for(int z=0;z<size[2];++z)for(int y=0;y<size[1];++y)for(int x=0;x<size[0];++x,++idx){
   unsigned v=bytes[idx]&7;if(!v)continue;const int p[3]={x,y,z};
   for(unsigned layer=0;layer<3;++layer)if(v&(1u<<layer)){auto&b=out.layers[layer];++b.count;for(int k=0;k<3;++k){b.lo[k]=std::min(b.lo[k],p[k]);b.hi[k]=std::max(b.hi[k],p[k]);}}
  }f.unmap(bytes);
  for(auto&b:out.layers){if(!b.count){b.lo={{0,0,0}};b.hi={{-1,-1,-1}};continue;}
   for(int i=0;i<3;++i){b.center[i]=offset[i];for(int k=0;k<3;++k)b.center[i]+=d[i*3+k]*(.5*(b.lo[k]+b.hi[k]))*step[k];}}
  return out;
 }
};
} // namespace overview_breathing
