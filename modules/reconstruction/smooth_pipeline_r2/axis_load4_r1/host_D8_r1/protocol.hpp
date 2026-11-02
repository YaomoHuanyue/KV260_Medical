#pragma once
#include <array>
#include <cstdint>
#include <stdexcept>

namespace smooth_d8 {
inline void require(bool value,const char* message) {
    if(!value)throw std::runtime_error(message);
}
struct Config {
    uint32_t vertices,edges,iterations;
    uint64_t graph_address;
    uint32_t beats()const{return (edges+7)/8;}
    uint32_t maximum_requests()const{return edges?1+8*iterations:0;}
    void validate()const {
        require(vertices>=1&&vertices<=1000000,"D8 vertices outside ABI");
        require(edges<=12000000&&iterations>=1&&iterations<=16,"D8 edges/iterations outside ABI");
        require(graph_address&&graph_address%64==0&&graph_address<0x80000000ULL,
                "D8 graph must be an aligned owned low-DDR buffer");
        require(uint64_t(beats())*64<=0x80000000ULL-graph_address,"D8 graph range outside low DDR");
    }
};
struct Result {uint32_t requests=0,graph_beats=0,stream_errors=0;};
class Protocol {
    Config config;
    Result state;
    bool finished=false;
public:
    explicit Protocol(Config value):config(value){config.validate();}
    // The static writer has already checked KEEP/STRB/USER/LAST. All header
    // fields, including its owner address, are checked before scheduling DMA.
    uint32_t accept(const std::array<uint32_t,16>& f) {
        require(!finished,"D8 frame after FINAL");
        require(f[0]==0x31474d53u&&f[1]==1,"D8 header magic/version mismatch");
        require(f[2]==1||f[2]==2,"D8 unknown frame kind");
        require(f[3]==state.requests&&f[4]==config.vertices&&f[5]==config.edges&&f[6]==config.beats(),
                "D8 header sequence or configuration mismatch");
        require((uint64_t(f[8])|(uint64_t(f[9])<<32))==config.graph_address,
                "D8 header names a different graph owner");
        require(f[10]==state.requests*config.beats(),"D8 consumed graph count mismatch");
        for(unsigned i=11;i<16;++i)require(f[i]==0,"D8 reserved header word is nonzero");
        require((f[7]&~511u)==0&&(f[7]&state.stream_errors)==state.stream_errors,
                "D8 unknown or regressed stream error bits");
        state.stream_errors=f[7];
        if(f[2]==1) {
            require(config.edges&&state.requests<config.maximum_requests(),"D8 excessive/empty graph request");
            ++state.requests;state.graph_beats+=config.beats();
        }else {
            require(!config.edges||state.requests>0||state.stream_errors,
                    "D8 successful nonempty graph finalized without reading its input");
            finished=true;
        }
        return f[2];
    }
    Result result()const {require(finished,"D8 missing FINAL");return state;}
};
}
