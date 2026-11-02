#pragma once
#include "gamepad_input.hpp"

namespace medical_gamepad {
struct InputState {Axes axes;bool connected=false;QString name,status;quint64 frames=0,losses=0;};
// One latest complete frame, never a FIFO of old stick commands. Loss is sticky
// until consumed; a later frame must not conceal a true evdev overflow.
class InputMailbox {
 mutable QMutex mutex_;InputState state_;bool queued_=false,lost_=false;
public:
 bool put(InputState state,bool lost=false){QMutexLocker lock(&mutex_);state_=std::move(state);lost_|=lost;bool notify=!queued_;queued_=true;return notify;}
 std::pair<InputState,bool> take(){QMutexLocker lock(&mutex_);queued_=false;bool lost=lost_;lost_=false;return {state_,lost};}
 InputState peek()const{QMutexLocker lock(&mutex_);return state_;}
};
class ThreadedInput:public QObject {
 Config config_;QThread thread_;QObject*worker_=nullptr;QTimer dispatch_;InputMailbox mailbox_;QString lastStatus_;bool started_=false;
 void publish(Input*input,bool lost,bool frame,quint64&frames,quint64&losses){
  if(frame)++frames;if(lost)++losses;
  InputState state{input->current(),input->connected(),input->name(),input->statusText(),frames,losses};
  if(mailbox_.put(std::move(state),lost))QMetaObject::invokeMethod(this,[this]{dispatch_.start(8);},Qt::QueuedConnection);
 }
 void deliver(){
  auto value=mailbox_.take();
  if(value.second){qWarning()<<"Gamepad evdev synchronization lost; neutral rearm required";if(onLost)onLost();}
  if(value.first.status!=lastStatus_){lastStatus_=value.first.status;qInfo().noquote()<<"Gamepad:"<<lastStatus_;if(onStatus)onStatus(lastStatus_);}
  if(onFrame)onFrame(value.first.axes);
 }
public:
 std::function<void(Axes)>onFrame;std::function<void()>onLost;std::function<void(QString)>onStatus;
 ThreadedInput(Config config,QObject*parent=nullptr):QObject(parent),config_(config){
  dispatch_.setSingleShot(true);dispatch_.setTimerType(Qt::PreciseTimer);connect(&dispatch_,&QTimer::timeout,this,[this]{deliver();});
  thread_.setObjectName("Gamepad evdev input");
 }
 ~ThreadedInput(){dispatch_.stop();thread_.quit();thread_.wait();}
 void start(){
  if(started_)return;started_=true;worker_=new QObject;worker_->moveToThread(&thread_);connect(&thread_,&QThread::finished,worker_,&QObject::deleteLater);thread_.start();
  QMetaObject::invokeMethod(worker_,[this]{
   // Construct all Input timers/notifiers in their owner thread.
   auto*input=new Input(config_,worker_);auto counts=std::make_shared<std::array<quint64,2>>(std::array<quint64,2>{0,0});
   input->onFrame=[this,input,counts](Axes){publish(input,false,true,(*counts)[0],(*counts)[1]);};
   input->onLost=[this,input,counts]{publish(input,true,false,(*counts)[0],(*counts)[1]);};
   input->onStatus=[this,input,counts](QString){publish(input,false,false,(*counts)[0],(*counts)[1]);};input->start();
  },Qt::QueuedConnection);
 }
 bool connected()const{return mailbox_.peek().connected;}Axes current()const{return mailbox_.peek().axes;}
 QString name()const{return mailbox_.peek().name;}QString statusText()const{return mailbox_.peek().status;}
 InputState statistics()const{return mailbox_.peek();}
};
}
