#pragma once
#include <cmath>
#include <algorithm>
#include <limits>
#include <cstdint>
#include <cstring>
#include "types.hpp"
constexpr unsigned AUDIT_POINTS=4096;
constexpr unsigned AUDIT_ANGLE_LANES=2;
constexpr uint64_t AUDIT_QUERY_TAG=0x4155444954303031ULL;
#include "cordic_constants.hpp"
#include "reciprocal_constants.hpp"
#ifndef NAV_NATIVE
#include <ap_int.h>
#include <hls_stream.h>
using AuditInteger=ap_int<64>;
#else
using AuditInteger=int64_t;
#endif
struct AuditTurn{AuditInteger y;double half_length;bool negative,valid;};
static double audit_reciprocal(double value){
#pragma HLS INLINE
 // Angles passed here exceed 1e-6 and are at most pi, hence normal binary64.
 uint64_t input;std::memcpy(&input,&value,8);
 unsigned exponent=unsigned(input>>52)&2047,index=unsigned(input>>44)&255;
 uint64_t normalized=(input&0xfffffffffffffULL)|(uint64_t(1023)<<52);
 double mantissa;std::memcpy(&mantissa,&normalized,8);
 double inverse=audit_reciprocal_table[index];
 for(unsigned iteration=0;iteration<3;++iteration){
  inverse=inverse*(2.-mantissa*inverse);
 }
 uint64_t result;std::memcpy(&result,&inverse,8);
 unsigned adjusted=unsigned((result>>52)&2047)+1023-exponent;
 result=(result&0xfffffffffffffULL)|(uint64_t(adjusted)<<52);
 std::memcpy(&inverse,&result,8);return inverse;
}
static void audit_rotation(AuditInteger&x,AuditInteger&y,AuditInteger&z,unsigned j){
#pragma HLS INLINE
 AuditInteger old_x=x,old_y=y,delta=audit_angle_table[j];
 if(old_y>0){x=old_x+(old_y>>j);y=old_y-(old_x>>j);z+=delta;}
 else if(old_y<0){x=old_x-(old_y>>j);y=old_y+(old_x>>j);z-=delta;}
}
static double audit_angle(AuditInteger z,bool negative){
#pragma HLS INLINE
#ifdef NAV_NATIVE
 double value=double(z);
#else
 double value=z.to_double();
#endif
 double angle=value*(2./1152921504606846976.);
 return negative?3.1415926535897932384626433832795-angle:angle;
}
static double audit_divide(double numerator,double denominator){
#pragma HLS INLINE off
#pragma HLS PIPELINE II=1
 return numerator/denominator;
}
static AuditTurn audit_turn(double cosine,double half_length,bool valid){
#pragma HLS INLINE
 double magnitude=std::abs(cosine),t=std::sqrt(audit_divide(1-magnitude,1+magnitude));
 // Convert through int64_t: ap_int's double constructor truncates via a
 // narrower intermediate in this HLS simulation runtime.
 int64_t scaled=static_cast<int64_t>(t*1152921504606846976.);
 return {AuditInteger(scaled),half_length,cosine<0,valid};
}
static double audit_acos(double cosine){
 AuditTurn a=audit_turn(cosine,0,true);AuditInteger x=AuditInteger(1)<<60,y=a.y,z=0;
 for(unsigned j=0;j<56;++j)audit_rotation(x,y,z,j);
 return audit_angle(z,a.negative);
}
static AuditTurn audit_geometry(const double p[AUDIT_POINTS][3],unsigned i,unsigned n){
#pragma HLS INLINE
 if(!i||i+1>=n)return {0,0,false,false};
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
 double cosine=std::max(-1.,std::min(1.,audit_divide(dot,std::max(left*right,1e-20))));
 return audit_turn(cosine,.5*(left+right),left>1e-8&&right>1e-8);
}
#ifdef NAV_NATIVE
static void audit_bends(const double p[AUDIT_POINTS][3],unsigned n,double bends[AUDIT_POINTS]){
 for(unsigned i=0;i<n;++i){
  auto a=audit_geometry(p,i,n);AuditInteger x=AuditInteger(1)<<60,y=a.y,z=0;
  for(unsigned j=0;j<56;++j)audit_rotation(x,y,z,j);
  double angle=audit_angle(z,a.negative);
  bends[i]=a.valid&&angle>1e-6?a.half_length*audit_reciprocal(angle):std::numeric_limits<double>::infinity();
 }
}
#endif

