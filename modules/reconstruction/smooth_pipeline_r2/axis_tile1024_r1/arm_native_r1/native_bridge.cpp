// Test-only transport model. Arithmetic is the unchanged complete native D8
// algorithm, running on another thread; it cannot advance without the real
// host driver's REQUEST service. No hardware or XRT is accessed here.
#define SMOOTH_NATIVE
#define mesh_smooth mesh_smooth_legacy_adapter
#include "../mesh_smooth.cpp"
#undef mesh_smooth
#include "driver.hpp"
#include <condition_variable>
#include <mutex>
#include <thread>
#include <functional>
#include <exception>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <pthread.h>

namespace {
using namespace smooth_d8;
thread_local uint64_t measurements[8]{};
class NativePort {
    const EdgeWord* graph;
    Config config;
    std::mutex mutex;
    std::condition_variable changed;
    pthread_t worker{};
    bool worker_joinable=false;
    std::exception_ptr failure;
    bool stop=false,armed=false,header_ready=false,reader_active=false,core_finished=false;
    bool writer_pulse=false,reader_pulse=false,core_pulse=false;
    uint32_t cursor=0;
    std::array<uint32_t,16> header{};
public:
    std::function<void()> algorithm;
    uint32_t starts=0,arms=0,sends=0,received_beats=0,polls=0;
    NativePort(const EdgeWord* source,Config cfg):graph(source),config(cfg){}
    ~NativePort(){cancel();}
    void cancel(){
        {std::lock_guard<std::mutex> lock(mutex);stop=true;changed.notify_all();}
        if(worker_joinable){pthread_join(worker,nullptr);worker_joinable=false;}
    }
    void preflight(Config cfg){
        cfg.validate();require(cfg.graph_address==config.graph_address,"Test graph owner mismatch");
    }
    void arm_header(){
        std::lock_guard<std::mutex> lock(mutex);
        require(!armed&&!header_ready,"Host rearmed an undrained header receiver");
        armed=true;++arms;changed.notify_all();
    }
    void start_core(){
        require(starts++==0,"Host restarted the smoothing core");
        pthread_attr_t attributes;
        require(pthread_attr_init(&attributes)==0,"Native worker attributes");
        const int stack=pthread_attr_setstacksize(&attributes,64*1024*1024);
        const int created=stack?stack:pthread_create(&worker,&attributes,[](void* value)->void*{
            auto& self=*static_cast<NativePort*>(value);
            try{self.algorithm();}
            catch(...){std::lock_guard<std::mutex> lock(self.mutex);self.failure=std::current_exception();}
            std::lock_guard<std::mutex> lock(self.mutex);
            self.core_finished=true;self.core_pulse=true;self.changed.notify_all();return nullptr;
        },this);
        pthread_attr_destroy(&attributes);require(created==0,"Native worker creation/64MiB stack");
        worker_joinable=true;
    }
    void send_graph(uint64_t address,uint32_t beats){
        std::lock_guard<std::mutex> lock(mutex);
        require(address==config.graph_address&&beats==config.beats(),"Host altered DMA graph range");
        require(armed&&!reader_active,"Graph started before next receiver armed or prior reader drained");
        cursor=0;reader_active=true;++sends;changed.notify_all();
    }
    smooth_graph_axis::Word input(){
        std::unique_lock<std::mutex> lock(mutex);
        changed.wait(lock,[this]{return stop||reader_active;});
        require(!stop,"Test cancelled");
        smooth_graph_axis::Word word{};
        for(unsigned lane=0;lane<8;++lane)if(cursor*8+lane<config.edges)
            std::memcpy(word.data+lane,graph+cursor*8+lane,8);
        word.keep=word.strb=~uint64_t(0);word.user=cursor==0;word.last=cursor+1==config.beats();
        ++cursor;++received_beats;
        if(cursor==config.beats()){reader_active=false;reader_pulse=true;}
        return word;
    }
    void output(const smooth_graph_axis::Word& word){
        std::unique_lock<std::mutex> lock(mutex);
        changed.wait(lock,[this]{return stop||armed;});require(!stop,"Test cancelled");
        require(word.keep==~uint64_t(0)&&word.strb==~uint64_t(0)&&word.user==1&&word.last==1,
                "Actual algorithm emitted invalid header framing");
        std::memcpy(header.data(),word.data,64);
        armed=false;header_ready=true;writer_pulse=true;changed.notify_all();
    }
    Poll poll(){
        std::lock_guard<std::mutex> lock(mutex);++polls;
        if(failure)std::rethrow_exception(failure);
        Poll status{reader_pulse,!reader_active,writer_pulse,!armed,core_pulse,core_finished};
        reader_pulse=writer_pulse=core_pulse=false;return status;
    }
    std::array<uint32_t,16> read_header(){
        std::lock_guard<std::mutex> lock(mutex);
        require(header_ready&&!reader_active,"Host read incomplete or overlapping header");
        header_ready=false;return header;
    }
    void finish(uint32_t headers){
        require(headers==arms&&headers==sends+1&&received_beats==sends*config.beats(),"Incomplete graph drain");
        if(worker_joinable){pthread_join(worker,nullptr);worker_joinable=false;}
    }
    void idle(){std::this_thread::yield();}
    [[noreturn]] void retain_active(const char* text){cancel();throw std::runtime_error(text);}
};
smooth_graph_axis::Word read_native(void* port){return static_cast<NativePort*>(port)->input();}
void write_native(void* port,const smooth_graph_axis::Word& word){static_cast<NativePort*>(port)->output(word);}
}
extern "C" SM_EXPORT uint64_t D8_host_stat(uint32_t field){return field<8?measurements[field]:0;}
extern "C" SM_EXPORT void mesh_smooth_D8_host(const PointWord* original,const uint32_t* rows,
    const EdgeWord* graph,const uint32_t* frozen,const FaceWord* faces,PointMemory current,
    PointMemory half,PointMemory candidate,PointMemory lap,PointMemory next,uint32_t* report,
    uint32_t nv,uint32_t nf,uint32_t nnz,float limit,uint32_t iterations){
    // Original test includes invalid nv=0. Preserve its original report and
    // all-bank oracle; only valid jobs may enter a host DMA transaction.
    if(!nv||nv>1000000||nnz>12000000||!iterations||iterations>16||nf>2000000||!(limit>0)||!std::isfinite(limit)){
        mesh_smooth_legacy_adapter(original,rows,graph,frozen,faces,current,half,candidate,lap,next,report,nv,nf,nnz,limit,iterations);
        std::memset(measurements,0,sizeof(measurements));return;
    }
    try{
        Config config{nv,nnz,iterations,0x12340000};NativePort port(graph,config);
        GraphInput input{&port,read_native};GraphOutput output{&port,write_native};
        port.algorithm=[&]{mesh_smooth_axis(input,output,original,rows,config.graph_address,frozen,
            faces,current,half,candidate,lap,next,report,nv,nf,nnz,limit,iterations);};
        const auto result=execute(port,config);
        require(result.stream_errors==0,"Actual algorithm reported a graph stream error");
        measurements[0]=result.requests;measurements[1]=result.graph_beats;measurements[2]=port.starts;
        measurements[3]=port.arms;measurements[4]=port.sends;measurements[5]=port.polls;
        measurements[6]=port.received_beats;measurements[7]=1;
    }catch(const std::exception& error){
        std::fprintf(stderr,"Actual D8 host/native algorithm failure: %s\n",error.what());std::abort();
    }
}
extern "C" SM_EXPORT void mesh_smooth(const PointWord* original,const uint32_t* rows,
    const EdgeWord* graph,const uint32_t* frozen,const FaceWord* faces,PointMemory current,
    PointMemory half,PointMemory candidate,PointMemory lap,PointMemory next,uint32_t* report,
    uint32_t nv,uint32_t nf,uint32_t nnz,float limit,uint32_t iterations){
    mesh_smooth_D8_host(original,rows,graph,frozen,faces,current,half,candidate,lap,next,report,nv,nf,nnz,limit,iterations);
}
