#include "register_port.hpp"
#include <map>
#include <memory>
#include <vector>
#include <iostream>
#include <functional>

using namespace smooth_d8;
struct Retained:std::runtime_error {using std::runtime_error::runtime_error;};
struct Model {
    Config config;
    std::vector<std::array<uint32_t,16>> frames;
    uint32_t tick=0,header_tick=0,reader_tick=0;
    unsigned armed=0,started=0,sent=0,read=0,retained=0;
    bool header_live=false,reader_live=false,fail_guards=false,finish_called=false;
    unsigned readback_fault=~0u;
    Poll last{};
    Model(uint32_t requests,Config value,uint32_t errors=0):config(value) {
        for(uint32_t i=0;i<=requests;++i){
            std::array<uint32_t,16> h{};
            h[0]=0x31474d53;h[1]=1;h[2]=i<requests?1:2;h[3]=i;
            h[4]=config.vertices;h[5]=config.edges;h[6]=config.beats();
            h[7]=errors;h[8]=uint32_t(config.graph_address);h[9]=uint32_t(config.graph_address>>32);
            h[10]=i*config.beats();frames.push_back(h);
        }
    }
    void arm(){require(!header_live,"Rearm active writer");header_live=true;header_tick=tick+3;++armed;}
    void start(){require(started++==0&&armed==1,"Core start order/count incorrect");}
    void send(){require(header_live&&!reader_live,"Reader restart/receiver not armed");reader_live=true;reader_tick=tick;++sent;}
    Poll poll(){
        ++tick;
        const bool final_armed=armed==frames.size();
        // Done pulses precede idle by several polls. FINAL/core can complete
        // before the writer becomes idle. The host must latch each separately.
        last={reader_live&&tick==reader_tick+2,!reader_live||tick>=reader_tick+7,
              header_live&&tick==header_tick,header_live&&tick>=header_tick+5,
              final_armed&&tick==header_tick-1,final_armed&&tick>=header_tick+2};
        if(reader_live&&last.reader_idle)reader_live=false;
        return last;
    }
    std::array<uint32_t,16> take(){
        require(header_live&&tick>=header_tick+5&&!reader_live,"Read before complete DMA drain");
        require(read<frames.size(),"Read beyond scripted frames");header_live=false;return frames[read++];
    }
};
struct FakeIP {
    Model& model;unsigned type;
    std::map<unsigned,uint32_t> registers;
    uint32_t read_register(unsigned offset){
        if(offset==0){
            if(!model.started)return 4;
            if(type==0)model.poll();
            const auto s=model.last;
            return type==0?(unsigned(s.reader_done)*2+unsigned(s.reader_idle)*4):
                   type==1?(unsigned(s.writer_done)*2+unsigned(s.writer_idle)*4):
                           (unsigned(s.core_done)*2+unsigned(s.core_idle)*4);
        }
        return registers[offset]^(offset==model.readback_fault?1:0);
    }
    void write_register(unsigned offset,uint32_t value){
        if(offset){registers[offset]=value;return;}
        require(value==1,"Unexpected DMA/control operation");
        if(type==0)model.send();else if(type==1)model.arm();else model.start();
    }
};
struct FakeGPIO {
    uint32_t state=(65534u<<16)|0xd800;
    uint32_t read_register(unsigned offset){require(offset==8,"Unexpected GPIO access");return state;}
};
struct FakeSession {
    Model& model;
    std::unique_ptr<FakeIP> reader,writer,ip;
    std::unique_ptr<FakeGPIO> gpio;
    explicit FakeSession(Model& value):model(value),
        reader(new FakeIP{value,0,{}}),writer(new FakeIP{value,1,{}}),ip(new FakeIP{value,2,{}}),gpio(new FakeGPIO){
        auto& r=ip->registers;r[0xc0]=value.config.vertices;r[0xd0]=value.config.edges;
        r[0xe0]=value.config.iterations;r[0x30]=uint32_t(value.config.graph_address);r[0x34]=uint32_t(value.config.graph_address>>32);
    }
    void wait_status(uint32_t mask,uint32_t value){
        require(mask==0xffff0000,"Unexpected shutdown/isolation request");
        require(model.read==model.frames.size()&&model.sent+1==model.read,"Finish before all headers/graph DMAs drain");
        require(value==((65534+model.read)&65535)<<16,"Static transaction counter wrap/count mismatch");
        gpio->state=value|0xd800;model.finish_called=true;
    }
};
struct Memory {
    Model& model;
    void validate(Config config){config.validate();}
    uint64_t graph_address(){return model.config.graph_address;}
    uint64_t header_address(){return 0x20000000;}
    std::array<uint32_t,16> invalidate_and_copy_header(){return model.take();}
    void check_guards(){require(!model.fail_guards,"Injected guard failure AFTER complete drain");}
    [[noreturn]] void retain_active(const char* text){++model.retained;throw Retained(text);}
};
static unsigned tests=0;
static void check(bool value){if(!value)throw std::runtime_error("Test assertion failed");}
int main(){
    const Config normal{17,35,16,0x12340000};
    auto run=[&](Model& m,std::function<void(FakeSession&)> mutate={},bool rejects=false,bool retains=false){
        FakeSession session(m);Memory memory{m};if(mutate)mutate(session);
        RegisterPort<FakeSession,Memory> port(session,memory);
        bool rejected=false;
        try{
            const auto r=execute(port,m.config);
            check(r.requests==m.sent&&r.graph_beats==m.sent*m.config.beats());
            check(m.started==1&&m.armed==m.sent+1&&m.finish_called);
            check(r.stream_errors==m.frames.back()[7]);
        }catch(const std::runtime_error&){rejected=true;}
        check(rejected==rejects&&bool(m.retained)==retains);++tests;
    };
    for(uint32_t requests:{1u,3u,7u,31u,65u,129u}){Model m(requests,normal);run(m);}
    for(uint32_t edges:{0u,1u,7u,8u,9u,32767u,32768u,32769u,12000000u}){
        auto config=normal;config.edges=edges;Model m(edges?3:0,config);run(m);
    }
    // These jobs have valid framing/ownership but algorithm-detected payload
    // errors. Drain every request and FINAL, then return the error bits.
    for(uint32_t error:{2u,4u,8u,16u,32u,64u,128u,256u,511u}){Model m(3,normal,error);run(m);}
    for(unsigned field=0;field<16;++field){
        Model m(3,normal);m.frames[0][field]^=field==2?4:0x80000000u;
        run(m,{},true,true);check(m.sent==0);
    }
    for(unsigned frame:{1u,3u})for(unsigned field:{0u,3u,4u,5u,6u,8u,9u,10u,15u}){
        Model m(3,normal);m.frames[frame][field]^=0x80000000u;run(m,{},true,true);
    }
    {Model m(130,normal);run(m,{},true,true);check(m.sent==129);}
    {Model m(3,normal,64);m.frames[2][7]=0;run(m,{},true,true);}
    {Model m(0,normal);run(m,{},true,true);}
    for(unsigned identity:{0xc2u,0xd7u,0u}){Model m(3,normal);run(m,[&](FakeSession& s){s.gpio->state=(65534u<<16)|(identity<<8);},true,false);check(!m.started&&!m.armed);}
    {Model m(3,normal);run(m,[](FakeSession& s){s.gpio->state|=1;},true,false);}
    for(unsigned offset:{0xc0u,0xd0u,0xe0u,0x30u,0x34u}){
        Model m(3,normal);run(m,[&](FakeSession& s){s.ip->registers[offset]^=1;},true,false);
    }
    {Model m(3,normal);m.readback_fault=0x20;run(m,{},true,false);check(!m.started&&!m.armed);}
    {Model m(3,normal);m.fail_guards=true;run(m,{},true,false);check(m.finish_called);}
    for(unsigned field=0;field<5;++field){
        auto config=normal;
        if(field==0)config.vertices=0;if(field==1)config.edges=12000001;
        if(field==2)config.iterations=17;if(field==3)config.graph_address+=1;if(field==4)config.graph_address=0x7fffffc0;
        Model m(3,config);run(m,{},true,false);check(!m.started&&!m.armed);
    }
    std::cout<<"PASS D8 actual register driver "<<tests<<" control/ownership/drain/error scenarios; hardware not accessed\n";
}
