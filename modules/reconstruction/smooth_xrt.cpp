#include <xrt/xrt_device.h>
#include <xrt/xrt_bo.h>
#include <experimental/xrt_ip.h>
#include "hls/mesh_smooth.hpp"
#include "fpga/firmware_guard.hpp"
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <sstream>
#include <thread>
#include <vector>
using Clock=std::chrono::steady_clock;
template<class T> std::vector<T> read(const std::filesystem::path& file,size_t count){
    std::ifstream f(file,std::ios::binary|std::ios::ate);if(!f||f.tellg()!=std::streamoff(count*sizeof(T)))throw std::runtime_error("Input size mismatch: "+file.string());
    std::vector<T> v(count);f.seekg(0);f.read(reinterpret_cast<char*>(v.data()),count*sizeof(T));if(!f)throw std::runtime_error("Input read failed");return v;
}
static double seconds(Clock::time_point t){return std::chrono::duration<double>(Clock::now()-t).count();}
struct Session {
    xrt::device device;
    xrt::uuid uuid;
    xrt::ip ip;
    explicit Session(const char* metadata):device(0),uuid(device.load_xclbin(metadata)),ip(device,uuid,"mesh_smooth:mesh_smooth_0"){}
};
static void run_job(const char* metadata,const std::filesystem::path& folder,const std::filesystem::path& output_path,
    const std::filesystem::path& report_path,std::unique_ptr<Session>& session,bool worker){
    unsigned nv,nf,nnz,iterations;float limit;
    std::ifstream config(folder/"config.txt");config>>nv>>nf>>nnz>>limit>>iterations;
    if(!config||!nv||nv>1000000||nf>2000000||nnz>12000000||!std::isfinite(limit)||limit<=0||iterations<1||iterations>16)throw std::runtime_error("Invalid smoothing dimensions");
    auto original=read<SmoothPoint>(folder/"original.bin",nv);auto rows=read<uint32_t>(folder/"rows.bin",nv+1);
    auto edges=read<SmoothEdge>(folder/"edges.bin",nnz);auto frozen=read<uint32_t>(folder/"frozen.bin",nv);auto faces=read<SmoothFace>(folder/"faces.bin",nf);
    for(auto p:original)if(!std::isfinite(p.x)||!std::isfinite(p.y)||!std::isfinite(p.z))throw std::runtime_error("Nonfinite point");
    if(rows[0]||rows.back()!=nnz||!std::is_sorted(rows.begin(),rows.end()))throw std::runtime_error("Invalid CSR row offsets");
    for(auto e:edges)if(e.index>=nv||!std::isfinite(e.weight)||e.weight<=0)throw std::runtime_error("Invalid neighbor");
    for(auto f:faces)if(f.a>=nv||f.b>=nv||f.c>=nv)throw std::runtime_error("Invalid triangle");
    for(auto v:frozen)if(v>1)throw std::runtime_error("Invalid frozen mask");
    std::ifstream fw("/sys/firmware/devicetree/base/fpga-region/firmware-name",std::ios::binary);std::string firmware;std::getline(fw,firmware,'\0');
    if(firmware!="kv260_mc_smooth.bit.bin")throw std::runtime_error("Smoothing firmware not active; no registers accessed");
    auto expected=std::filesystem::canonical("/proc/self/exe").parent_path().parent_path()/"smooth/package/kv260_mc_smooth.xclbin";
    require_loaded_smooth_package(expected);
    std::ifstream a(metadata,std::ios::binary),b(expected,std::ios::binary);
    if(!a||!b||!std::equal(std::istreambuf_iterator<char>(a),std::istreambuf_iterator<char>(),std::istreambuf_iterator<char>(b),std::istreambuf_iterator<char>()))throw std::runtime_error("Metadata does not match reconstruction firmware");
    auto start=Clock::now();bool reused=bool(session);
    if(!session)session=std::make_unique<Session>(metadata);
    auto& device=session->device;auto& ip=session->ip;
    if(!(ip.read_register(0)&4))throw std::runtime_error("Smoothing accelerator not idle");
    std::vector<xrt::bo> buffers;
    auto input=[&](const void* source,size_t bytes){buffers.emplace_back(device,std::max<size_t>(bytes,16),xrt::bo::flags::normal,0);auto& bo=buffers.back();if(bytes)std::memcpy(bo.map<void*>(),source,bytes);bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);};
    input(original.data(),nv*sizeof(SmoothPoint));input(rows.data(),rows.size()*4);input(edges.data(),edges.size()*sizeof(SmoothEdge));input(frozen.data(),nv*4);input(faces.data(),nf*sizeof(SmoothFace));
    for(unsigned i=0;i<5;++i)buffers.emplace_back(device,nv*sizeof(SmoothPoint),xrt::bo::flags::normal,0);
    buffers.emplace_back(device,64,xrt::bo::flags::normal,0);
    for(unsigned i=0;i<buffers.size();++i){uint32_t offset=0x10+i*0x10;auto address=buffers[i].address();if(address%64)throw std::runtime_error("DMA buffer does not meet 64-byte HLS alignment");ip.write_register(offset,uint32_t(address));ip.write_register(offset+4,uint32_t(address>>32));
        if(ip.read_register(offset)!=uint32_t(address)||ip.read_register(offset+4)!=uint32_t(address>>32))throw std::runtime_error("DMA address readback mismatch");}
    uint32_t limit_bits;std::memcpy(&limit_bits,&limit,4);
    for(auto arg:std::array<std::pair<uint32_t,uint32_t>,5>{{{0xc0,nv},{0xc8,nf},{0xd0,nnz},{0xd8,limit_bits},{0xe0,iterations}}}){ip.write_register(arg.first,arg.second);if(ip.read_register(arg.first)!=arg.second)throw std::runtime_error("Scalar argument mismatch");}
    double prepare_seconds=seconds(start);auto pl_start=Clock::now();ip.read_register(0);ip.write_register(0,1);
    while(!(ip.read_register(0)&2)){
        if(seconds(pl_start)>180){std::cerr<<"FATAL: PL timeout. DMA buffers retained; reset board before terminating process.\n"<<std::flush;for(;;)std::this_thread::sleep_for(std::chrono::seconds(60));}
        std::this_thread::sleep_for(std::chrono::microseconds(100));}
    double pl_seconds=seconds(pl_start);buffers[10].sync(XCL_BO_SYNC_BO_FROM_DEVICE);auto report=buffers[10].map<const uint32_t*>();
    if(report[0])throw std::runtime_error("PL smoothing status="+std::to_string(report[0]));
    buffers[5].sync(XCL_BO_SYNC_BO_FROM_DEVICE);std::ofstream output(output_path,std::ios::binary);output.write(buffers[5].map<const char*>(),nv*sizeof(SmoothPoint));if(!output)throw std::runtime_error("Output write failed");
    float before,after;std::memcpy(&before,report+2,4);std::memcpy(&after,report+3,4);
    std::ofstream result(report_path);result<<"{\"backend\":\"pl\",\"context_reused\":"<<(reused?"true":"false")<<",\"pl_seconds\":"<<pl_seconds<<",\"prepare_seconds\":"<<prepare_seconds<<",\"host_seconds\":"<<seconds(start)<<",\"accepted_iterations\":"<<report[1]<<",\"attempts\":"<<report[4]<<",\"roughness_before_mm\":"<<before<<",\"roughness_after_mm\":"<<after<<",\"status\":"<<report[0]<<"}\n";
    if(!result)throw std::runtime_error("Cannot write report");
    if(!worker)std::cout<<"PL smoothing seconds="<<pl_seconds<<std::endl;
}
int main(int argc,char** argv){try{
    std::unique_ptr<Session> session;
    if(argc==3&&std::string(argv[1])=="--session"){
        // Task-scoped stdin protocol. EOF releases the idle context; no daemon.
        std::cout<<"READY"<<std::endl;
        std::string line;
        while(std::getline(std::cin,line)){
            std::istringstream fields(line);std::string input,output,report,extra;
            if(!std::getline(fields,input,'\t')||!std::getline(fields,output,'\t')||!std::getline(fields,report,'\t')||std::getline(fields,extra,'\t')||input.empty()||output.empty()||report.empty())
                throw std::runtime_error("Invalid session request");
            run_job(argv[2],input,output,report,session,true);
            std::cout<<"DONE"<<std::endl;
        }
    } else {
        if(argc!=5)throw std::runtime_error("Usage: smooth_xrt firmware.xclbin input_folder output.f32 report.json OR --session firmware.xclbin");
        run_job(argv[1],argv[2],argv[3],argv[4],session,false);
    }
    return 0;
}catch(const std::exception& e){std::cerr<<"ERROR: "<<e.what()<<std::endl;return 1;}}
