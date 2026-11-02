#pragma once
#include <cstdint>
#ifndef SM_GRAPH_AXIS_NATIVE
#include <ap_int.h>
#include <ap_axi_sdata.h>
#include <hls_stream.h>
#endif

namespace smooth_graph_axis {
constexpr uint32_t MAX_VERTICES=1000000;
constexpr uint32_t MAX_EDGES=12000000;
enum Error : uint32_t { BAD_CONFIG=1, KEEP=2, STRB=4, USER=8, LAST=16,
    PADDING=32, INDEX=64, WEIGHT=128 };

#ifdef SM_GRAPH_AXIS_NATIVE
struct Word {
    uint64_t data[8];
    uint64_t keep,strb;
    uint8_t user,last;
};
struct Stream {
    void* context;
    Word (*reader)(void*);
    Word read(){return reader(context);}
};
#else
using Word=ap_axiu<512,1,0,0>;
using Stream=hls::stream<Word>;
#endif

struct Quarter {
    uint64_t edges[4];
    uint8_t count;
};

// Real algorithm edge payload: one quarter per call, at most one512-bit input
// read per call. Tile consumers retain unused quarter lanes at tile boundaries.
// This component does not implement the numeric smoothing or a DFX wrapper.
class Reader {
    Stream& input;
    uint32_t nv,total,used,beats,received,errors;
    Word word;
    bool upper;
public:
    Reader(Stream& source,uint32_t vertices,uint32_t nnz)
        :input(source),nv(vertices),total(nnz),used(0),beats((nnz+7)/8),
         received(0),errors(0),word{},upper(false){
#pragma HLS inline
        if(vertices<1||vertices>MAX_VERTICES||nnz>MAX_EDGES){
            errors=BAD_CONFIG;total=0;beats=0;
        }
    }
    bool done()const{return used==total;}
    uint32_t status()const{return errors;}
    uint32_t consumed_edges()const{return used;}
    uint32_t consumed_beats()const{return received;}

    Quarter next4(){
#pragma HLS inline
        Quarter result{};
#pragma HLS array_partition variable=result.edges complete
        if(done())return result;
        if(!upper){
            word=input.read();
            if(uint64_t(word.keep)!=~uint64_t(0))errors|=KEEP;
            if(uint64_t(word.strb)!=~uint64_t(0))errors|=STRB;
            if(bool(word.user)!=(received==0))errors|=USER;
            if(bool(word.last)!=(received+1==beats))errors|=LAST;
            if(received+1==beats && (total&7)){
                check_tail:for(unsigned lane=0;lane<8;++lane){
#pragma HLS unroll
                    if(lane>=(total&7)){
#ifdef SM_GRAPH_AXIS_NATIVE
                        if(word.data[lane])errors|=PADDING;
#else
                        if(word.data.range(lane*64+63,lane*64)!=0)errors|=PADDING;
#endif
                    }
                }
            }
            ++received;
        }
        result.count=uint8_t(total-used<4?total-used:4);
        unpack4:for(unsigned lane=0;lane<4;++lane){
#pragma HLS unroll
            if(lane<result.count){
#ifdef SM_GRAPH_AXIS_NATIVE
                uint64_t packed=word.data[(upper?4:0)+lane];
#else
                uint64_t packed=word.data.range(lane*64+63,lane*64);
#endif
                const uint32_t index=uint32_t(packed),weight=uint32_t(packed>>32);
                const bool bad_index=index>=nv;
                const bool bad_weight=(weight&0x7f800000u)==0x7f800000u;
                if(bad_index)errors|=INDEX;
                if(bad_weight)errors|=WEIGHT;
                // Never let a corrupted index become a DDR/cache address.
                result.edges[lane]=(bad_index||bad_weight)?0:packed;
            }
        }
#ifndef SM_GRAPH_AXIS_NATIVE
        word.data>>=256;
#endif
        upper=!upper;used+=result.count;
        return result;
    }
};
}
