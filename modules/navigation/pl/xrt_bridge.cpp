#include <xrt/xrt_device.h>
#include <xrt/xrt_bo.h>
#include <experimental/xrt_ip.h>
#include <array>
#include <algorithm>
#include <chrono>
#include <csignal>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <regex>
#include <thread>
using Clock=std::chrono::steady_clock;
static double elapsed(Clock::time_point start){return std::chrono::duration<double>(Clock::now()-start).count();}
static void error_text(char* buffer,size_t length,const std::exception& error){if(length){std::strncpy(buffer,error.what(),length-1);buffer[length-1]=0;}}
static void guard(const std::filesystem::path& metadata){
    std::ifstream fw("/sys/firmware/devicetree/base/fpga-region/firmware-name",std::ios::binary);std::string firmware;
    std::getline(fw,firmware,'\0');if(firmware!="kv260_navigation.bit.bin")throw std::runtime_error("Navigation firmware not active; no MMIO access");
    std::ifstream mf(metadata.parent_path()/"manifest.json"),marker("/run/kv260-navigation-loaded.sha256");
    std::string manifest((std::istreambuf_iterator<char>(mf)),{}),hash;std::getline(marker,hash);std::smatch match;
    if(!mf||!marker||!std::regex_search(manifest,match,std::regex("\"bit_bin_sha256\"\\s*:\\s*\"([0-9a-f]{64})\""))||hash!=match[1].str())
        throw std::runtime_error("Loaded firmware hash differs; no XRT device or MMIO access");
    std::ifstream a(metadata,std::ios::binary),b("/lib/firmware/xilinx/kv260-navigation-v1/kv260_navigation.xclbin",std::ios::binary);
    if(!a||!b||!std::equal(std::istreambuf_iterator<char>(a),std::istreambuf_iterator<char>(),std::istreambuf_iterator<char>(b),std::istreambuf_iterator<char>()))
        throw std::runtime_error("Metadata mismatch; no XRT device or MMIO access");
}
struct Session{
    xrt::device device;xrt::uuid uuid;std::array<std::unique_ptr<xrt::ip>,6> ip;
    std::unique_ptr<xrt::bo> input,output;size_t capacity=0;bool active=false,compact=false,shared=false;
    Session(const char* metadata):device(0),uuid(device.load_xclbin(metadata)){
        const char* names[]={"nav_reader:nav_reader_0","nav_edt:nav_edt_0","nav_writer:nav_writer_0",
            "nav_reader:nav_route_reader_0","nav_route:nav_route_0","nav_writer:nav_route_writer_0"};
        std::ifstream mf(std::filesystem::path(metadata).parent_path()/"manifest.json");
        std::string manifest((std::istreambuf_iterator<char>(mf)),{});
        compact=std::regex_search(manifest,std::regex("\"route_protocol\"\\s*:\\s*\"compact.v2\""));
        shared=std::regex_search(manifest,std::regex("\"route_dma\"\\s*:\\s*\"shared.v1\""));
        if(compact)names[5]="nav_route_writer:nav_route_writer_0";
        unsigned count=std::regex_search(manifest,std::regex("\"route_core\"\\s*:\\s*\"nav_route.v1\""))?6:3;
        if(shared){names[0]="nav_reader_split:nav_reader_0";names[2]="nav_writer_merge:nav_writer_0";names[3]="nav_route:nav_route_0";count=4;}
        for(unsigned i=0;i<count;++i)ip[i]=std::make_unique<xrt::ip>(device,uuid,names[i]);
    }
};
extern "C" void* nav_open(const char* metadata,char* error,size_t error_size){
    try{guard(metadata);return new Session(metadata);}catch(const std::exception& e){error_text(error,error_size,e);return nullptr;}
}
extern "C" void nav_close(void* handle){delete static_cast<Session*>(handle);}
extern "C" int nav_run(void* handle,const void* source,void* destination,unsigned length,unsigned groups,unsigned weight,unsigned mode,
    double* hardware_seconds,double* host_seconds,char* error,size_t error_size){
    try{
        if(!handle||!source||!destination||!length||length>1024||!groups||groups>131072||!weight||mode>1)
            throw std::runtime_error("Invalid navigation line job");
        auto& s=*static_cast<Session*>(handle);size_t bytes=size_t(length)*groups*64;unsigned count=length*groups;
        if(bytes>640000000)throw std::runtime_error("Navigation transfer exceeds 80M-voxel budget");
        auto start=Clock::now();for(unsigned i=0;i<3;++i)if(!(s.ip[i]->read_register(0)&4))throw std::runtime_error("Navigation CU is not idle");
        if(bytes>s.capacity){s.input=std::make_unique<xrt::bo>(s.device,bytes,xrt::bo::flags::normal,0);
            s.output=std::make_unique<xrt::bo>(s.device,bytes,xrt::bo::flags::normal,0);s.capacity=bytes;}
        std::memcpy(s.input->map<void*>(),source,bytes);s.input->sync(XCL_BO_SYNC_BO_TO_DEVICE,bytes,0);
        auto pointer=[&](unsigned ip,uint64_t address){if(address%64)throw std::runtime_error("Unaligned DMA buffer");
            s.ip[ip]->write_register(0x10,uint32_t(address));s.ip[ip]->write_register(0x14,uint32_t(address>>32));};
        pointer(0,s.input->address());pointer(2,s.output->address());
        s.ip[0]->write_register(0x20,count);s.ip[2]->write_register(0x20,count);
        if(s.shared){s.ip[0]->write_register(0x28,0);s.ip[2]->write_register(0x38,0);}
        for(auto scalar:std::array<std::pair<unsigned,unsigned>,4>{{{0x10,length},{0x18,groups},{0x20,weight},{0x28,mode}}})
            s.ip[1]->write_register(scalar.first,scalar.second);
        for(unsigned i=0;i<3;++i)s.ip[i]->read_register(0);
        auto old_int=std::signal(SIGINT,SIG_IGN),old_term=std::signal(SIGTERM,SIG_IGN);
        auto pl_start=Clock::now();s.active=true;s.ip[2]->write_register(0,1);s.ip[1]->write_register(0,1);s.ip[0]->write_register(0,1);
        std::array<bool,3> done{{false,false,false}};
        while(!std::all_of(done.begin(),done.end(),[](bool x){return x;})){
            for(unsigned i=0;i<3;++i)if(!done[i])done[i]=(s.ip[i]->read_register(0)&2)!=0;
            if(elapsed(pl_start)>60){std::cerr<<"FATAL: navigation DMA timeout; buffers retained. Reset board before stopping worker.\n"<<std::flush;
                for(;;)std::this_thread::sleep_for(std::chrono::seconds(10));}
            std::this_thread::sleep_for(std::chrono::microseconds(50));
        }
        s.active=false;*hardware_seconds=elapsed(pl_start);std::signal(SIGINT,old_int);std::signal(SIGTERM,old_term);
        if(s.ip[1]->read_register(0x30)||s.ip[2]->read_register(0x28))throw std::runtime_error("PL navigation protocol/status error");
        if(s.shared&&s.ip[2]->read_register(0x30)!=count)throw std::runtime_error("Shared EDT writer length mismatch");
        s.output->sync(XCL_BO_SYNC_BO_FROM_DEVICE,bytes,0);std::memcpy(destination,s.output->map<void*>(),bytes);
        *host_seconds=elapsed(start);return 0;
    }catch(const std::exception& e){
        if(handle&&static_cast<Session*>(handle)->active){
            std::cerr<<"FATAL: error during active DMA: "<<e.what()<<"; buffers retained. Reset board before stopping worker.\n"<<std::flush;
            for(;;)std::this_thread::sleep_for(std::chrono::seconds(10));
        }
        error_text(error,error_size,e);return 1;
    }
}
extern "C" int nav_route_run(void* handle,const void* source,void* destination,unsigned input_count,unsigned output_count,unsigned operation,
    double* hardware_seconds,double* host_seconds,char* error,size_t error_size){
    try{
        if(!handle||!source||!destination||!input_count||input_count>131072||!output_count||output_count>16384||operation>1)
            throw std::runtime_error("Invalid navigation route job");
        auto& s=*static_cast<Session*>(handle);size_t in_bytes=size_t(input_count)*64,out_bytes=size_t(output_count)*64;
        if(!s.ip[3])throw std::runtime_error("Route core absent from this navigation package");
        const std::array<unsigned,3> cores{{s.shared?0U:3U,s.shared?3U:4U,s.shared?2U:5U}};
        unsigned reader=cores[0],core=cores[1],writer=cores[2];
        auto start=Clock::now();for(unsigned i:cores)if(!(s.ip[i]->read_register(0)&4))throw std::runtime_error("Route CU is not idle");
        // Reserve the query output capacity during scene upload, so the first
        // query does not allocate and map a second pair of BOs.
        constexpr size_t route_capacity=(2+512+8192)*64;
        size_t capacity=std::max(std::max(in_bytes,out_bytes),route_capacity);
        if(capacity>s.capacity){s.input=std::make_unique<xrt::bo>(s.device,capacity,xrt::bo::flags::normal,0);
            s.output=std::make_unique<xrt::bo>(s.device,capacity,xrt::bo::flags::normal,0);s.capacity=capacity;}
        std::memcpy(s.input->map<void*>(),source,in_bytes);s.input->sync(XCL_BO_SYNC_BO_TO_DEVICE,in_bytes,0);
        auto pointer=[&](unsigned ip,uint64_t address){if(address%64)throw std::runtime_error("Unaligned route buffer");
            s.ip[ip]->write_register(0x10,uint32_t(address));s.ip[ip]->write_register(0x14,uint32_t(address>>32));};
        pointer(reader,s.input->address());pointer(writer,s.output->address());
        s.ip[reader]->write_register(0x20,input_count);s.ip[writer]->write_register(0x20,output_count);
        if(s.shared){s.ip[reader]->write_register(0x28,1);s.ip[writer]->write_register(0x38,1);}
        s.ip[core]->write_register(0x10,operation);s.ip[core]->write_register(0x18,input_count);s.ip[core]->write_register(0x20,output_count);
        for(unsigned i:cores)s.ip[i]->read_register(0);
        auto old_int=std::signal(SIGINT,SIG_IGN),old_term=std::signal(SIGTERM,SIG_IGN);
        auto pl_start=Clock::now();s.active=true;s.ip[writer]->write_register(0,1);s.ip[core]->write_register(0,1);s.ip[reader]->write_register(0,1);
        std::array<bool,3> done{{false,false,false}};
        while(!std::all_of(done.begin(),done.end(),[](bool x){return x;})){
            for(unsigned i=0;i<3;++i)if(!done[i])done[i]=(s.ip[cores[i]]->read_register(0)&2)!=0;
            if(elapsed(pl_start)>60){std::cerr<<"FATAL: route DMA timeout; buffers retained. Reset board before stopping worker.\n"<<std::flush;
                for(;;)std::this_thread::sleep_for(std::chrono::seconds(10));}
            std::this_thread::sleep_for(std::chrono::microseconds(50));
        }
        s.active=false;*hardware_seconds=elapsed(pl_start);std::signal(SIGINT,old_int);std::signal(SIGTERM,old_term);
        unsigned result=s.ip[core]->read_register(0x28),writer_status=s.ip[writer]->read_register(0x28);
        if(writer_status)throw std::runtime_error("Route writer framing error");
        unsigned written=s.compact?s.ip[writer]->read_register(0x30):output_count;
        if(!written||written>output_count)throw std::runtime_error("Route writer invalid length");
        out_bytes=size_t(written)*64;
        s.output->sync(XCL_BO_SYNC_BO_FROM_DEVICE,out_bytes,0);
        if(s.compact){
            auto header=s.output->map<const uint64_t*>();
            if(operation==0){if(written!=1)throw std::runtime_error("Invalid scene acknowledgment length");}
            else if(written<2||header[1]>4096||header[2]>4096||written!=2+(header[2]+7)/8+header[1]*2)
                throw std::runtime_error("Route payload differs from header length");
        }
        std::memcpy(destination,s.output->map<void*>(),out_bytes);
        *host_seconds=elapsed(start);return int(result);
    }catch(const std::exception& e){
        if(handle&&static_cast<Session*>(handle)->active){std::cerr<<"FATAL: active route DMA error: "<<e.what()<<"; buffers retained. Reset board before stopping worker.\n"<<std::flush;
            for(;;)std::this_thread::sleep_for(std::chrono::seconds(10));}
        error_text(error,error_size,e);return -1;
    }
}
