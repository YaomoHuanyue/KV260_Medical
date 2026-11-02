#pragma once
#include <cstdint>
namespace depthcompose {
// RGBA8 straight alpha, followed by unsigned 24-bit depth and a valid bit.
// Layer 0 wins equal-depth ties. Output is RGBA8 over an opaque background.
struct Fragment {uint32_t rgba,depth;uint8_t index;bool valid;};
static void compare(Fragment&left,Fragment&right){
#pragma HLS INLINE
 uint32_t a=left.valid?left.depth:0xffffff,b=right.valid?right.depth:0xffffff;
 if(a<b||(a==b&&left.index<right.index)){Fragment t=left;left=right;right=t;}
}
static uint8_t blend(uint8_t source,uint8_t destination,uint8_t alpha){
#pragma HLS INLINE
 uint16_t t=uint16_t(source)*alpha+uint16_t(destination)*(255-alpha)+128;
 return uint8_t((t+(t>>8))>>8);
}
static uint32_t pixel(const uint32_t color[4],const uint32_t depth[4],uint32_t background){
#pragma HLS INLINE
 Fragment f[4];
#pragma HLS ARRAY_PARTITION variable=f complete
 for(unsigned j=0;j<4;++j){
#pragma HLS UNROLL
  f[j]={color[j],depth[j]&0xffffff,uint8_t(j),(depth[j]>>24)!=0};
 }
 compare(f[0],f[1]);compare(f[2],f[3]);compare(f[0],f[2]);compare(f[1],f[3]);compare(f[1],f[2]);
 uint8_t result[3]={uint8_t(background),uint8_t(background>>8),uint8_t(background>>16)};
#pragma HLS ARRAY_PARTITION variable=result complete
 for(unsigned j=0;j<4;++j){
#pragma HLS UNROLL
  uint8_t alpha=f[j].valid?uint8_t(f[j].rgba>>24):0;
  for(unsigned channel=0;channel<3;++channel){
#pragma HLS UNROLL
   result[channel]=blend(uint8_t(f[j].rgba>>(8*channel)),result[channel],alpha);
  }
 }
 return uint32_t(result[0])|(uint32_t(result[1])<<8)|(uint32_t(result[2])<<16)|0xff000000U;
}
}
