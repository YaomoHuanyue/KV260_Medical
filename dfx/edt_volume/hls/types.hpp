#pragma once
#include <cstdint>
#include <cstring>
#ifdef EDT_VOLUME_NATIVE
#include <queue>
#include <stdexcept>
struct VolumeWord { uint64_t lane[8]{}; };
template<class T> class VolumeStream {
 std::queue<T> queue;
public:
 void write(const T& value){queue.push(value);}
 T read(){if(queue.empty())throw std::runtime_error("volume stream underflow");T value=queue.front();queue.pop();return value;}
};
inline uint64_t cost(const VolumeWord&word,unsigned lane){return word.lane[lane];}
inline void cost(VolumeWord&word,unsigned lane,uint64_t value){word.lane[lane]=value;}
inline unsigned byte(const VolumeWord&word,unsigned index){return unsigned(word.lane[index/8]>>(8*(index%8)))&255;}
inline void bits32(VolumeWord&word,unsigned index,uint32_t value){unsigned l=index/2,s=(index%2)*32;word.lane[l]=(word.lane[l]&~(uint64_t(0xffffffff)<<s))|(uint64_t(value)<<s);}
#else
#include <ap_int.h>
#include <hls_stream.h>
using VolumeWord=ap_uint<512>;
template<class T> using VolumeStream=hls::stream<T>;
inline uint64_t cost(const VolumeWord&word,unsigned lane){return uint64_t(word.range(64*lane+63,64*lane));}
inline void cost(VolumeWord&word,unsigned lane,uint64_t value){word.range(64*lane+63,64*lane)=value;}
inline unsigned byte(const VolumeWord&word,unsigned index){return unsigned(word.range(index*8+7,index*8));}
inline void bits32(VolumeWord&word,unsigned index,uint32_t value){word.range(32*index+31,32*index)=value;}
#endif
constexpr unsigned VOLUME_MAX_LINE=1024,VOLUME_LANES=8,VOLUME_STRIPE_WORDS=16;
// Interface depth describes the C/RTL fixture allocation, not a runtime limit.
constexpr unsigned VOLUME_SIM_WORDS=2048;
constexpr uint64_t VOLUME_INF=~uint64_t(0);
extern "C" void edt_volume(const VolumeWord*mask,VolumeWord*work_a,VolumeWord*work_b,VolumeWord*distance,
 unsigned nz,unsigned ny,unsigned nx,uint32_t wz,uint32_t wy,uint32_t wx,unsigned&status);
