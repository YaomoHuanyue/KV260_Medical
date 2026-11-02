#pragma once
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace navigation_media {
// Original Python flythrough frame-count, uniform physical arc and final hold.
struct Timeline {
 double length; int fps, moving, hold;
 Timeline(double mm,int rate,double speed):length(mm),fps(rate){
  if(!std::isfinite(mm)||mm<=0||rate<1||rate>60||!std::isfinite(speed)||speed<=0||speed>100)
   throw std::runtime_error("Invalid route, frame rate or physical speed");
  double count=std::floor(mm/speed*rate);
  if(count>100000)throw std::runtime_error("Video exceeds 100000 route frames");
  moving=std::max(2,int(count));hold=int(rate*.8);
 }
 int total()const{return moving+hold;}
 double arc(int i)const{
  if(i<0||i>=total())throw std::runtime_error("Invalid frame index");
  return i>=moving?length:double(i)*length/(moving-1);
 }
};
}
