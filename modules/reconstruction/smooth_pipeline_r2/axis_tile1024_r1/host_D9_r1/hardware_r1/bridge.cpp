#include "session.hpp"
#include "../register_port.hpp"
#include "../xrt_memory.hpp"
#define SMOOTH_NATIVE // Plain ABI types only; no algorithm source is included.
#include "../../mesh_smooth.hpp"
#include <array>
#include <cmath>

// The only algorithm invocation is the PL control/AXIS driver. No native
// smoothing implementation is compiled into this library.
static_assert(sizeof(SmoothPoint)==16&&sizeof(SmoothEdge)==8&&sizeof(SmoothFace)==16,"D9 original ABI");
using namespace smooth_d9_hw;
namespace {
constexpr size_t GUARD=4096;
thread_local std::string error;
struct Context {
    Session session;
    std::thread::id owner=std::this_thread::get_id();
    std::array<std::unique_ptr<xrt::bo>,12> buffers{};
    std::array<size_t,12> capacities{};
    std::array<double,12> phases{};
    std::array<uint64_t,8> counters{};
    explicit Context(const char* root):session(root){}
    void owned(){require(owner==std::this_thread::get_id(),"D9 owner thread mismatch");}
    void allocate(unsigned j,size_t bytes){
        const size_t needed=bytes+2*GUARD;
        if(!buffers[j]||capacities[j]<needed){
            buffers[j].reset();capacities[j]=0;
            buffers[j]=std::make_unique<xrt::bo>(session.buffer(needed,xrt::bo::flags::cacheable));
            capacities[j]=buffers[j]->size();++counters[4];
        }else ++counters[5];
        require(buffers[j]->address()+needed<=0x80000000ULL,"D9 guarded BO beyond mapped DDR");
    }
    unsigned char* data(unsigned j){return buffers[j]->map<unsigned char*>()+GUARD;}
    void guards(unsigned j,size_t bytes){
        auto* p=buffers[j]->map<unsigned char*>();
        std::memset(p,0xa7,GUARD);std::memset(p+GUARD+bytes,0xa7,GUARD);
    }
    void check_guard(unsigned j,size_t bytes){
        buffers[j]->sync(XCL_BO_SYNC_BO_FROM_DEVICE,GUARD,0);
        buffers[j]->sync(XCL_BO_SYNC_BO_FROM_DEVICE,GUARD,GUARD+bytes);
        std::array<unsigned char,2*GUARD> snapshot{};
        const auto* p=buffers[j]->map<const unsigned char*>();
        std::memcpy(snapshot.data(),p,GUARD);std::memcpy(snapshot.data()+GUARD,p+GUARD+bytes,GUARD);
        require(std::all_of(snapshot.begin(),snapshot.end(),[](unsigned char v){return v==0xa7;}),"D9 logical DMA red zone damaged");
    }
};
Context& context(void* value){require(value,"D9 null context");auto& h=*static_cast<Context*>(value);h.owned();return h;}
}

