#pragma once
#include "gamepad_motion.hpp"
#include <QtCore>
#include <array>
#include <bitset>
#include <cerrno>
#include <cstring>
#include <functional>
#include <memory>
#include <optional>
#include <linux/input.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace medical_gamepad {
struct Config {
 std::array<int,3> codes{ABS_Y,ABS_RX,ABS_RY};
 std::array<bool,3> invert{true,false,true};
 double deadzone=.15,exponent=1.5,turnDegreesPerSecond=45;QString device;
 static int axis(QString name){
  static const QMap<QString,int> names{{"ABS_X",ABS_X},{"ABS_Y",ABS_Y},{"ABS_Z",ABS_Z},{"ABS_RX",ABS_RX},{"ABS_RY",ABS_RY},{"ABS_RZ",ABS_RZ}};
  if(!names.contains(name))throw std::invalid_argument("Unsupported gamepad axis name");return names[name];
 }
 static Config load(QString filename){
  QFile f(filename);if(!f.open(QIODevice::ReadOnly))throw std::runtime_error("Cannot read gamepad configuration");
  QJsonParseError error;auto doc=QJsonDocument::fromJson(f.readAll(),&error);if(error.error!=QJsonParseError::NoError||!doc.isObject())throw std::runtime_error("Invalid gamepad configuration JSON");
  auto o=doc.object();if(o["schema"]!="kv260.gamepad.v1")throw std::runtime_error("Unknown gamepad configuration schema");
  Config c;auto axes=o["axes"].toObject();auto invert=o["invert"].toObject();QStringList keys{"forward","yaw","pitch"};
  for(int i=0;i<3;++i){c.codes[i]=axis(axes[keys[i]].toString());if(!invert[keys[i]].isBool())throw std::runtime_error("Missing gamepad direction setting");c.invert[i]=invert[keys[i]].toBool();}
  if(c.codes[0]==c.codes[1]||c.codes[0]==c.codes[2]||c.codes[1]==c.codes[2])throw std::runtime_error("Gamepad axes must be distinct");
  c.deadzone=o["deadzone"].toDouble(-1);c.exponent=o["response_exponent"].toDouble(-1);c.turnDegreesPerSecond=o["turn_degrees_per_second"].toDouble(-1);c.device=o["device"].toString();
  if(!std::isfinite(c.deadzone)||c.deadzone<.02||c.deadzone>.5||!std::isfinite(c.exponent)||c.exponent<1||c.exponent>3||!std::isfinite(c.turnDegreesPerSecond)||c.turnDegreesPerSecond<5||c.turnDegreesPerSecond>120)throw std::runtime_error("Gamepad deadzone/rate out of range");
  return c;
 }
};
struct Snapshot {std::array<AxisRange,3> ranges;std::array<int,3> values{};};
inline std::optional<Snapshot> snapshot(int fd,const Config&config){
 Snapshot s;
 for(int i=0;i<3;++i){input_absinfo a{};if(ioctl(fd,EVIOCGABS(config.codes[i]),&a)<0)return std::nullopt;s.ranges[i]={a.minimum,a.maximum,a.flat};s.values[i]=a.value;if(!s.ranges[i].valid())return std::nullopt;}
 return s;
}
class Decoder {
 Config config_;Snapshot state_;bool dropping_=false;
public:
 enum class Result {None,Frame,Lost,Resync};
 Decoder(Config config,Snapshot state):config_(config),state_(state){}
 Axes axes()const{
  double a[3];for(int i=0;i<3;++i)a[i]=state_.ranges[i].normalized(state_.values[i],config_.deadzone,config_.exponent)*(config_.invert[i]?-1:1);
  double length=std::hypot(a[1],a[2]);if(length>1){a[1]/=length;a[2]/=length;}return {a[0],a[1],a[2]};
 }
 void synchronize(Snapshot s){state_=s;dropping_=false;}
 Result consume(const input_event&e){
  if(e.type==EV_SYN&&e.code==SYN_DROPPED){dropping_=true;return Result::Lost;}
  if(dropping_)return e.type==EV_SYN&&e.code==SYN_REPORT?Result::Resync:Result::None;
  if(e.type==EV_ABS)for(int i=0;i<3;++i)if(e.code==config_.codes[i])state_.values[i]=e.value;
  return e.type==EV_SYN&&e.code==SYN_REPORT?Result::Frame:Result::None;
 }
};
// Reusable nonblocking fd reader. Tests exercise this same byte/framing path
// using a pipe, without exposing a synthetic-input API in the production UI.
class EventReader:public QObject {
 int fd_;Decoder decoder_;std::unique_ptr<QSocketNotifier> notifier_;QByteArray pending_;bool closed_=false;
 std::function<std::optional<Snapshot>()> snapshot_;
 void lost(){if(onLost)onLost();}
 void drain(){
  for(int batch=0;batch<4&&!closed_;++batch){
   char buffer[sizeof(input_event)*64];ssize_t n=::read(fd_,buffer,sizeof(buffer));
   if(n<0&&(errno==EAGAIN||errno==EWOULDBLOCK))return;
   if(n<0&&errno==EINTR)continue;
   if(n<=0){disconnect();return;}
   pending_.append(buffer,int(n));
   while(!closed_&&pending_.size()>=int(sizeof(input_event))){
    input_event event{};std::memcpy(&event,pending_.constData(),sizeof(event));pending_.remove(0,sizeof(event));
    auto result=decoder_.consume(event);
    if(result==Decoder::Result::Lost)lost();
    else if(result==Decoder::Result::Resync){auto value=snapshot_();if(!value){disconnect();return;}decoder_.synchronize(*value);if(onFrame)onFrame(decoder_.axes());}
    else if(result==Decoder::Result::Frame&&onFrame)onFrame(decoder_.axes());
   }
  }
 }
public:
 std::function<void(Axes)>onFrame;std::function<void()>onLost,onDisconnected;
 EventReader(int ownedFD,Config config,Snapshot state,std::function<std::optional<Snapshot>()>resync,QObject*parent=nullptr):QObject(parent),fd_(ownedFD),decoder_(config,state),snapshot_(std::move(resync)){
  if(fd_<0)throw std::invalid_argument("Invalid gamepad descriptor");
  int flags=fcntl(fd_,F_GETFL);if(flags<0||fcntl(fd_,F_SETFL,flags|O_NONBLOCK)<0){::close(fd_);fd_=-1;throw std::runtime_error("Cannot make gamepad descriptor nonblocking");}
  notifier_=std::make_unique<QSocketNotifier>(fd_,QSocketNotifier::Read,this);
  connect(notifier_.get(),&QSocketNotifier::activated,this,[this]{drain();});
 }
 ~EventReader(){if(notifier_)notifier_->setEnabled(false);if(fd_>=0)::close(fd_);}
 void disconnect(){if(closed_)return;closed_=true;notifier_->setEnabled(false);lost();if(onDisconnected)onDisconnected();}
 Axes current()const{return closed_?Axes{}:decoder_.axes();}
 bool present()const{return !closed_&&snapshot_().has_value();}
};
template<unsigned N>inline bool bit(const std::array<unsigned long,(N+sizeof(unsigned long)*8-1)/(sizeof(unsigned long)*8)>&a,unsigned code){return code<N&&(a[code/(sizeof(unsigned long)*8)]&(1UL<<(code%(sizeof(unsigned long)*8))));}
inline bool matchesGamepad(int fd,const Config&config){
 constexpr int word=sizeof(unsigned long)*8;std::array<unsigned long,(KEY_CNT+word-1)/word>keys{};std::array<unsigned long,(ABS_CNT+word-1)/word>abs{};
 if(ioctl(fd,EVIOCGBIT(EV_KEY,sizeof(keys)),keys.data())<0||ioctl(fd,EVIOCGBIT(EV_ABS,sizeof(abs)),abs.data())<0||!bit<KEY_CNT>(keys,BTN_GAMEPAD))return false;
 for(auto code:config.codes)if(!bit<ABS_CNT>(abs,code))return false;return true;
}
class Input:public QObject {
 Config config_;QTimer scan_;QFileSystemWatcher watcher_;std::unique_ptr<EventReader>reader_;Axes current_;QString name_,status_;bool connected_=false,retiring_=false;
 void status(QString text){if(status_==text)return;status_=text;if(onStatus)onStatus(status_);}
 void disconnected(){
  connected_=false;retiring_=true;current_={};if(onFrame)onFrame(current_);status(QString::fromUtf8("手柄已断开，移动停止"));
  // Never destroy the notifier while its own activated callback is on stack.
  QTimer::singleShot(0,this,[this]{reader_.reset();retiring_=false;scan_.start();discover();});
 }
 void discover(){
  if(connected_||retiring_)return;
  auto nodes=config_.device.isEmpty()?QDir("/dev/input").entryList({"event*"},QDir::System|QDir::Files,QDir::Name):QStringList{config_.device};
  bool denied=false;
  for(auto node:nodes){
   QString path=node.startsWith('/')?node:"/dev/input/"+node;QString real=QFileInfo(path).canonicalFilePath();if(!real.startsWith("/dev/input/event"))continue;
   int fd=::open(real.toLocal8Bit().constData(),O_RDONLY|O_NONBLOCK|O_CLOEXEC);
   if(fd<0){denied=denied||errno==EACCES;continue;}
   struct stat st{};bool valid=fstat(fd,&st)==0&&S_ISCHR(st.st_mode)&&matchesGamepad(fd,config_);auto state=valid?snapshot(fd,config_):std::nullopt;
   if(!state){::close(fd);continue;}
   char title[256]{};ioctl(fd,EVIOCGNAME(sizeof(title)),title);name_=QString::fromLocal8Bit(title);if(name_.isEmpty())name_=real;
   reader_=std::make_unique<EventReader>(fd,config_,*state,[fd,config=config_]{return snapshot(fd,config);},this);
   reader_->onFrame=[this](Axes value){current_=value;if(onFrame)onFrame(value);};
   reader_->onLost=[this]{current_={};if(onLost)onLost();};reader_->onDisconnected=[this]{disconnected();};
   connected_=true;current_=reader_->current();scan_.stop();status(QString::fromUtf8("手柄已连接：")+name_);if(onFrame)onFrame(current_);return;
  }
  status(denied?QString::fromUtf8("手柄输入权限不足"):QString::fromUtf8("手柄未连接"));
 }
public:
 std::function<void(Axes)>onFrame;std::function<void()>onLost;std::function<void(QString)>onStatus;
 Input(Config config,QObject*parent=nullptr):QObject(parent),config_(std::move(config)){
  scan_.setInterval(1000);scan_.setTimerType(Qt::CoarseTimer);connect(&scan_,&QTimer::timeout,this,[this]{discover();});
  if(QFileInfo::exists("/dev/input"))watcher_.addPath("/dev/input");
  connect(&watcher_,&QFileSystemWatcher::directoryChanged,this,[this]{if(connected_){if(!reader_->present())reader_->disconnect();}else discover();});
 }
 void start(){discover();if(!connected_)scan_.start();}
 bool connected()const{return connected_;}Axes current()const{return current_;}QString name()const{return name_;}QString statusText()const{return status_;}
};
}
