#pragma once
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace medical_gamepad {
struct Axes {
 double forward=0,yaw=0,pitch=0;
 bool neutral()const{return std::abs(forward)+std::abs(yaw)+std::abs(pitch)<1e-9;}
};
struct Delta { double millimeters=0,yaw=0,pitch=0; };
struct AxisRange {
 int minimum=-32768,maximum=32767,flat=0;
 bool valid()const{return maximum>minimum&&flat>=0;}
 double normalized(int value,double deadzone,double exponent)const{
  if(!valid()||!std::isfinite(deadzone)||deadzone<0||deadzone>=1||!std::isfinite(exponent)||exponent<1)throw std::invalid_argument("Invalid gamepad axis calibration");
  double center=(double(minimum)+maximum)/2,span=value>=center?maximum-center:center-minimum;
  double x=std::clamp((double(value)-center)/span,-1.,1.);
  double zone=std::clamp(std::max(deadzone,flat/span),0.,.95);
  if(std::abs(x)<=zone)return 0;
  return std::copysign(std::pow((std::abs(x)-zone)/(1-zone),exponent),x);
 }
};
class Motion {
 bool armed_=false;Axes axes_;
public:
 void suspend(){armed_=false;axes_={};}
 void update(Axes axes,bool allowed){
  if(!allowed||!std::isfinite(axes.forward)||!std::isfinite(axes.yaw)||!std::isfinite(axes.pitch)){suspend();return;}
  axes.forward=std::clamp(axes.forward,-1.,1.);axes.yaw=std::clamp(axes.yaw,-1.,1.);axes.pitch=std::clamp(axes.pitch,-1.,1.);
  double length=std::hypot(axes.yaw,axes.pitch);if(length>1){axes.yaw/=length;axes.pitch/=length;}
  if(!armed_){if(axes.neutral())armed_=true;axes_={};return;}
  axes_=axes;
 }
 bool armed()const{return armed_;}
 bool moving()const{return armed_&&!axes_.neutral();}
 Delta step(double seconds,double mmPerSecond,double degreesPerSecond)const{
  if(!std::isfinite(seconds)||seconds<0||!std::isfinite(mmPerSecond)||mmPerSecond<=0||!std::isfinite(degreesPerSecond)||degreesPerSecond<=0)throw std::invalid_argument("Invalid gamepad motion clock/rate");
  if(!moving())return {};
  // A blocked UI must never catch up several seconds of stale stick input.
  double dt=std::min(seconds,.05);
  return {axes_.forward*mmPerSecond*dt,axes_.yaw*degreesPerSecond*dt,axes_.pitch*degreesPerSecond*dt};
 }
};
}
