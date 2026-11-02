#include "session.hpp"
#include "pipeline.hpp"
#include "dma_completion.hpp"
#include <array>

namespace {
using namespace hu_dfx;
constexpr size_t GUARD=4096,CONFIG=1440;
constexpr uint32_t MAX_REQUEST=1u<<23;
thread_local std::string last_error;

void dma_argument(xrt::ip& ip,unsigned offset,uint32_t value){
    ip.write_register(offset,value);require(ip.read_register(offset)==value,"HU DMA argument readback failed");
}
void guards(const unsigned char* p,size_t bytes){
    for(size_t i=0;i<GUARD;++i)require(p[i]==0xa5&&p[GUARD+bytes+i]==0xa5,"HU DMA buffer guard damaged");
}
struct Slot {
    std::unique_ptr<xrt::bo> input,output,config;
    size_t input_capacity=0,output_capacity=0;
    void allocate(Session& session,size_t in,size_t out){
        if(input_capacity<in){input=std::make_unique<xrt::bo>(session.buffer(in+2*GUARD,xrt::bo::flags::cacheable));input_capacity=in;}
        if(output_capacity<out){output=std::make_unique<xrt::bo>(session.buffer(out+2*GUARD,xrt::bo::flags::cacheable));output_capacity=out;}
        if(!config)config=std::make_unique<xrt::bo>(session.buffer(CONFIG+2*GUARD,xrt::bo::flags::cacheable));
    }
};
struct Job {
    Slot& slot;
    const uint32_t n;
    const size_t in_bytes,out_bytes;
    std::array<uint8_t,1401> table{};
    unsigned char *input,*output,*config;
    int8_t* destination;uint32_t* status;double* phases;
    std::array<double,12> time{};
    Clock::time_point begin,prepared,launched;
    std::unique_ptr<SignalGuard> signal;
    uint32_t transactions=0;
    Job(Slot& s,uint32_t count,int8_t* dst,uint32_t* report,double* metrics,Clock::time_point start)
        :slot(s),n(count),in_bytes(std::max(size_t(64),(size_t(count)*2+63)/64*64)),
         out_bytes(std::max(size_t(64),(size_t(count)+63)/64*64)),destination(dst),status(report),phases(metrics),begin(start){}
};
struct Operations {
    Session& session;
    explicit Operations(Session& s):session(s){}
    void prepare_device(Job& j){
        auto t=Clock::now();session.select("hu");j.time[3]=seconds(t);
        j.time[9]=session.load_seconds;j.time[10]=session.switch_seconds;t=Clock::now();
        require(!(session.gpio->read_register(8)&1)&&(session.ip->read_register(0)&4),"HU core is not idle");
        for(auto pair:{std::make_pair(session.reader.get(),j.slot.input->address()+GUARD),
                       std::make_pair(session.writer.get(),j.slot.output->address()+GUARD)}){
            require(pair.second%64==0&&(pair.first->read_register(0)&4),"HU DMA not idle/aligned");
            dma_argument(*pair.first,0x10,uint32_t(pair.second));dma_argument(*pair.first,0x14,uint32_t(pair.second>>32));
        }
        dma_argument(*session.reader,0x20,(j.n+31)/32);dma_argument(*session.writer,0x20,(j.n+63)/64);
        const uint64_t a=j.slot.config->address()+GUARD;
        require(a%64==0&&a+CONFIG<=0x80000000ULL,"HU config outside mapped low DDR");
        session.arg(0x10,uint32_t(a));session.arg(0x14,uint32_t(a>>32));session.arg(0x1c,j.n);
        j.transactions=session.gpio->read_register(8)>>16;j.time[4]=seconds(t);
        j.signal=std::make_unique<SignalGuard>();
    }
    void launch(Job& j)noexcept{
        j.launched=Clock::now();j.time[11]=seconds(j.prepared);
        try{
            if(j.n)session.writer->write_register(0,1);
            session.ip->write_register(0,1);
            if(j.n)session.reader->write_register(0,1);
        }catch(const std::exception& e){retain(e.what());}catch(...){retain("HU launch exception");}
    }
    void wait(Job& j)noexcept{
        try{
            bool rd=j.n==0,wd=j.n==0,core=false;
            while(!seed_stream::dma_complete(rd,wd,core)){
                if(!rd)rd=session.reader->read_register(0)&2;
                if(!wd)wd=session.writer->read_register(0)&2;
                if(!core)core=session.ip->read_register(0)&2;
                if(seed_stream::dma_timeout(rd,wd,core,seconds(j.launched)))retain("HU DMA completion timeout");
                if(!seed_stream::dma_complete(rd,wd,core))std::this_thread::sleep_for(std::chrono::microseconds(20));
            }
        }catch(const std::exception& e){retain(e.what());}catch(...){retain("HU wait exception");}
        j.time[5]=seconds(j.launched);j.signal.reset();
    }
    void post_drain(Job& j){
        if(j.n)require(session.writer->read_register(0x28)==0,"HU AXIS framing error");
        session.wait_status(0xffff0000,((j.transactions+unsigned(j.n!=0))&65535)<<16);
        auto t=Clock::now();
        j.slot.output->sync(XCL_BO_SYNC_BO_FROM_DEVICE,j.out_bytes+2*GUARD,0);
        j.slot.config->sync(XCL_BO_SYNC_BO_FROM_DEVICE,CONFIG+2*GUARD,0);
        j.time[6]=seconds(t);
    }
    void validate(Job& j){
        auto t=Clock::now();guards(j.input,j.in_bytes);guards(j.output,j.out_bytes);guards(j.config,CONFIG);
        require(std::memcmp(j.config+GUARD,j.table.data(),1401)==0,"HU model LUT modified");
        for(size_t i=1401;i<1408;++i)require(j.config[GUARD+i]==0xcd,"HU LUT padding modified");
        std::array<uint32_t,8> report{};std::memcpy(report.data(),j.config+GUARD+1408,32);
        const std::array<uint32_t,8> expected{0x31554851,1,0,j.n,(j.n+31)/32,(j.n+63)/64,j.n,0};
        require(report==expected,"HU hardware status mismatch");
        if(j.n)for(size_t i=j.n;i<j.out_bytes;++i)require(j.output[GUARD+i]==0,"HU logical tail is not zero");
        if(j.n)std::memcpy(j.destination,j.output+GUARD,j.n);
        std::memcpy(j.status,report.data(),32);j.time[7]=seconds(t);j.time[8]=seconds(j.begin);
        std::memcpy(j.phases,j.time.data(),sizeof(j.time));
    }
    [[noreturn]]void retain_active()noexcept{retain("HU context destroyed during DMA");}
};
struct Handle {
    Session session;
    std::array<Slot,2> slots;
    Operations operations;
    hu_host::Pipeline<Job,Operations> pipeline;
    explicit Handle(const char* root):session(root),operations(session),pipeline(operations){}
};
}

