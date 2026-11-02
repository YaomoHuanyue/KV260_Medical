#pragma once
#include <cstdint>
#include <cstring>
#ifdef NAV_NATIVE
#include <queue>
#include <stdexcept>
struct Word { uint64_t value[8]{}; };
struct Packet { Word data; uint64_t keep=~uint64_t(0),strb=~uint64_t(0);bool last=false,user=false; };
template<class T> class Stream {
    std::queue<T> q;
public:
    void write(const T& value){q.push(value);}
    T read(){if(q.empty())throw std::runtime_error("stream underflow");T x=q.front();q.pop();return x;}
    bool empty()const{return q.empty();}
};
inline uint64_t lane(const Word& w,unsigned i){return w.value[i];}
inline void lane(Word& w,unsigned i,uint64_t x){w.value[i]=x;}
#else
#include <ap_int.h>
#include <ap_axi_sdata.h>
#include <hls_stream.h>
using Word=ap_uint<512>;
using Packet=ap_axiu<512,1,0,0>;
template<class T> using Stream=hls::stream<T>;
inline uint64_t lane(const Word& w,unsigned i){return uint64_t(w.range(64*i+63,64*i));}
inline void lane(Word& w,unsigned i,uint64_t x){w.range(64*i+63,64*i)=x;}
#endif
constexpr unsigned NAV_LANES=8,NAV_MAX_LINE=1024,NAV_MAX_GROUPS=131072;
constexpr uint64_t NAV_INF=~uint64_t(0);
inline Packet packet(Word data,uint32_t id,uint32_t count){
    Packet p;p.data=data;p.keep=~uint64_t(0);p.strb=~uint64_t(0);p.last=id+1==count;p.user=id==0;return p;
}
extern "C" void nav_reader(const Word* input,Stream<Packet>& output,uint32_t count);
extern "C" void nav_edt(Stream<Packet>& input,Stream<Packet>& output,uint32_t length,uint32_t groups,
    uint32_t weight,uint32_t mode,uint32_t& status);
extern "C" void nav_writer(Stream<Packet>& input,Word* output,uint32_t count,uint32_t& status);
extern "C" void nav_route_writer(Stream<Packet>& input,Word* output,uint32_t capacity,uint32_t& status,uint32_t& written);
