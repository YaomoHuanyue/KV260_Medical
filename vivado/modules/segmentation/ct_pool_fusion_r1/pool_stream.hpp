#pragma once
#include "../ct_pl/stream_types.hpp"

// Internal C5 writer stream: one word contains eight signed INT8 channels.
// Preserve the full-resolution branch for U-Net skips while producing the
// 2x2 stride2 max-pool branch without rereading the activation from DDR.
namespace ct_pool_fusion {
static constexpr unsigned max_words=512u*512u*8u;
inline bool valid(unsigned words,unsigned h,unsigned w,unsigned c){
 return h>=2&&h<=512&&w>=2&&w<=512&&!(h&1)&&!(w&1)&&
        c>=8&&c<=64&&!(c&(c-1))&&words==h*w*(c/8);
}
inline W64 signed_max8(W64 a,W64 b){
#pragma HLS INLINE
 W64 result=0;
 for(unsigned lane=0;lane<8;++lane){
#pragma HLS UNROLL
  const int8_t av=byte64(a,lane),bv=byte64(b,lane);
  result|=W64(uint8_t(av>bv?av:bv))<<(lane*8);
 }
 return result;
}
static void forward_pool(Stream<W64>& input,Stream<W64>& full,Stream<W64>& pooled,
                         const W256* lut,unsigned words,unsigned h,unsigned w,unsigned c,uint32_t& status){
#pragma HLS INLINE off
 if(words>max_words){status=8;return;}
 if(!valid(words,h,w,c)){
  // Geometry errors do not trap an already-started upstream stream. Forward
  // the bounded original transaction, report error and emit no pooled data.
  for(unsigned i=0;i<words;++i){
#pragma HLS PIPELINE II=1
   full.write(input.read());
  }
  status=4;return;
 }
 int8_t table[8][256];
#pragma HLS ARRAY_PARTITION variable=table complete dim=1
#pragma HLS BIND_STORAGE variable=table type=ram_1p impl=lutram
 for(unsigned block=0;block<8;++block){
  const W256 value=lut[block];
  for(unsigned i=0;i<32;++i){
#pragma HLS PIPELINE II=1
   for(unsigned lane=0;lane<8;++lane){
#pragma HLS UNROLL
    table[lane][32*block+i]=byte256(value,i);
   }
  }
 }
 W64 previous[256*8],left[8];
#pragma HLS BIND_STORAGE variable=previous type=ram_1p impl=bram
#pragma HLS ARRAY_PARTITION variable=left complete
 const unsigned groups=c/8;
 for(unsigned y=0;y<h;++y)for(unsigned x=0;x<w;++x)for(unsigned group=0;group<groups;++group){
#pragma HLS PIPELINE II=1
  const W64 value=input.read();full.write(value);
  if(!(x&1)){left[group]=value;}
  else{
   const W64 horizontal=signed_max8(left[group],value);
   const unsigned address=(x/2)*groups+group;
   if(!(y&1)){previous[address]=horizontal;}
   else{
    const W64 maximum=signed_max8(previous[address],horizontal);
    W64 mapped=0;
    for(unsigned lane=0;lane<8;++lane){
#pragma HLS UNROLL
     mapped|=W64(uint8_t(table[lane][uint8_t(byte64(maximum,lane))]))<<(lane*8);
    }
    pooled.write(mapped);
   }
  }
 }
 status=0;
}
}
