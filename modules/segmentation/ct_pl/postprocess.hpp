#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#if defined(__aarch64__)
#include <arm_neon.h>
#endif

// Preserve separate float32 multiply/divide and nearest-even rounding.
// Compile with -ffp-contract=off and without -ffast-math.
inline void quantize_acc(const int32_t* acc,int8_t* output,unsigned pixels,unsigned channels,
                         const int32_t* bias,const float* scale,float qscale,int zero){
 for(unsigned p=0;p<pixels;p++){
  unsigned c=0;
#if defined(__aarch64__)
  const auto divisor=vdupq_n_f32(qscale);
  const auto lo=vdupq_n_f32(float(-128-zero)),hi=vdupq_n_f32(float(127-zero));
  for(;c+4<=channels;c+=4){
   auto sum=vaddq_s32(vld1q_s32(acc+p*channels+c),vld1q_s32(bias+c));
   auto value=vmulq_f32(vcvtq_f32_s32(sum),vld1q_f32(scale+c));
   value=vdivq_f32(value,divisor);
   value=vminq_f32(vmaxq_f32(value,lo),hi);
   auto q=vaddq_s32(vcvtnq_s32_f32(value),vdupq_n_s32(zero));
   auto narrow=vmovn_s16(vcombine_s16(vmovn_s32(q),vdup_n_s16(0)));
   uint32_t packed=vget_lane_u32(vreinterpret_u32_s8(narrow),0);
   std::memcpy(output+p*channels+c,&packed,4);
  }
#endif
  for(;c<channels;c++){
   // Unsigned addition preserves the reference int32 wrapping semantics.
   int32_t sum=int32_t(uint32_t(acc[p*channels+c])+uint32_t(bias[c]));
   float value=float(sum)*scale[c];value=value/qscale;
   value=std::min(float(127-zero),std::max(float(-128-zero),value));
   output[p*channels+c]=int8_t(int(std::nearbyintf(value))+zero);
  }
 }
}
