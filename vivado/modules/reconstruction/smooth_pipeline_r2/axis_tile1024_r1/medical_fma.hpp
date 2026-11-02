#pragma once
#include "finite_fma.hpp"
// The certified leaf handles all finite binary32 operands. A finite product
// accumulated into an infinity must preserve that infinity, including when
// the exact product would overflow after rounding. Nonfinite multiplicands
// are outside the validated medical input domain; invalid math remains NaN.
static float medical_fma(float a,float b,float c){
#pragma HLS inline
    union{float f;uint32_t u;}aa,bb,cc,out;aa.f=a;bb.f=b;cc.f=c;
    bool af=((aa.u>>23)&255)!=255,bf=((bb.u>>23)&255)!=255;
    if(af&&bf&&(cc.u&0x7fffffffu)==0x7f800000u)return c;
    out.u=finite_fma::bits(aa.u,bb.u,cc.u);return out.f;
}
static SmoothPoint accumulate_neighbor(SmoothPoint sum,SmoothPoint p,float w){
#pragma HLS inline off
    return {medical_fma(p.x,w,sum.x),medical_fma(p.y,w,sum.y),medical_fma(p.z,w,sum.z),0};
}
