#include "gamepad_input.hpp"
#include "gamepad_dispatch.hpp"
#include "gamepad_camera.hpp"
#include "views_attributes_r52.hpp"
#include <QTest>
#include <iostream>
#include <thread>
using namespace medical_gamepad;
static int checks=0;
static void check(bool condition,const char*message){if(!condition)throw std::runtime_error(message);++checks;}
static void closeTo(double a,double b,const char*message){check(std::abs(a-b)<1e-5,message);}
static QVector3D vector(QJsonValue value){auto a=value.toArray();return {float(a[0].toDouble()),float(a[1].toDouble()),float(a[2].toDouble())};}
static void sameVector(QVector3D a,QVector3D b,const char*message){check((a-b).length()<2e-5,message);}
static input_event event(unsigned type,unsigned code,int value){input_event e{};e.type=type;e.code=code;e.value=value;return e;}
static void send(int fd,input_event value){check(::write(fd,&value,sizeof(value))==sizeof(value),"Cannot send simulated event bytes");}
static QJsonArray a(QVector3D p){return {p.x(),p.y(),p.z()};}
static QJsonObject curvedScene(){
 QJsonArray positions{a({0,0,0}),a({0,0,-10}),a({10,0,-10}),a({10,0,-20})};
 QJsonArray forward{a({0,0,-1}),a({1,0,0}),a({0,0,-1}),a({0,0,-1})};QJsonArray up{a({0,1,0}),a({0,1,0}),a({0,1,0}),a({0,1,0})};
 return {{"meshes",QJsonObject{}},{"navigation",QJsonObject{{"positions",positions},{"forward",forward},{"up",up},{"arc",QJsonArray{0,10,20,30}}}}};
}
int main(int argc,char**argv){
 QApplication app(argc,argv);QJsonObject report{{"physical_gamepad_tested",false},{"PL_access",false},{"kernel_HID_mapping_tested",false},{"test_kind","native nonblocking pipe events and offscreen production MeshView"}};
 try{
  check(argc==3,"Expected config and evidence path");auto config=Config::load(QString::fromLocal8Bit(argv[1]));
  check(config.codes==std::array<int,3>{ABS_Y,ABS_RX,ABS_RY},"Default axes changed");
  AxisRange range;closeTo(range.normalized(0,.15,1.5),0,"Center drift");closeTo(range.normalized(-32768,.15,1.5),-1,"Signed minimum");closeTo(range.normalized(32767,.15,1.5),1,"Signed maximum");
  closeTo(range.normalized(999999,.15,1.5),1,"Clamp invalid axis value");AxisRange unsignedRange{0,255,0};closeTo(unsignedRange.normalized(128,.15,1.5),0,"Unsigned center");
  check(range.normalized(12000,.15,1.5)>0,"Proportional response missing");check(range.normalized(12000,.15,1.5)<range.normalized(20000,.15,1.5),"Response not monotonic");
  AxisRange flat{-100,100,30};closeTo(flat.normalized(29,.15,1),0,"Kernel flat not respected");
  bool rejected=false;try{AxisRange{1,1,0}.normalized(1,.15,1);}catch(...){rejected=true;}check(rejected,"Invalid calibration accepted");
  Motion m;m.update({1,0,0},true);check(!m.armed(),"Held stick moved at startup");m.update({},true);check(m.armed(),"Neutral did not arm");m.update({1,1,1},true);
  auto delta=m.step(.02,2,45);closeTo(delta.millimeters,.04,"Forward physical speed");closeTo(std::hypot(delta.yaw,delta.pitch),.9,"Diagonal speed boost");
  closeTo(m.step(5,2,45).millimeters,.1,"UI stall caused a jump");m.update({},true);check(!m.moving(),"Neutral did not stop");m.update({-1,0,0},true);check(m.step(.02,2,45).millimeters<0,"Backward axis");
  m.update({1,0,0},false);check(!m.armed(),"Wrong-tab/modal/focus gate failed");m.update({1,0,0},true);check(!m.moving(),"Held stick resumed after blocked page");m.update({},true);m.update({1,0,0},true);
  double distance=0;for(int i=0;i<50;++i)distance+=m.step(.02,2,45).millimeters;closeTo(distance,2,"Held constant axis requires repeated events");m.suspend();check(!m.moving(),"Suspend did not clear command");
  InputMailbox mailbox;int notifications=0;
  std::thread producer([&]{for(int i=1;i<=20000;++i){InputState s;s.connected=true;s.axes={.8,.6,-.4};s.frames=i;s.losses=i>=100?1:0;if(mailbox.put(s,i==100))++notifications;}});
  QThread::msleep(40);producer.join();auto combined=mailbox.take();
  check(combined.first.frames==20000,"Input producer blocked behind GUI");check(notifications==1,"Raw reports flooded GUI queue");
  check(combined.second&&combined.first.losses==1,"Coalescing concealed input loss");check(!mailbox.take().second,"Loss flag was not consumed");
  closeTo(combined.first.axes.forward,.8,"Latest dual-stick forward lost");closeTo(combined.first.axes.yaw,.6,"Latest dual-stick yaw lost");closeTo(combined.first.axes.pitch,-.4,"Latest dual-stick pitch lost");
  Motion dualMotion;dualMotion.update({},true);dualMotion.update(combined.first.axes,true);check(dualMotion.moving(),"Dual sticks not active");
  dualMotion.update({0,.6,-.4},true);check(dualMotion.moving()&&dualMotion.step(.02,2,45).yaw>0,"Releasing left interrupted right stick");
  dualMotion.update({.8,0,0},true);check(dualMotion.moving()&&dualMotion.step(.02,2,45).millimeters>0,"Releasing right interrupted left stick");
  MeshView dualView;dualView.setScope(true);dualView.loadScene("/unused-dual-scene.json",curvedScene());dualView.setDistance(2);dualView.setManualNavigation(true);
  dualMotion.update({1,1,.1},true);
  for(int i=0;i<100;++i){auto d=dualMotion.step(.02,2,45);check(dualView.manualMotion(d.millimeters,d.yaw,d.pitch),"Continuous dual-stick command interrupted");}
  closeTo(dualView.distance(),6,"Combined sticks lost forward distance");check(dualView.cameraRequest()["manual_yaw_degrees"].toDouble()>80,"Combined sticks lost turn");
  check(!dualView.cameraRequest()["auto_align"].toBool(),"Combined sticks reenabled alignment");
  int fds[2];check(pipe2(fds,O_NONBLOCK|O_CLOEXEC)==0,"pipe2 failed");Snapshot state;state.values={0,0,0};int frames=0,lost=0,disconnected=0;Motion streamMotion;streamMotion.update({},true);Axes latest;
  {
   EventReader reader(fds[0],config,state,[&]{return std::optional<Snapshot>(state);});
   reader.onFrame=[&](Axes axes){++frames;latest=axes;streamMotion.update(axes,true);};reader.onLost=[&]{++lost;streamMotion.suspend();};reader.onDisconnected=[&]{++disconnected;};
   check(!matchesGamepad(fds[1],config),"Non-gamepad descriptor accepted");
   send(fds[1],event(EV_ABS,ABS_Y,-32768));send(fds[1],event(EV_ABS,ABS_RX,32767));QTest::qWait(10);check(frames==0,"Partial packet published before SYN_REPORT");send(fds[1],event(EV_SYN,SYN_REPORT,0));QTest::qWait(10);
   check(frames==1,"SYN packet not delivered");closeTo(latest.forward,1,"Left forward polarity");closeTo(latest.yaw,1,"Right horizontal polarity");
   auto e=event(EV_ABS,ABS_RY,-32768);auto*bytes=reinterpret_cast<const char*>(&e);check(::write(fds[1],bytes,3)==3,"Fragment write failed");QTest::qWait(5);check(frames==1,"Fragment was treated as full event");check(::write(fds[1],bytes+3,sizeof(e)-3)==sizeof(e)-3,"Fragment tail failed");send(fds[1],event(EV_SYN,SYN_REPORT,0));QTest::qWait(10);check(latest.pitch>0,"Right up polarity");
   send(fds[1],event(EV_SYN,SYN_DROPPED,0));state.values={-32768,32767,0};send(fds[1],event(EV_ABS,ABS_Y,32767));send(fds[1],event(EV_SYN,SYN_REPORT,0));QTest::qWait(10);
   check(lost==1,"SYN_DROPPED was ignored");check(!streamMotion.moving(),"Overflow resumed a held stick");closeTo(latest.forward,1,"Overflow did not query the snapshot");
   send(fds[1],event(EV_ABS,ABS_Y,0));send(fds[1],event(EV_ABS,ABS_RX,0));send(fds[1],event(EV_ABS,ABS_RY,0));send(fds[1],event(EV_SYN,SYN_REPORT,0));QTest::qWait(10);check(streamMotion.armed(),"Neutral after overflow did not rearm");
   int beats=0;QTimer heartbeat;QObject::connect(&heartbeat,&QTimer::timeout,[&]{++beats;});heartbeat.start(1);QTest::qWait(25);check(beats>0,"No-input read blocked Qt");
   ::close(fds[1]);QTest::qWait(10);check(disconnected==1,"Unplug/EOF not detected");check(!streamMotion.moving()&&reader.current().neutral(),"Disconnect retained motion");
  }
  MeshView view;view.setScope(true);view.loadScene("/unused-test-scene.json",curvedScene());view.setDistance(2);
  auto initial=view.cameraRequest();auto initialF=vector(initial["forward"]),initialU=vector(initial["up"]);view.setManualNavigation(true);
  check(view.manualNavigation(),"Manual mode did not start");sameVector(initialF,vector(view.cameraRequest()["forward"]),"Takeover jumped the camera");
  view.setProperty("synthetic_wall_active",true);view.setProperty("synthetic_wall_center",QVariant::fromValue(QVector3D(100,50,-20)));
  check(view.manualMotion(100,0,0),"Left stick did not move");closeTo(view.distance(),30,"Path end clamp");sameVector(initialF,vector(view.cameraRequest()["forward"]),"Path/lesion automatically changed manual orientation");check(!view.cameraRequest()["synthetic_target_view"].toBool(),"Synthetic end aim still enabled");
  QTest::qWait(1100);sameVector(initialF,vector(view.cameraRequest()["forward"]),"Manual view auto corrected after release");check(!view.cameraRequest()["auto_align"].toBool(),"Auto alignment still enabled");
  view.manualMotion(0,45,0);auto right=QVector3D::crossProduct(initialF,initialU).normalized();check(QVector3D::dotProduct(vector(view.cameraRequest()["forward"]),right)>.6,"Right stick yaw direction");
  view.manualMotion(0,0,30);check(QVector3D::dotProduct(vector(view.cameraRequest()["forward"]),initialU)>.4,"Up stick pitch direction");auto saved=view.scopeViewState();auto savedRequest=view.cameraRequest();view.resetView();check(view.restoreScopeViewState(saved),"Manual state restore rejected");sameVector(vector(savedRequest["forward"]),vector(view.cameraRequest()["forward"]),"Video/state restore lost manual direction");
  auto invalid=saved;auto invalidCamera=invalid["manual_camera"].toObject();invalidCamera["base_forward"]=QJsonArray{0,0,0};invalid["manual_camera"]=invalidCamera;check(!view.restoreScopeViewState(invalid),"Invalid saved direction accepted");sameVector(vector(savedRequest["forward"]),vector(view.cameraRequest()["forward"]),"Invalid restore modified camera");
  view.manualMotion(0,10000,10000);check(std::abs(view.cameraRequest()["manual_pitch_degrees"].toDouble())<=75,"Pitch limit failed");view.manualMotion(-100,0,0);closeTo(view.distance(),0,"Path start clamp");
  view.setAutoAlign(true);check(!view.manualNavigation(),"Explicit auto-align did not leave manual mode");check(view.restoreScopeViewState({{"distance_mm",5.},{"manual_yaw_degrees",3.},{"manual_pitch_degrees",2.},{"auto_align",false}}),"Legacy camera state no longer supported");
  report["passed"]=true;
 }catch(const std::exception&e){report["passed"]=false;report["error"]=e.what();}
 report["checks"]=checks;auto raw=QJsonDocument(report).toJson();std::cout<<raw.constData();if(argc>=3){QFile out(QString::fromLocal8Bit(argv[2]));if(out.open(QIODevice::WriteOnly))out.write(raw);}
 return report["passed"].toBool()?0:1;
}
