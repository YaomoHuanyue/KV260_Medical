#pragma once
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace medical_motion {
inline double position(double start, double elapsed_ms, double speed, double total) {
 if(!std::isfinite(start)||!std::isfinite(elapsed_ms)||!std::isfinite(speed)||
    !std::isfinite(total)||elapsed_ms<0||speed<=0||total<0)
  throw std::invalid_argument("Invalid physical navigation clock");
 return std::clamp(start+elapsed_ms*speed/1000.,0.,total);
}
inline double step(double at,double delta,double total) {
 if(!std::isfinite(at)||!std::isfinite(delta)||!std::isfinite(total)||total<0)
  throw std::invalid_argument("Invalid physical navigation step");
 return std::clamp(at+delta,0.,total);
}
}