extern "C" const char* D9_error(){return error.c_str();}
extern "C" void* D9_open_root(const char* root){
    try{return new Context(root);}catch(const std::exception& e){error=e.what();return nullptr;}
}
extern "C" int D9_restore(void* handle){
    try{auto& h=context(handle);h.session.select("smooth");return 0;}
    catch(const std::exception& e){error=e.what();return -1;}
}
extern "C" int D9_close(void* handle){
    try{auto& h=context(handle);h.session.quiesce();delete &h;return 0;}
    catch(const std::exception& e){error=e.what();return -1;}
}
extern "C" int D9_run(void* handle,const SmoothPoint* original,const uint32_t* rows,
    const SmoothEdge* edges,const uint32_t* frozen,const SmoothFace* faces,
    SmoothPoint* current,SmoothPoint* half,SmoothPoint* candidate,SmoothPoint* lap,SmoothPoint* next_lap,
    uint32_t* report,uint32_t nv,uint32_t nf,uint32_t nnz,float limit,uint32_t iterations,
    bool all_work_banks,double* phases,uint64_t* counters){
    try{
        auto& h=context(handle);auto& s=h.session;
        std::lock_guard<std::recursive_mutex> operation(s.operation_mutex);
        const auto total=Clock::now();auto t=total;h.phases.fill(0);h.counters.fill(0);
        require(original&&rows&&frozen&&current&&report&&phases&&counters,"D9 null required input/output");
        require((edges||!nnz)&&(faces||!nf),"D9 null nonempty input");
        require(nv>=1&&nv<=1000000&&nf<=2000000&&nnz<=12000000&&iterations>=1&&iterations<=16&&
            std::isfinite(limit)&&limit>0,"D9 invalid configuration before allocation or switching");
        require(!all_work_banks||(half&&candidate&&lap&&next_lap),"D9 complete validation needs all five bank buffers");
        require(rows[0]==0&&rows[nv]==nnz,"D9 CSR endpoints");
        for(unsigned i=0;i<nv;++i)require(rows[i]<=rows[i+1]&&rows[i+1]<=nnz&&frozen[i]<=1&&
            std::isfinite(original[i].x)&&std::isfinite(original[i].y)&&std::isfinite(original[i].z),"D9 invalid CSR/point/frozen");
        for(unsigned i=0;i<nnz;++i)require(edges[i].index<nv&&std::isfinite(edges[i].weight)&&edges[i].weight>0,"D9 invalid graph edge");
        for(unsigned i=0;i<nf;++i)require(faces[i].a<nv&&faces[i].b<nv&&faces[i].c<nv,"D9 invalid face");
        h.phases[0]=seconds(t);t=Clock::now();
        const size_t graph_bytes=size_t((nnz+7)/8)*64;
        const std::array<size_t,12> sizes={size_t(nv)*16,size_t(nv+1)*4,graph_bytes,size_t(nv)*4,size_t(nf)*16,
            size_t(nv)*16,size_t(nv)*16,size_t(nv)*16,size_t(nv)*16,size_t(nv)*16,64,64};
        for(unsigned j=0;j<12;++j)h.allocate(j,sizes[j]);
        h.phases[1]=seconds(t);t=Clock::now();
        const void* inputs[]={original,rows,edges,frozen,faces};
        void* work[]={current,half,candidate,lap,next_lap};
        for(unsigned j=0;j<12;++j){
            if(j==2||j==11)continue; // Graph/HeaderMemory owns their one upload and guards.
            h.guards(j,sizes[j]);
            if(j<5&&sizes[j])std::memcpy(h.data(j),inputs[j],sizes[j]);
            if(j>=5&&j<10&&work[j-5])std::memcpy(h.data(j),work[j-5],sizes[j]);
        }
        std::memcpy(h.data(10),report,64);
        h.phases[2]=seconds(t);t=Clock::now();
        for(unsigned j=0;j<11;++j){
            if(j==2)continue;
            if(j<5||j==10||all_work_banks||j==5)h.buffers[j]->sync(XCL_BO_SYNC_BO_TO_DEVICE,sizes[j]+2*GUARD,0);
            else{
                h.buffers[j]->sync(XCL_BO_SYNC_BO_TO_DEVICE,GUARD,0);
                h.buffers[j]->sync(XCL_BO_SYNC_BO_TO_DEVICE,GUARD,GUARD+sizes[j]);
            }
        }
        h.phases[3]=seconds(t);t=Clock::now();
        const smooth_d9::Config config{nv,nnz,iterations,h.buffers[2]->address()+GUARD};
        smooth_d9::XrtGraphHeaderMemory memory(*h.buffers[2],*h.buffers[11],{},
            [](const char* message){retain(message);});
        memory.prepare(config,edges,size_t(nnz)*8);
        h.phases[10]=seconds(t);
        s.select("axis_smooth");h.phases[4]=s.load_seconds;h.phases[5]=s.switch_seconds;
        t=Clock::now();
        for(unsigned j=0;j<11;++j){
            const auto address=h.buffers[j]->address()+GUARD;
            s.arg(0x10+j*16,uint32_t(address));s.arg(0x14+j*16,uint32_t(address>>32));
        }
        uint32_t bits;std::memcpy(&bits,&limit,4);
        s.arg(0xc0,nv);s.arg(0xc8,nf);s.arg(0xd0,nnz);s.arg(0xd8,bits);s.arg(0xe0,iterations);
        h.phases[11]=seconds(t);
        smooth_d9::RegisterPort<Session,smooth_d9::XrtGraphHeaderMemory> port(s,memory);
        smooth_d9::Result result;
        {
            SignalGuard active_dma;t=Clock::now();
            result=smooth_d9::execute(port,config,180);
            h.phases[6]=seconds(t);
        }
        // execute returns only after core, reader and writer have all drained.
        t=Clock::now();
        for(unsigned j=0;j<11;++j)if(j!=2)h.check_guard(j,sizes[j]);
        h.buffers[10]->sync(XCL_BO_SYNC_BO_FROM_DEVICE,64,GUARD);
        std::array<uint32_t,16> status{};std::memcpy(status.data(),h.data(10),64);
        require(!result.stream_errors&&status[0]==0,"D9 completed with stream/algorithm error");
        for(unsigned j=5;j<10;++j)if(j==5||all_work_banks)
            h.buffers[j]->sync(XCL_BO_SYNC_BO_FROM_DEVICE,sizes[j],GUARD);
        h.phases[7]=seconds(t);t=Clock::now();
        for(unsigned j=5;j<10;++j)if(j==5||all_work_banks)std::memcpy(work[j-5],h.data(j),sizes[j]);
        std::memcpy(report,status.data(),64);h.phases[8]=seconds(t);
        h.counters[0]=result.requests;h.counters[1]=result.graph_beats;
        h.counters[2]=uint64_t(result.graph_beats)*64;h.counters[3]=result.stream_errors;
        for(size_t bytes:h.capacities)h.counters[6]+=bytes;
        h.counters[7]=s.switches;
        h.phases[9]=seconds(total);
        std::copy(h.phases.begin(),h.phases.end(),phases);std::copy(h.counters.begin(),h.counters.end(),counters);
        return 0;
    }catch(const std::exception& e){error=e.what();return -1;}
}
