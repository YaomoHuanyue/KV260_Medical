#include "session.hpp"
#include "smooth_types.hpp"
#include <array>
#include <cmath>
#include <limits>
#include <sys/resource.h>

namespace {
using namespace mc_dfx;
constexpr size_t GUARD=4096,MAX_OUTPUT=512*1024*1024;
thread_local std::string last_error;

void range(const void* pointer,size_t bytes) {
    const auto p=reinterpret_cast<uintptr_t>(pointer);
    require(pointer&&bytes<=std::numeric_limits<uintptr_t>::max()-p,"Invalid output memory range before DMA");
}
bool overlaps(const void* a,size_t an,const void* b,size_t bn) {
    auto x=reinterpret_cast<uintptr_t>(a),y=reinterpret_cast<uintptr_t>(b);
    return x<y+bn&&y<x+an;
}
void guards(const unsigned char* p,size_t bytes) {
    for(size_t i=0;i<GUARD;++i)
        require(p[i]==0xa5&&p[GUARD+bytes+i]==0xa5,"MC DMA canary damaged");
}
void set_dma(xrt::ip& ip,unsigned offset,uint32_t value) {
    ip.write_register(offset,value);require(ip.read_register(offset)==value,"MC static DMA argument readback");
}
struct Handle {
    Session session;
    std::unique_ptr<xrt::bo> input,output;
    size_t input_capacity=0,output_capacity=0,input_bytes=0;
    uint32_t nx=0,ny=0,nz=0;
    explicit Handle(const char* root):session(root){}
};
uint64_t maximum(uint32_t nx,uint32_t ny,uint32_t nz) {
    require(nx>=2&&nx<=512&&ny>=2&&ny<=512&&nz>=2&&nz<=512,"MC dimensions outside [2,512] before DMA");
    return uint64_t(9)*(nx-1)*(ny-1)*(nz-1);
}
}

extern "C" const char* mc_error(){return last_error.c_str();}
extern "C" void* mc_open_root(const char* root) {
    try{(void)Session::medical_directory(root);return new Handle(root);}
    catch(const std::exception& e){last_error=e.what();return nullptr;}
}
extern "C" int mc_upload(void* handle,const uint8_t* data,uint64_t bytes,
    uint32_t nx,uint32_t ny,uint32_t nz,double* metrics) {
    try {
        (void)maximum(nx,ny,nz);
        const size_t voxels=size_t(nx)*ny*nz;
        require(data&&bytes==voxels&&metrics,"MC exact input byte count/pointers required before hardware access");
        range(data,voxels);range(metrics,4*sizeof(double));
        require(!overlaps(data,voxels,metrics,4*sizeof(double)),"MC upload input/metrics overlap before hardware access");
        require(handle,"Null MC context before hardware access");auto& h=*static_cast<Handle*>(handle);
        std::lock_guard<std::recursive_mutex> lock(h.session.operation_mutex);
        const auto begin=Clock::now();std::array<double,4> times{};
        // A failed replacement must not expose a partly prepared new mask as
        // the previously valid upload.
        h.nx=h.ny=h.nz=0;h.input_bytes=0;
        const size_t padded=(voxels+63)/64*64;
        auto t=Clock::now();
        if(h.input_capacity<padded) {
            h.input=std::make_unique<xrt::bo>(h.session.buffer(padded+2*GUARD,xrt::bo::flags::cacheable));
            h.input_capacity=padded;
        }
        times[0]=seconds(t);t=Clock::now();
        auto* mapped=h.input->map<unsigned char*>();
        std::memset(mapped,0xa5,GUARD);std::memset(mapped+GUARD+padded,0xa5,GUARD);
        std::memcpy(mapped+GUARD,data,voxels);std::memset(mapped+GUARD+voxels,0,padded-voxels);
        times[1]=seconds(t);t=Clock::now();
        h.input->sync(XCL_BO_SYNC_BO_TO_DEVICE,padded+2*GUARD,0);
        times[2]=seconds(t);times[3]=seconds(begin);
        h.nx=nx;h.ny=ny;h.nz=nz;h.input_bytes=padded;
        std::memcpy(metrics,times.data(),sizeof(times));return 0;
    }catch(const std::exception& e){last_error=e.what();return 1;}
}

