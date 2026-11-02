#include "runtime.hpp"
#include "../axi_profile_r312/host_snapshot_r354.hpp"
#define SMOOTH_NATIVE
#include "../manual_bram_apply_r2585/mesh_smooth.hpp"
#include <array>
#include <cmath>

static_assert(sizeof(SmoothPoint)==16&&sizeof(SmoothEdge)==8&&sizeof(SmoothFace)==16,"Original smoothing ABI sizes required");
using namespace smoothspeed;
namespace {
constexpr size_t GUARD=4096;
thread_local std::string error;
struct Context {
    Session session;
    bool profile_enabled=false,profile_valid=false;
    std::array<std::uint64_t,16> profile_counts{};
    std::vector<xrt::bo> buffers;
    std::vector<size_t> capacity;
    std::array<double,12> phases{};
    std::array<unsigned char,GUARD> guard_expected;
    std::array<unsigned char,2*GUARD> guard_snapshot;
    explicit Context(bool measure=false,const char* project_root=nullptr):session(project_root),profile_enabled(measure){buffers.reserve(11);capacity.reserve(11);guard_expected.fill(0xa7);}
    void allocate(unsigned j,size_t bytes){
        if(j>=buffers.size()){buffers.push_back(session.buffer(bytes+2*GUARD));capacity.push_back(bytes);}
        else if(capacity[j]<bytes){buffers[j]=session.buffer(bytes+2*GUARD);capacity[j]=bytes;}
        require(buffers[j].address()+GUARD+bytes+GUARD<=0x80000000ULL,"DMA guard range");
    }
    void* data(unsigned j){return static_cast<char*>(buffers[j].map<void*>())+GUARD;}
    void guards(unsigned j,size_t bytes){
        auto p=buffers[j].map<unsigned char*>();std::memset(p,0xa7,GUARD);std::memset(p+GUARD+bytes,0xa7,GUARD);
    }
    void check_guard(unsigned j,size_t bytes){
        buffers[j].sync(XCL_BO_SYNC_BO_FROM_DEVICE,GUARD,0);
        buffers[j].sync(XCL_BO_SYNC_BO_FROM_DEVICE,GUARD,GUARD+bytes);
        auto p=buffers[j].map<const unsigned char*>();
        std::memcpy(guard_snapshot.data(),p,GUARD);std::memcpy(guard_snapshot.data()+GUARD,p+GUARD+bytes,GUARD);
        require(!std::memcmp(guard_snapshot.data(),guard_expected.data(),GUARD) && !std::memcmp(guard_snapshot.data()+GUARD,guard_expected.data(),GUARD),"Smoothing DMA red zone changed");
    }
};
}

