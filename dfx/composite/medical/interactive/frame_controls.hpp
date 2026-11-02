#pragma once
#include <QJsonObject>
#include <QJsonArray>
#include <QVector3D>
#include <QStringList>
#include <cmath>
#include <sys/stat.h>
struct FileStamp {
 uint64_t device=0,inode=0,size=0;int64_t modified=0,changed=0,modifiedNS=0,changedNS=0;
 static FileStamp read(const QString&path){struct stat st{};auto name=path.toUtf8();
  check(!stat(name.constData(),&st)&&S_ISREG(st.st_mode),"Scene data file unavailable");
  return {uint64_t(st.st_dev),uint64_t(st.st_ino),uint64_t(st.st_size),st.st_mtim.tv_sec,st.st_ctim.tv_sec,st.st_mtim.tv_nsec,st.st_ctim.tv_nsec};}
 bool operator==(const FileStamp&o)const{return device==o.device&&inode==o.inode&&size==o.size&&modified==o.modified&&changed==o.changed&&modifiedNS==o.modifiedNS&&changedNS==o.changedNS;}
};
struct FrameControls {
 unsigned width=384,height=218,opacityByte=51;float yaw=0,pitch=0,zoom=1,requiredRadius=.7f,resolutionMargin=0,clipValue=0,radius=0;
 bool full=true,lung=true,airway=true,nodule=true,clip=false,focus=false,benchmark=false;
 int clipAxis=2,colorMode=0;QVector3D center;QString capture;
 static void known(const QJsonObject&o,const QStringList&keys){for(auto i=o.begin();i!=o.end();++i)check(keys.contains(i.key()),"Unknown medical control field");}
 static double number(const QJsonObject&o,const char*name,double value,double lo,double hi){if(!o.contains(name))return value;
  check(o[name].isDouble(),"Medical control number required");double x=o[name].toDouble();check(std::isfinite(x)&&x>=lo&&x<=hi,"Medical control number out of range");return x;}
 static bool flag(const QJsonObject&o,const char*name,bool value){if(!o.contains(name))return value;check(o[name].isBool(),"Medical control boolean required");return o[name].toBool();}
 static FrameControls parse(const QJsonObject&o){
  known(o,{"command","sequence","width","height","yaw_degrees","pitch_degrees","full_lung","capture_path","strong_PS_benchmark", "layers","lung_opacity","zoom","center_lps_mm","radius_mm","clipping","color_mode","required_radius_mm","resolution_margin_mm"});
  FrameControls c;double w=number(o,"width",384,16,640),h=number(o,"height",218,4,512);
  check(w==std::floor(w)&&h==std::floor(h)&&unsigned(w)%16==0,"Invalid medical viewport dimensions");c.width=w;c.height=h;
  c.yaw=number(o,"yaw_degrees",0,-100000,100000);c.pitch=number(o,"pitch_degrees",0,-100000,100000);
  c.zoom=number(o,"zoom",1,.3,6);c.requiredRadius=number(o,"required_radius_mm",.7,0,100);
  c.resolutionMargin=number(o,"resolution_margin_mm",0,0,100);double mode=number(o,"color_mode",0,0,3);check(mode==std::floor(mode),"Invalid analysis mode");c.colorMode=mode;
  c.opacityByte=unsigned(std::floor(number(o,"lung_opacity",.2,0,1)*255+.5));
  c.full=flag(o,"full_lung",true);c.benchmark=flag(o,"strong_PS_benchmark",false);
  if(o.contains("capture_path")){check(o["capture_path"].isString(),"Capture path must be a string");c.capture=o["capture_path"].toString();}
  if(o.contains("sequence")){double sequence=number(o,"sequence",0,0,2147483647);check(sequence==std::floor(sequence),"Invalid frame sequence");}
  if(o.contains("layers")){check(o["layers"].isObject(),"Layer controls must be an object");auto layers=o["layers"].toObject();known(layers,{"lung","airway","nodule"});c.lung=flag(layers,"lung",true);c.airway=flag(layers,"airway",true);c.nodule=flag(layers,"nodule",true);}
  if(o.contains("clipping")){check(o["clipping"].isObject(),"Clipping controls must be an object");auto clipping=o["clipping"].toObject();known(clipping,{"enabled","axis","value_mm"});c.clip=flag(clipping,"enabled",false);
   double axis=number(clipping,"axis",2,0,2);check(axis==std::floor(axis),"Invalid clipping axis");c.clipAxis=axis;c.clipValue=number(clipping,"value_mm",0,-100000,100000);check(!c.clip||clipping.contains("value_mm"),"Enabled clipping needs a position");}
  c.focus=o.contains("center_lps_mm")||o.contains("radius_mm");if(c.focus){
   check(o["center_lps_mm"].isArray()&&o.contains("radius_mm"),"Focus needs both center and radius");auto center=o["center_lps_mm"].toArray();check(center.size()==3,"Focus center needs three coordinates");
   for(unsigned k=0;k<3;++k){check(center[k].isDouble()&&std::isfinite(center[k].toDouble())&&std::abs(center[k].toDouble())<=100000,"Invalid focus coordinate");c.center[k]=center[k].toDouble();}
   c.radius=number(o,"radius_mm",0,.1,100000);
  }
  return c;
 }
 QJsonObject json()const{return {{"width",int(width)},{"height",int(height)},{"yaw_degrees",yaw},{"pitch_degrees",pitch},
  {"zoom",zoom},{"full_lung",full},{"layers",QJsonObject{{"lung",lung},{"airway",airway},{"nodule",nodule}}},
  {"lung_opacity_byte",int(opacityByte)},{"color_mode",colorMode},{"required_radius_mm",requiredRadius},{"resolution_margin_mm",resolutionMargin},
  {"clipping",QJsonObject{{"enabled",clip},{"axis",clipAxis},{"value_mm",clipValue}}},{"focus",focus},
  {"center_lps_mm",QJsonArray{center.x(),center.y(),center.z()}},{"radius_mm",radius}};}
};