// Each call is a real algorithm stream transaction. The UI invokes it in its
// background worker. Count/produce share the same immutable uploaded mask BO.
extern "C" int mc_stream(void* handle,uint32_t mode,uint32_t capacity,uint32_t expected,
    uint8_t* destination,uint64_t destination_capacity,uint32_t* report,double* metrics) {
    try {
        require(mode<=1&&expected<=9u*511u*511u*511u,"MC mode/count invalid before hardware access");
        const uint64_t vertices=mode?0:uint64_t(std::min(capacity,expected))*3;
        const uint64_t output_words=(vertices+7)/8+1,output_bytes=output_words*64;
        require(output_bytes<=MAX_OUTPUT&&destination_capacity>=output_bytes,"MC output allocation bound before hardware access");
        range(destination,size_t(output_bytes));range(report,64);range(metrics,10*sizeof(double));
        require(!overlaps(destination,size_t(output_bytes),report,64)&&
                !overlaps(destination,size_t(output_bytes),metrics,10*sizeof(double))&&
                !overlaps(report,64,metrics,10*sizeof(double)),"MC output/report/metrics overlap before hardware access");
        require(handle,"Null MC context before hardware access");auto& h=*static_cast<Handle*>(handle);
        std::lock_guard<std::recursive_mutex> lock(h.session.operation_mutex);
        require(h.input&&h.input_bytes&&expected<=maximum(h.nx,h.ny,h.nz),"Upload an MC mask before streaming");
        const auto begin=Clock::now();std::array<double,10> times{};auto t=Clock::now();
        if(h.output_capacity<output_bytes) {
            h.output=std::make_unique<xrt::bo>(h.session.buffer(size_t(output_bytes)+2*GUARD,xrt::bo::flags::cacheable));
            h.output_capacity=size_t(output_bytes);
        }
        auto* mapped=h.output->map<unsigned char*>();
        std::memset(mapped,0xa5,GUARD);std::memset(mapped+GUARD+output_bytes,0xa5,GUARD);
        times[0]=seconds(t);t=Clock::now();
        // The core writes every output byte; do not fill/clean the payload.
        h.output->sync(XCL_BO_SYNC_BO_TO_DEVICE,GUARD,0);
        h.output->sync(XCL_BO_SYNC_BO_TO_DEVICE,GUARD,GUARD+size_t(output_bytes));
        times[1]=seconds(t);t=Clock::now();
        const uint64_t ia=h.input->address()+GUARD,oa=h.output->address()+GUARD;
        require(ia%64==0&&oa%64==0,"MC DMA physical alignment");
        require(ia+h.input_bytes<=oa||oa+output_bytes<=ia,"MC physical buffers overlap");
        h.session.select("axis_mc");
        require(h.input->address()+GUARD==ia&&h.output->address()+GUARD==oa,"MC BO moved across DFX");
        times[2]=seconds(t);times[8]=h.session.load_seconds;times[9]=h.session.switch_seconds;t=Clock::now();
        require(!(h.session.gpio->read_register(8)&1)&&(h.session.ip->read_register(0)&4),"MC core not idle");
        for(auto pair:{std::make_pair(h.session.reader.get(),ia),std::make_pair(h.session.writer.get(),oa)}) {
            require(pair.first->read_register(0)&4,"MC static DMA not idle");
            set_dma(*pair.first,0x10,uint32_t(pair.second));set_dma(*pair.first,0x14,uint32_t(pair.second>>32));
        }
        const uint32_t inputs=uint32_t(h.input_bytes/64);
        set_dma(*h.session.reader,0x20,inputs);set_dma(*h.session.writer,0x20,uint32_t(output_words));
        h.session.arg(0x10,h.nx);h.session.arg(0x18,h.ny);h.session.arg(0x20,h.nz);
        h.session.arg(0x28,capacity);h.session.arg(0x30,mode);h.session.arg(0x38,expected);h.session.arg(0x40,inputs);
        const uint32_t transactions=h.session.gpio->read_register(8)>>16;times[3]=seconds(t);t=Clock::now();
        {
            SignalGuard active;
            try {
                h.session.writer->write_register(0,1);h.session.ip->write_register(0,1);h.session.reader->write_register(0,1);
                bool rd=false,wd=false,core=false;
                while(!rd||!wd||!core) {
                    if(!rd)rd=h.session.reader->read_register(0)&2;
                    if(!wd)wd=h.session.writer->read_register(0)&2;
                    if(!core)core=h.session.ip->read_register(0)&2;
                    if(seconds(t)>60)retain("MC stream completion timeout");
                    if(!rd||!wd||!core)std::this_thread::sleep_for(std::chrono::microseconds(20));
                }
            }catch(const std::exception& e){retain(e.what());}catch(...){retain("MC active DMA exception");}
        }
        times[4]=seconds(t);t=Clock::now();
        require(h.session.writer->read_register(0x28)==0,"MC output AXIS framing failure");
        h.session.wait_status(0xffff0000,((transactions+1)&65535)<<16);
        h.output->sync(XCL_BO_SYNC_BO_FROM_DEVICE,size_t(output_bytes)+2*GUARD,0);
        times[5]=seconds(t);t=Clock::now();
        guards(h.input->map<const unsigned char*>(),h.input_bytes);guards(mapped,size_t(output_bytes));
        std::array<uint32_t,16> footer{};std::memcpy(footer.data(),mapped+GUARD+output_bytes-64,64);
        require(footer[0]==0x3141434d&&footer[1]==1&&footer[14]==0&&footer[15]==0,"MC footer identity");
        require(footer[5]==h.nx&&footer[6]==h.ny&&footer[7]==h.nz&&footer[8]==inputs&&
                footer[9]==output_words&&footer[10]==capacity&&footer[11]==mode&&footer[12]==expected,"MC footer configuration");
        require(footer[3]<=maximum(h.nx,h.ny,h.nz)&&footer[4]<=footer[3]&&footer[13]==footer[4]*3,"MC footer counts");
        if(footer[2]==0) {
            require(mode?footer[4]==0:(footer[3]==expected&&footer[4]==std::min(capacity,expected)),"MC successful count mismatch");
            for(size_t i=size_t(footer[4])*24;i+64<output_bytes;++i)
                require(mapped[GUARD+i]==0,"MC logical output tail");
        }
        std::memcpy(destination,mapped+GUARD,size_t(output_bytes));std::memcpy(report,footer.data(),64);
        times[6]=seconds(t);times[7]=seconds(begin);std::memcpy(metrics,times.data(),sizeof(times));return 0;
    }catch(const std::exception& e){last_error=e.what();return 1;}
}
extern "C" int mc_close(void** pointer) {
    try {
        require(pointer&&*pointer,"Null MC context");auto* h=static_cast<Handle*>(*pointer);
        {std::lock_guard<std::recursive_mutex> lock(h->session.operation_mutex);h->session.quiesce();}
        delete h;*pointer=nullptr;return 0;
    }catch(const std::exception& e){last_error=e.what();return 1;}
}