// IEEE order keys preserve numeric comparisons exactly, including negative
// arcs, infinities and signed zero. No quantization or geometry change.
static uint64_t audit_key(double value){
#pragma HLS INLINE
 uint64_t raw;std::memcpy(&raw,&value,8);
 if((raw&0x7fffffffffffffffULL)==0)raw=0;
 return raw>>63?~raw:raw^0x8000000000000000ULL;
}
static uint32_t audit_key(float value){
#pragma HLS INLINE
 uint32_t raw;std::memcpy(&raw,&value,4);
 if((raw&0x7fffffffU)==0)raw=0;
 return raw>>31?~raw:raw^0x80000000U;
}
static double audit_double(uint64_t key){
#pragma HLS INLINE
 uint64_t raw=key>>63?key^0x8000000000000000ULL:~key;
 double value;std::memcpy(&value,&raw,8);return value;
}
static float audit_float(uint32_t key){
#pragma HLS INLINE
 uint32_t raw=key>>31?key^0x80000000U:~key;
 float value;std::memcpy(&value,&raw,4);return value;
}
struct AuditResolved{AuditInteger z;double half_length;bool negative,valid;};
struct AuditSample{uint64_t arc,end;uint32_t radius;unsigned index;double bend;};
struct AuditMinimum{unsigned index;float radius;double bend;};

