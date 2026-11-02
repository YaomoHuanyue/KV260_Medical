#pragma once
#include <cmath>
#include <algorithm>
#include <limits>
#include <cstdint>
#ifndef NAV_NATIVE
#include <hls_math.h>
#endif
constexpr unsigned AUDIT_POINTS=4096;
constexpr uint64_t AUDIT_QUERY_TAG=0x4155444954303031ULL;
static double audit_acos(double x){
 // Half-angle form retains the small difference from +1 before invoking
 // atan, whose input is close to zero rather than a trigonometric endpoint.
 double magnitude=std::abs(x),t=std::sqrt((1-magnitude)/(1+magnitude));
#ifdef NAV_NATIVE
 double angle=2*std::atan(t);
#else
 double angle=2*hls::atan(t);
#endif
 return x<0?3.1415926535897932384626433832795-angle:angle;
}
// The same float64 discrete turn radius and straight/degenerate thresholds as
// ui/features/analysis.py. Endpoints and straight turns have infinite radius.
static void audit_bends(const double p[AUDIT_POINTS][3],unsigned n,double bends[AUDIT_POINTS]){
#pragma HLS INLINE off
 for(unsigned i=0;i<n;++i){
#pragma HLS PIPELINE II=16
  double result=std::numeric_limits<double>::infinity();
  if(i&&i+1<n){
   double x[3],y[3];
#pragma HLS ARRAY_PARTITION variable=x complete
#pragma HLS ARRAY_PARTITION variable=y complete
   for(unsigned j=0;j<3;++j){
#pragma HLS UNROLL
    x[j]=p[i][j]-p[i-1][j];y[j]=p[i+1][j]-p[i][j];
   }
   double left=std::sqrt(x[0]*x[0]+x[1]*x[1]+x[2]*x[2]);
   double right=std::sqrt(y[0]*y[0]+y[1]*y[1]+y[2]*y[2]);
   double dot=x[0]*y[0]+x[1]*y[1]+x[2]*y[2];
   double cosine=std::max(-1.,std::min(1.,dot/std::max(left*right,1e-20)));
   double angle=audit_acos(cosine);
   if(left>1e-8&&right>1e-8&&angle>1e-6)result=.5*(left+right)/angle;
  }
  bends[i]=result;
 }
}
// Reverse monotone deques: each index enters and leaves at most once. Bounds
// include all samples at arc[i]+window, matching searchsorted(..., right).
static void audit_forward(const double arcs[AUDIT_POINTS],const float radii[AUDIT_POINTS],const double bends[AUDIT_POINTS],unsigned n,double window,double margin,double minimum[AUDIT_POINTS],double minimum_bend[AUDIT_POINTS]){
#pragma HLS INLINE off
 uint16_t radius_queue[AUDIT_POINTS],bend_queue[AUDIT_POINTS];
#pragma HLS BIND_STORAGE variable=radius_queue type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=bend_queue type=ram_2p impl=bram
 unsigned rf=0,rb=0,bf=0,bb=0;
 for(unsigned remaining=n;remaining;--remaining){
  unsigned i=remaining-1;double end=arcs[i]+window;
  while(rf<rb&&arcs[radius_queue[rf]]>end)++rf;
  while(bf<bb&&arcs[bend_queue[bf]]>end)++bf;
  while(rb>rf&&radii[radius_queue[rb-1]]>=radii[i])--rb;
  while(bb>bf&&bends[bend_queue[bb-1]]>=bends[i])--bb;
  radius_queue[rb++]=uint16_t(i);bend_queue[bb++]=uint16_t(i);
  minimum[i]=std::max(0.,double(radii[radius_queue[rf]])-margin);
  minimum_bend[i]=bends[bend_queue[bf]];
 }
}
static unsigned audit_state(double minimum,double bend,double required,double threshold){
#pragma HLS INLINE
 double spare=minimum-required;
 return spare < -1e-5||(threshold>0&&bend+1e-5<threshold)?2:(spare<.4?1:0);
}