namespace {
static_assert(sizeof(SmoothPoint)==16&&sizeof(SmoothEdge)==8&&sizeof(SmoothFace)==16,"Smoothing ABI sizes");

std::filesystem::path owned_output(Handle& handle,const char* value) {
    require(value&&*value,"Explicit reconstruction output path required");
    const auto project=handle.session.medical_root.parent_path().parent_path();
    std::filesystem::path path(value);
    require(path.is_absolute()&&path.lexically_normal()==path&&std::filesystem::is_directory(path.parent_path()),"Canonical reconstruction output parent required");
    const auto resolved=std::filesystem::weakly_canonical(path);
    const auto relative=resolved.lexically_relative(project);
    require(!relative.empty()&&!relative.is_absolute()&&*relative.begin()!=".."&&!std::filesystem::is_symlink(path),"Output outside owned medical project");
    require(!std::filesystem::exists(path),"Preserve existing reconstruction output");
    return path;
}

#include "smooth_guarded.inc"
}

extern "C" int mc_smooth_job(void* pointer,const char* folder,const char* output,const char* report) {
    try {
        require(pointer&&folder&&*folder&&output&&*output&&report&&*report,"Null smoothing command before hardware access");
        auto& h=*static_cast<Handle*>(pointer);std::lock_guard<std::recursive_mutex> lock(h.session.operation_mutex);
        std::filesystem::path input(folder);const auto project=h.session.medical_root.parent_path().parent_path();
        require(input.is_absolute()&&input.lexically_normal()==input&&std::filesystem::is_directory(input)&&
                std::filesystem::canonical(input)==input,"Canonical smoothing input folder required");
        const auto relative=input.lexically_relative(project);
        require(!relative.empty()&&!relative.is_absolute()&&*relative.begin()!="..","Smoothing input outside medical project");
        const auto out=owned_output(h,output),metadata=owned_output(h,report);
        require(out!=metadata,"Distinct smoothing output/report paths required");
        // All MC DMA is already drained. Geometry/CSR now lives in the staged
        // files, so its large BO pool need not overlap smoothing allocations.
        h.input.reset();h.output.reset();h.input_capacity=h.output_capacity=h.input_bytes=0;
        h.nx=h.ny=h.nz=0;
        smooth_job_impl(h.session,input,out,metadata);return 0;
    }catch(const std::exception& e){last_error=e.what();return 1;}
}

extern "C" int mc_session_report(void* pointer,const char* filename) {
    try {
        require(pointer&&filename&&*filename,"Null session report before hardware access");
        auto& h=*static_cast<Handle*>(pointer);std::lock_guard<std::recursive_mutex> lock(h.session.operation_mutex);
        const auto path=owned_output(h,filename);struct rusage usage{};
        require(getrusage(RUSAGE_SELF,&usage)==0,"Cannot read reconstruction process memory");
        writefile(path,"{\"partial_switches\":"+std::to_string(h.session.switches)+
            ",\"xrt_metadata_loads\":1,\"fixed_dma_cus\":2,\"peak_rss_kib\":"+std::to_string(usage.ru_maxrss)+
            ",\"mc_backend\":\"DFX_PL_MC_AXIS_D7\",\"smooth_backend\":\"DFX_PL_FMA2\",\"boot_id\":\""+
            h.session.boot.substr(0,36)+"\"}\n");return 0;
    }catch(const std::exception& e){last_error=e.what();return 1;}
}