// Traverse in reverse so bend calculation and forward-window reduction can
// run concurrently. Two iterative lanes retain all 56 Q60 rotations.
static void audit_produce(const double p[AUDIT_POINTS][3],unsigned n,Stream<AuditTurn>&out){
#pragma HLS INLINE off
#pragma HLS ALLOCATION instances=audit_divide limit=1 function
 for(unsigned remaining=n;remaining;--remaining){
#pragma HLS PIPELINE II=32
  unsigned i=remaining-1;
  out.write(audit_geometry(p,i,n));
 }
}
static void audit_cordic(Stream<AuditTurn>&in,Stream<AuditResolved>&out,unsigned n){
#pragma HLS INLINE off
 for(unsigned block=0;block<n;block+=AUDIT_ANGLE_LANES){
  AuditTurn data[AUDIT_ANGLE_LANES];AuditInteger x[AUDIT_ANGLE_LANES],y[AUDIT_ANGLE_LANES],z[AUDIT_ANGLE_LANES];
#pragma HLS ARRAY_PARTITION variable=data complete
#pragma HLS ARRAY_PARTITION variable=x complete
#pragma HLS ARRAY_PARTITION variable=y complete
#pragma HLS ARRAY_PARTITION variable=z complete
  for(unsigned k=0;k<AUDIT_ANGLE_LANES;++k){
#pragma HLS PIPELINE II=1
   data[k]=block+k<n?in.read():AuditTurn{};x[k]=AuditInteger(1)<<60;y[k]=data[k].y;z[k]=0;
  }
  for(unsigned j=0;j<56;++j){
#pragma HLS PIPELINE II=1
   for(unsigned k=0;k<AUDIT_ANGLE_LANES;++k){
#pragma HLS UNROLL
    audit_rotation(x[k],y[k],z[k],j);
   }
  }
  for(unsigned k=0;k<AUDIT_ANGLE_LANES;++k){
#pragma HLS PIPELINE II=1
   auto a=data[k];if(block+k<n)out.write({z[k],a.half_length,a.negative,a.valid});
  }
 }
}
static void audit_finish(Stream<AuditResolved>&in,Stream<AuditSample>&out,const double arcs[AUDIT_POINTS],const float radii[AUDIT_POINTS],unsigned n,double window,double bends[AUDIT_POINTS]){
#pragma HLS INLINE off
 for(unsigned i=0;i<n;++i){
#pragma HLS PIPELINE II=32
  auto a=in.read();double angle=audit_angle(a.z,a.negative);
  double bend=a.valid&&angle>1e-6?a.half_length*audit_reciprocal(angle):std::numeric_limits<double>::infinity();
  unsigned index=n-1-i;
  bends[index]=bend;out.write({audit_key(arcs[index]),audit_key(arcs[index]+window),audit_key(radii[index]),index,bend});
 }
}
// Queue entries contain keys directly: no random URAM lookup or serial FP
// comparator while expiring/popping entries. The window remains inclusive.
static void audit_reduce(Stream<AuditSample>&in,Stream<AuditMinimum>&out,unsigned n){
#pragma HLS INLINE off
 uint64_t radius_arc[AUDIT_POINTS],bend_arc[AUDIT_POINTS],bend_key[AUDIT_POINTS];
 uint32_t radius_key[AUDIT_POINTS];
#pragma HLS BIND_STORAGE variable=radius_arc type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=bend_arc type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=bend_key type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=radius_key type=ram_2p impl=bram
 unsigned rf=0,rb=0,bf=0,bb=0;
 for(unsigned count=0;count<n;++count){
  auto a=in.read();uint64_t bend=audit_key(a.bend);
  while(rf<rb&&radius_arc[rf]>a.end)++rf;
  while(bf<bb&&bend_arc[bf]>a.end)++bf;
  while(rb>rf&&radius_key[rb-1]>=a.radius)--rb;
  while(bb>bf&&bend_key[bb-1]>=bend)--bb;
  radius_arc[rb]=a.arc;radius_key[rb++]=a.radius;
  bend_arc[bb]=a.arc;bend_key[bb++]=bend;
  out.write({a.index,audit_float(radius_key[rf]),audit_double(bend_key[bf])});
 }
}
static unsigned audit_state(double minimum,double bend,double required,double threshold){
#pragma HLS INLINE
 double spare=minimum-required;
 return spare < -1e-5||(threshold>0&&bend+1e-5<threshold)?2:(spare<.4?1:0);
}
static uint64_t audit_state_bits(uint8_t state){
#pragma HLS INLINE
 return state==2?0x4000000000000000ULL:state==1?0x3ff0000000000000ULL:0;
}
static double audit_sum(double a,double b){
#pragma HLS INLINE off
#pragma HLS PIPELINE II=1
 return a+b;
}
static void audit_store(Stream<AuditMinimum>&in,unsigned n,double margin,double required,double threshold,double minimum[AUDIT_POINTS],double minimum_bend[AUDIT_POINTS],double spare[AUDIT_POINTS],uint8_t state[AUDIT_POINTS]){
#pragma HLS INLINE off
#pragma HLS ALLOCATION instances=audit_sum limit=1 function
 for(unsigned count=0;count<n;++count){
#pragma HLS PIPELINE II=32
  auto a=in.read();double value=std::max(0.,audit_sum(double(a.radius),-margin));
  double gap=audit_sum(value,-required),adjusted=audit_sum(a.bend,1e-5);
  minimum[a.index]=value;minimum_bend[a.index]=a.bend;spare[a.index]=gap;
  state[a.index]=uint8_t(gap < -1e-5||(threshold>0&&adjusted<threshold)?2:(gap<.4?1:0));
 }
}
static void audit_statistics(const double p[AUDIT_POINTS][3],const double arcs[AUDIT_POINTS],const float radii[AUDIT_POINTS],unsigned n,double window,double margin,double required,double threshold,double bends[AUDIT_POINTS],double minimum[AUDIT_POINTS],double minimum_bend[AUDIT_POINTS],double spare[AUDIT_POINTS],uint8_t state[AUDIT_POINTS]){
#pragma HLS INLINE off
#pragma HLS DATAFLOW
 Stream<AuditTurn>turns;Stream<AuditResolved>resolved;Stream<AuditSample>samples;Stream<AuditMinimum>minima;
#pragma HLS STREAM variable=turns depth=16
#pragma HLS STREAM variable=resolved depth=16
#pragma HLS STREAM variable=samples depth=16
#pragma HLS STREAM variable=minima depth=16
 audit_produce(p,n,turns);
 audit_cordic(turns,resolved,n);
 audit_finish(resolved,samples,arcs,radii,n,window,bends);
 audit_reduce(samples,minima,n);
 audit_store(minima,n,margin,required,threshold,minimum,minimum_bend,spare,state);
}
