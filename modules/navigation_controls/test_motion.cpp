#include "motion.hpp"
#include <cassert>
#include <limits>
#include <iostream>
int main(){
 assert(medical_motion::position(3,250,2,20)==3.5);
 assert(medical_motion::position(3,100000,2,20)==20);
 assert(medical_motion::step(3,-20,20)==0);
 assert(medical_motion::step(3,.25,20)==3.25);
 assert(medical_motion::step(20,2,20)==20);
 // Interrupted playback re-anchors, independent of event/timer frequency.
 double at=medical_motion::position(3,750,2,20);
 assert(medical_motion::position(at,500,8,20)==8.5);
 int rejected=0;
 for(double bad:{-1.,std::numeric_limits<double>::quiet_NaN()}){
  try{medical_motion::position(0,bad,2,20);}catch(const std::invalid_argument&){++rejected;}
 }
 try{medical_motion::position(0,1,0,20);}catch(const std::invalid_argument&){++rejected;}
 assert(rejected==3);
 std::cout<<"physical_clock_bounds_reanchor_and_invalid_inputs_passed\n";
}
