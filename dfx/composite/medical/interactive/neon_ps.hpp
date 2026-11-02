#pragma once
// Independent strongest PS comparison candidate. Same exact byte rounding,
// original layer order and input ownership; no changed geometry or opacity.
#include <arm_neon.h>
namespace medical_render {
static uint8x8_t exactBlend8(uint8x8_t carry,uint8x8_t source,uint8x8_t alpha){
 uint16x8_t t=vaddq_u16(vmull_u8(source,alpha),vmull_u8(carry,vsub_u8(vdup_n_u8(255),alpha)));
 t=vaddq_u16(t,vdupq_n_u16(128));
 return vshrn_n_u16(vaddq_u16(t,vshrq_n_u16(t,8)),8);
}
static void fusedOrderedNeon(const std::vector<std::vector<uint32_t>>&colors,std::vector<uint32_t>&out,unsigned threads,unsigned activeLayers=0){
 check(!colors.empty()&&out.size()%8==0&&activeLayers<=colors.size(),"NEON exact blend dimensions invalid");
 const int blocks=int(out.size()/8),layers=int(activeLayers?activeLayers:colors.size());
 #pragma omp parallel for num_threads(threads) schedule(static)
 for(int block=0;block<blocks;++block){
  uint8x8x4_t carry;for(unsigned c=0;c<3;++c)carry.val[c]=vdup_n_u8((medical_live::background>>(8*c))&255);
  carry.val[3]=vdup_n_u8(255);
  auto apply=[&](int rank){
   auto source=vld4_u8(reinterpret_cast<const uint8_t*>(colors[rank].data()+block*8));
   for(unsigned c=0;c<3;++c)carry.val[c]=exactBlend8(carry.val[c],source.val[c],source.val[3]);
  };
  apply(0);for(int rank=layers-1;rank>0;--rank)apply(rank);
  vst4_u8(reinterpret_cast<uint8_t*>(out.data()+block*8),carry);
 }
}
}