extern "C" const char* speed_error(){return error.c_str();}
extern "C" void* speed_open(){try{return new Context();}catch(const std::exception& e){error=e.what();return nullptr;}}
extern "C" void* speed_open_profile(){try{return new Context(true);}catch(const std::exception& e){error=e.what();return nullptr;}}
extern "C" void* speed_open_root(const char* project_root,bool measure){
    try{require(project_root&&*project_root,"Explicit medical project root required");return new Context(measure,project_root);}
    catch(const std::exception& e){error=e.what();return nullptr;}
}
extern "C" int speed_profile_snapshot(void* handle,std::uint64_t* counts){
    try{
        require(handle&&counts,"Null profile snapshot argument");auto& h=*static_cast<Context*>(handle);
        std::lock_guard<std::recursive_mutex> lock(h.session.operation_mutex);
        require(h.profile_enabled&&h.profile_valid,"No complete diagnostic snapshot available");
        std::copy(h.profile_counts.begin(),h.profile_counts.end(),counts);return 0;
    }catch(const std::exception& e){error=e.what();return -1;}
}
extern "C" void speed_close(void* handle){delete static_cast<Context*>(handle);}
extern "C" int speed_restore(void* handle){
    try{auto& s=static_cast<Context*>(handle)->session;s.select("smooth");s.echo();s.select("scope");return 0;}
    catch(const std::exception& e){error=e.what();return -1;}
}
extern "C" int speed_run(void* handle,const SmoothPoint* original,const uint32_t* rows,
    const SmoothEdge* edges,const uint32_t* frozen,const SmoothFace* faces,SmoothPoint* output,uint32_t* report,
    uint32_t nv,uint32_t nf,uint32_t nnz,float limit,uint32_t iterations,double* phases){
    try{
        require(handle&&original&&rows&&edges&&frozen&&faces&&output&&report&&phases,"Null smoothing argument");
        auto& h=*static_cast<Context*>(handle);auto& s=h.session;std::lock_guard<std::recursive_mutex> lock(s.operation_mutex);
        auto total=Clock::now(),t=total;h.phases.fill(0);h.profile_valid=false;
        require(nv>0&&nv<=1000000&&nf<=2000000&&nnz<=12000000&&iterations>=1&&iterations<=16&&std::isfinite(limit)&&limit>0,"Invalid configuration");
        require(rows[0]==0&&rows[nv]==nnz,"CSR endpoint");
        for(unsigned i=0;i<nv;++i)if(!(rows[i]<=rows[i+1]&&rows[i+1]<=nnz&&frozen[i]<=1&&std::isfinite(original[i].x)&&std::isfinite(original[i].y)&&std::isfinite(original[i].z)))throw std::runtime_error("CSR/point/frozen invalid");
        for(unsigned i=0;i<nnz;++i)if(!(edges[i].index<nv&&std::isfinite(edges[i].weight)&&edges[i].weight>0))throw std::runtime_error("Invalid neighbor");
        for(unsigned i=0;i<nf;++i)if(!(faces[i].a<nv&&faces[i].b<nv&&faces[i].c<nv))throw std::runtime_error("Invalid face");
        h.phases[0]=seconds(t);t=Clock::now();
        std::array<size_t,11> sizes={size_t(nv)*16,size_t(nv+1)*4,size_t(nnz)*8,size_t(nv)*4,size_t(nf)*16,
                                   size_t(nv)*16,size_t(nv)*16,size_t(nv)*16,size_t(nv)*16,size_t(nv)*16,64};
        for(unsigned j=0;j<11;++j)h.allocate(j,sizes[j]);
        h.phases[1]=seconds(t);t=Clock::now();
        const void* inputs[]={original,rows,edges,frozen,faces};
        for(unsigned j=0;j<11;++j){h.guards(j,sizes[j]);if(j<5 && sizes[j])std::memcpy(h.data(j),inputs[j],sizes[j]);}
        h.phases[2]=seconds(t);t=Clock::now();
        for(unsigned j=0;j<11;++j)h.buffers[j].sync(XCL_BO_SYNC_BO_TO_DEVICE,sizes[j]+2*GUARD,0);
        h.phases[3]=seconds(t);s.select("smooth");h.phases[4]=s.load_seconds;h.phases[5]=s.switch_seconds;
        for(unsigned j=0;j<11;++j){auto address=h.buffers[j].address()+GUARD;require(address%64==0,"Unaligned smoothing BO");s.arg(0x10+j*16,uint32_t(address));s.arg(0x14+j*16,uint32_t(address>>32));}
        uint32_t bits;std::memcpy(&bits,&limit,4);s.arg(0xc0,nv);s.arg(0xc8,nf);s.arg(0xd0,nnz);s.arg(0xd8,bits);s.arg(0xe0,iterations);
        // Diagnostics are opt-in; the default API never touches Fxxx.
        medical_profile::OptionalProfile<Mmio> profile(*s.ip,h.profile_enabled);
        if(h.profile_enabled)profile.start((s.ip->read_register(0)&4)!=0);
        h.phases[6]=s.execute(180);
        if(h.profile_enabled){h.profile_counts=profile.stop().counts;h.profile_valid=true;}
        t=Clock::now();
        h.buffers[10].sync(XCL_BO_SYNC_BO_FROM_DEVICE,64,GUARD);std::memcpy(report,h.data(10),64);require(report[0]==0,"PL smoothing error");
        h.buffers[5].sync(XCL_BO_SYNC_BO_FROM_DEVICE,sizes[5],GUARD);
        for(unsigned j=0;j<11;++j)h.check_guard(j,sizes[j]);
        h.phases[7]=seconds(t);t=Clock::now();std::memcpy(output,h.data(5),sizes[5]);h.phases[8]=seconds(t);
        h.phases[9]=seconds(total);std::copy(h.phases.begin(),h.phases.end(),phases);return 0;
    }catch(const std::exception& e){error=e.what();return -1;}
}
