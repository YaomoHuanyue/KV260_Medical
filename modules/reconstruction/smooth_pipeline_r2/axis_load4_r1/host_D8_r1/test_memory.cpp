#include "graph_memory.hpp"
#include <vector>
#include <iostream>
#include <tuple>

using namespace smooth_d8;
struct BO {
    uint64_t physical;
    std::vector<unsigned char> bytes;
    uint64_t address()const{return physical;}
    size_t size()const{return bytes.size();}
    template<class T>T map(){return reinterpret_cast<T>(bytes.data());}
};
struct Coherence {
    std::vector<std::tuple<char,uint64_t,size_t,size_t>>& events;
    void to_device(BO& bo,size_t length,size_t offset){events.emplace_back('T',bo.address(),length,offset);}
    void from_device(BO& bo,size_t length,size_t offset){events.emplace_back('F',bo.address(),length,offset);}
};
static unsigned tests=0;
static void check(bool value){require(value,"Graph/header memory test failed");}
template<class F>void rejects(F function){
    bool refused=false;try{function();}catch(const std::runtime_error&){refused=true;}
    check(refused);++tests;
}
int main(){
    for(uint32_t edges:{0u,1u,2u,7u,8u,9u,15u,16u,17u,511u,512u,513u,32767u,32768u,32769u}){
        Config config{513,edges,8,0x10001000};
        const size_t logical=size_t(edges)*8,padded=size_t(config.beats())*64;
        BO graph{0x10000000,std::vector<unsigned char>(8192+padded,0x5e)};
        BO header{0x20000000,std::vector<unsigned char>(8192+64,0x6d)};
        std::vector<std::tuple<char,uint64_t,size_t,size_t>> events;
        std::vector<unsigned char> source(logical);
        for(size_t i=0;i<logical;++i)source[i]=unsigned(i*31+7);
        GraphHeaderMemory<BO,Coherence> memory(graph,header,Coherence{events},[](const char* s){throw std::runtime_error(s);});
        rejects([&]{memory.validate(config);});
        memory.prepare(config,source.data(),source.size());memory.validate(config);
        check(events.size()==3&&events[0]==std::make_tuple('T',graph.address(),padded+8192,size_t(0)));
        check(std::equal(source.begin(),source.end(),graph.bytes.begin()+4096));
        for(size_t i=logical;i<padded;++i)check(graph.bytes[4096+i]==0);
        for(unsigned frame=0;frame<130;++frame){
            std::array<uint32_t,16> expected{};
            for(unsigned i=0;i<16;++i)expected[i]=(frame<<24)^i*0x16452d3u;
            std::memcpy(header.bytes.data()+4096,expected.data(),64);
            check(memory.invalidate_and_copy_header()==expected);
            check(events.back()==std::make_tuple('F',header.address(),size_t(64),size_t(4096)));
        }
        memory.check_guards();
        // All 130 replies reused the original graph upload; no repeated clean,
        // pack or full-graph copy is hidden in the per-request receiver.
        unsigned uploads=0;for(const auto& event:events)uploads+=std::get<0>(event)=='T'&&std::get<1>(event)==graph.address();
        check(uploads==1);
        auto changed=config;++changed.edges;rejects([&]{memory.validate(changed);});
        graph.bytes[0]^=1;rejects([&]{memory.check_guards();});graph.bytes[0]^=1;
        header.bytes.back()^=1;rejects([&]{memory.check_guards();});header.bytes.back()^=1;
        rejects([&]{memory.prepare(config,source.data(),source.size()+1);});
        rejects([&]{memory.validate(config);});++tests;
    }
    for(unsigned mode=0;mode<5;++mode){
        Config config{17,9,8,0x10001000};
        BO graph{0x10000000,std::vector<unsigned char>(8320,0x5e)};
        BO header{0x20000000,std::vector<unsigned char>(8256,0x6d)};
        if(mode==0)header.physical=graph.physical;
        if(mode==1)header.physical=0x80000000;
        if(mode==2)header.physical+=1;
        if(mode==3)graph.bytes.resize(8192);
        if(mode==4)header.bytes.resize(8192);
        std::vector<unsigned char> input(72);
        std::vector<std::tuple<char,uint64_t,size_t,size_t>> events;
        GraphHeaderMemory<BO,Coherence> memory(graph,header,Coherence{events},[](const char* s){throw std::runtime_error(s);});
        const auto before_graph=graph.bytes,before_header=header.bytes;
        rejects([&]{memory.prepare(config,input.data(),input.size());});
        check(events.empty()&&graph.bytes==before_graph&&header.bytes==before_header);
    }
    std::cout<<"PASS D8 graph/header memory "<<tests<<" input/tail/guard/ownership scenarios and 1950 header receives; hardware not accessed\n";
}