extern "C" const char* hu_error(){return last_error.c_str();}
extern "C" void* hu_open_root(const char* root){
    try{(void)Session::medical_directory(root);return new Handle(root);}
    catch(const std::exception& e){last_error=e.what();return nullptr;}
}
extern "C" uint64_t hu_submit(void* handle,const int16_t* input,uint32_t n,const int8_t* table,
    int8_t* output,uint32_t* report,double* phases){
    try{
        auto start=Clock::now();require(n<=MAX_REQUEST&&table&&report&&phases&&(!n||(input&&output)),"Invalid HU request before hardware access");
        require(handle,"Null HU context before hardware access");auto& h=*static_cast<Handle*>(handle);
        seed_overlap::Memory memory{{reinterpret_cast<uintptr_t>(input),size_t(n)*2},{{
            {reinterpret_cast<uintptr_t>(output),n},{reinterpret_cast<uintptr_t>(report),32},
            {reinterpret_cast<uintptr_t>(phases),12*sizeof(double)}}},{reinterpret_cast<uintptr_t>(table),1401}};
        return h.pipeline.submit(memory,[&](unsigned index){
            auto j=std::make_shared<Job>(h.slots[index],n,output,report,phases,start);j->time[0]=seconds(start);
            auto t=Clock::now();j->slot.allocate(h.session,j->in_bytes,j->out_bytes);
            j->input=j->slot.input->map<unsigned char*>();j->output=j->slot.output->map<unsigned char*>();j->config=j->slot.config->map<unsigned char*>();
            for(auto p:{std::make_pair(j->input,j->in_bytes),std::make_pair(j->output,j->out_bytes),std::make_pair(j->config,CONFIG)}){
                std::memset(p.first,0xa5,GUARD);std::memset(p.first+GUARD+p.second,0xa5,GUARD);
            }
            // Input is copied exactly once; only the sub-word input tail needs
            // a defined pad. DMA overwrites every byte of every output word.
            // Canary guards and the small model/status area stay initialized.
            if(n)std::memcpy(j->input+GUARD,input,size_t(n)*2);
            std::memset(j->input+GUARD+size_t(n)*2,0xcd,j->in_bytes-size_t(n)*2);
            std::memset(j->config+GUARD,0xcd,CONFIG);
            std::memcpy(j->table.data(),table,1401);std::memcpy(j->config+GUARD,table,1401);
            j->time[1]=seconds(t);t=Clock::now();
            j->slot.input->sync(XCL_BO_SYNC_BO_TO_DEVICE,j->in_bytes+2*GUARD,0);
            // No CPU output-payload writes: clean only its two canaries.
            // Guard offsets/lengths are cache-line aligned, including tails.
            j->slot.output->sync(XCL_BO_SYNC_BO_TO_DEVICE,GUARD,0);
            j->slot.output->sync(XCL_BO_SYNC_BO_TO_DEVICE,GUARD,GUARD+j->out_bytes);
            j->slot.config->sync(XCL_BO_SYNC_BO_TO_DEVICE,CONFIG+2*GUARD,0);
            j->time[2]=seconds(t);j->prepared=Clock::now();return j;
        });
    }catch(const std::exception& e){last_error=e.what();return 0;}
}
extern "C" int hu_collect(void* handle,uint64_t ticket){
    try{require(handle,"Null HU context");static_cast<Handle*>(handle)->pipeline.collect(ticket);return 0;}
    catch(const std::exception& e){last_error=e.what();return 1;}
}
extern "C" int hu_close(void** pointer){
    try{
        require(pointer&&*pointer,"Null HU context");auto* h=static_cast<Handle*>(*pointer);
        (void)h->pipeline.pending();std::string error;
        try{h->pipeline.drain();}catch(const std::exception& e){error=e.what();}
        require(h->pipeline.pending()==0,"HU pending commands retained");
        // Leave the RP isolated. Older hosts then skip unknown-core MMIO and
        // load their next RM directly, without an intermediate C9 bit switch.
        h->session.quiesce();delete h;*pointer=nullptr;
        if(!error.empty()){last_error=error;return 1;}return 0;
    }catch(const std::exception& e){last_error=e.what();return 1;}
}
