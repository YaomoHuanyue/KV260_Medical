#pragma once
#include <cstdint>
#ifdef CT_NATIVE
#include <queue>
#include <stdexcept>
using W64=uint64_t;
struct W256 { uint32_t v[8]={}; };
template<class W> struct Packet { W data{}; uint32_t keep=0xffffffffu,strb=0xffffffffu; bool last=false; };
using P64=Packet<W64>;using P256=Packet<W256>;
template<class T> class Stream { std::queue<T> q; public:
 void write(T v){q.push(v);} T read(){if(q.empty())throw std::runtime_error("stream underflow");T v=q.front();q.pop();return v;} bool empty()const{return q.empty();} };
inline int8_t byte64(W64 w,unsigned i){return int8_t(w>>(8*i));}
inline int8_t byte256(W256 w,unsigned i){return int8_t(w.v[i/4]>>(8*(i%4)));}
inline void setbyte(W256& w,unsigned i,int8_t v){unsigned b=8*(i%4);w.v[i/4]=(w.v[i/4]&~(255u<<b))|(uint32_t(uint8_t(v))<<b);}
inline void setlane(W256& w,unsigned i,int32_t v){w.v[i]=uint32_t(v);}
inline int32_t lane(W256 w,unsigned i){return int32_t(w.v[i]);}
#else
#include <ap_int.h>
#include <ap_axi_sdata.h>
#include <hls_stream.h>
using W64=ap_uint<64>;using W256=ap_uint<256>;
using P64=ap_axiu<64,0,0,0>;using P256=ap_axiu<256,0,0,0>;
template<class T>using Stream=hls::stream<T>;
inline int8_t byte64(W64 w,unsigned i){return ap_int<8>(w.range(i*8+7,i*8));}
inline int8_t byte256(W256 w,unsigned i){return ap_int<8>(w.range(i*8+7,i*8));}
inline void setbyte(W256& w,unsigned i,int8_t v){w.range(i*8+7,i*8)=v;}
inline void setlane(W256& w,unsigned i,int32_t v){w.range(i*32+31,i*32)=v;}
inline int32_t lane(W256 w,unsigned i){return ap_int<32>(w.range(i*32+31,i*32));}
#endif
inline W64 word64(W256 w,unsigned i){
#ifdef CT_NATIVE
 return W64(w.v[2*i])|(W64(w.v[2*i+1])<<32);
#else
 return w.range(i*64+63,i*64);
#endif
}
inline void setword64(W256& w,unsigned i,W64 v){
#ifdef CT_NATIVE
 w.v[2*i]=uint32_t(v);w.v[2*i+1]=uint32_t(v>>32);
#else
 w.range(i*64+63,i*64)=v;
#endif
}
inline uint32_t valid_bytes(unsigned words){return words>=4?0xffffffffu:((1u<<(words*8))-1u);}
inline bool valid_shape(unsigned h,unsigned w,unsigned ci,unsigned co,unsigned k){return h>=1&&h<=512&&w>=1&&w<=512&&ci>=1&&ci<=64&&co>=1&&co<=64&&(k==1||k==3);}
extern "C" void ct_reader(const W256* input,Stream<P256>& pixels,uint32_t height,uint32_t width,uint32_t cin,uint32_t kernel);
extern "C" void ct_conv(const W256* weights,Stream<P256>& pixels,Stream<P256>& sums,uint32_t height,uint32_t width,uint32_t cin,uint32_t cout,uint32_t kernel,uint32_t& status);
extern "C" void ct_writer(Stream<P256>& sums,W256* output,uint32_t count,uint32_t& status,const W256* parameters=nullptr,uint32_t mode=0,uint32_t channels=8,uint32_t output_scale_bits=0x3f800000,uint32_t output_zero=0);
