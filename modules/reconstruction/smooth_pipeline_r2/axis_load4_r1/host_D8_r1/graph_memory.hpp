#pragma once
#include "protocol.hpp"
#include <cstring>
#include <functional>
#include <utility>

namespace smooth_d8 {
// BO has XRT's address/size/map surface. Coherence supplies explicit to/from
// device synchronization. No buffer allocation occurs per REQUEST.
template<class BO,class Coherence>
class GraphHeaderMemory {
    static constexpr size_t guard=4096;
    BO& graph;BO& header;
    Coherence coherence;
    std::function<void(const char*)> retain;
    Config uploaded{};
    bool prepared=false;
    size_t payload=0;
    void physical(const BO& bo,size_t bytes)const {
        require(bo.address()%64==0&&bo.address()<0x80000000ULL&&
                uint64_t(bytes)+2*guard<=0x80000000ULL-bo.address(),"D8 BO outside aligned low DDR");
        require(bo.size()>=bytes+2*guard,"D8 BO too small for payload and guards");
    }
    void seed_guards(BO& bo,size_t bytes) {
        auto* p=bo.template map<unsigned char*>();
        std::memset(p,0xa7,guard);std::memset(p+guard+bytes,0xa7,guard);
    }
    void check(BO& bo,size_t bytes) {
        coherence.from_device(bo,guard,0);coherence.from_device(bo,guard,guard+bytes);
        const auto* p=bo.template map<const unsigned char*>();
        for(size_t i=0;i<guard;++i)require(p[i]==0xa7&&p[guard+bytes+i]==0xa7,"D8 graph/header DMA guard damaged");
    }
public:
    GraphHeaderMemory(BO& source,BO& receiver,Coherence cache,std::function<void(const char*)> retainer)
        :graph(source),header(receiver),coherence(std::move(cache)),retain(std::move(retainer)){}
    uint64_t graph_address()const{return graph.address()+guard;}
    uint64_t header_address()const{return header.address()+guard;}
    void prepare(Config config,const void* edges,size_t bytes) {
        config.validate();prepared=false;
        require(config.graph_address==graph_address()&&bytes==size_t(config.edges)*8&&(edges||bytes==0),
                "D8 graph input size/owner invalid before upload");
        payload=size_t(config.beats())*64;
        physical(graph,payload);physical(header,64);
        require(header.address()+64+2*guard<=graph.address()||
                graph.address()+payload+2*guard<=header.address(),"D8 guarded BO physical ranges overlap");
        seed_guards(graph,payload);seed_guards(header,64);
        auto* p=graph.template map<unsigned char*>()+guard;
        if(bytes)std::memcpy(p,edges,bytes);
        if(payload>bytes)std::memset(p+bytes,0,payload-bytes);
        coherence.to_device(graph,payload+2*guard,0);
        // Every header byte is overwritten by DMA. Only CPU-written guards
        // need an initial clean; each received header is then invalidated.
        coherence.to_device(header,guard,0);coherence.to_device(header,guard,guard+64);
        uploaded=config;prepared=true;
    }
    void validate(Config config)const {
        require(prepared&&config.vertices==uploaded.vertices&&config.edges==uploaded.edges&&
                config.iterations==uploaded.iterations&&config.graph_address==uploaded.graph_address,
                "D8 graph not prepared for this task");
        physical(graph,payload);physical(header,64);
    }
    std::array<uint32_t,16> invalidate_and_copy_header() {
        require(prepared,"D8 header before upload");
        coherence.from_device(header,64,guard);
        std::array<uint32_t,16> words;
        std::memcpy(words.data(),header.template map<const unsigned char*>()+guard,64);return words;
    }
    void check_guards(){check(graph,payload);check(header,64);}
    [[noreturn]] void retain_active(const char* message){retain(message);std::terminate();}
};
}
