#include <xrt/xrt_device.h>
#include <xrt/xrt_bo.h>
#include <experimental/xrt_ip.h>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <vector>
#include <iterator>
#include <cstdlib>
#include "fpga/firmware_guard.hpp"

using Clock = std::chrono::steady_clock;
static double elapsed(Clock::time_point t) {
    return std::chrono::duration<double>(Clock::now()-t).count();
}
static void pointer(xrt::ip& ip, uint32_t offset, uint64_t address) {
    ip.write_register(offset, uint32_t(address));
    ip.write_register(offset+4, uint32_t(address >> 32));
}
struct Result { uint32_t required, written, status; double seconds; };
static Result run(xrt::ip& ip, const xrt::bo& input, const xrt::bo& output,
                  uint32_t nx, uint32_t ny, uint32_t nz, uint32_t capacity, bool count) {
    pointer(ip,0x10,input.address()); pointer(ip,0x20,output.address());
    ip.write_register(0x30,nx); ip.write_register(0x38,ny); ip.write_register(0x40,nz);
    ip.write_register(0x48,capacity); ip.write_register(0x50,count);
    if (ip.read_register(0x30)!=nx || ip.read_register(0x38)!=ny || ip.read_register(0x40)!=nz ||
        ip.read_register(0x10)!=uint32_t(input.address()) || ip.read_register(0x14)!=uint32_t(input.address()>>32) ||
        ip.read_register(0x20)!=uint32_t(output.address()) || ip.read_register(0x24)!=uint32_t(output.address()>>32) ||
        ip.read_register(0x48)!=capacity || ip.read_register(0x50)!=uint32_t(count))
        throw std::runtime_error("AXI-Lite argument readback mismatch");
    ip.read_register(0);
    auto start=Clock::now(); ip.write_register(0,1);
    while (!(ip.read_register(0)&2)) {
        if (elapsed(start)>30) {
            // Do not release DDR allocations while a PL master may still write.
            std::cerr << "FATAL: PL timeout. Buffers retained; reset board before terminating this process.\n" << std::flush;
            for (;;) std::this_thread::sleep_for(std::chrono::seconds(60));
        }
        std::this_thread::sleep_for(std::chrono::microseconds(100));
    }
    return {ip.read_register(0x58),ip.read_register(0x68),ip.read_register(0x78),elapsed(start)};
}
int main(int argc,char** argv) {
    try {
        if (argc!=8) {
            std::cerr << "Usage: mc_xrt design.xclbin mask.u8 nx ny nz vertices.u64 report.json\n";
            return 2;
        }
        const auto nx=std::stoul(argv[3]),ny=std::stoul(argv[4]),nz=std::stoul(argv[5]);
        for (auto n : {nx,ny,nz}) if (n<2||n>512) throw std::runtime_error("Dimensions must be 2..512");
        const size_t bytes=nx*ny*nz;
        std::vector<uint8_t> mask(bytes);
        std::ifstream source(argv[2],std::ios::binary|std::ios::ate);
        if (!source||source.tellg()!=std::streamoff(bytes)) throw std::runtime_error("Mask size does not match dimensions");
        source.seekg(0); source.read(reinterpret_cast<char*>(mask.data()),bytes);
        if (!source||std::any_of(mask.begin(),mask.end(),[](auto v){return v>1;})) throw std::runtime_error("Expected uint8 binary Mask");
        if (!std::filesystem::exists("/sys/bus/platform/devices/axi:mc_platform/driver") ||
            !std::filesystem::exists("/sys/bus/platform/devices/axi:mc_afi/driver"))
            throw std::runtime_error("MC firmware/platform not ready; load matching firmware manually");
        std::ifstream firmware("/sys/firmware/devicetree/base/fpga-region/firmware-name",std::ios::binary);
        std::string loaded;std::getline(firmware,loaded,'\0');
        if (loaded!="medical_axis4.bit.bin" && loaded!="kv260_mc_smooth.bit.bin")
            throw std::runtime_error("Reconstruction firmware is not active; refusing PL register access");
        {
            // Loading a different CU layout makes this XRT version tear down its
            // existing CUs. Both algorithms must use the same combined metadata.
            auto expected=std::filesystem::canonical("/proc/self/exe").parent_path().parent_path()/
                (loaded=="medical_axis4.bit.bin" ? "render_axis/package/medical_axis4.xclbin" : "smooth/package/kv260_mc_smooth.xclbin");
            if(loaded=="kv260_mc_smooth.bit.bin")require_loaded_smooth_package(expected);
            std::ifstream a(argv[1],std::ios::binary),b(expected,std::ios::binary);
            if (!a||!b||!std::equal(std::istreambuf_iterator<char>(a),std::istreambuf_iterator<char>(),
                                   std::istreambuf_iterator<char>(b),std::istreambuf_iterator<char>()))
                throw std::runtime_error("MC requires metadata matching the active reconstruction firmware");
        }
        auto device=xrt::device(0);
        auto uuid=device.load_xclbin(argv[1]);
        auto ip=xrt::ip(device,uuid,"binary_mc:binary_mc_0");
        auto ctrl=ip.read_register(0);
        if (!(ctrl&4)) throw std::runtime_error("MC accelerator is not idle");
        auto start=Clock::now();
        auto input=xrt::bo(device,bytes,xrt::bo::flags::normal,0);
        std::memcpy(input.map<void*>(),mask.data(),bytes);
        input.sync(XCL_BO_SYNC_BO_TO_DEVICE);
        size_t initial_mib=32;
        if(const char* text=std::getenv("MC_PL_INITIAL_OUTPUT_MIB")) {
            size_t used=0;initial_mib=std::stoul(text,&used);
            if(text[used]!='\0'||initial_mib<1||initial_mib>128)
                throw std::runtime_error("MC_PL_INITIAL_OUTPUT_MIB must be 1..128");
        }
        // The kernel counts all cells even after capacity overflow. Generate
        // first, then retry only if necessary: avoid a compulsory full scan.
        const size_t bound=9*size_t(nx-1)*(ny-1)*(nz-1);
        const uint32_t first_capacity=uint32_t(std::min(bound,initial_mib*1024*1024/24));
        size_t allocation=std::max<size_t>(size_t(first_capacity)*24,8);
        auto output=xrt::bo(device,allocation,xrt::bo::flags::normal,0);
        Result result=run(ip,input,output,nx,ny,nz,first_capacity,false);
        const double first_seconds=result.seconds;
        unsigned generation_passes=1;
        if(result.status & ~uint32_t(2)) throw std::runtime_error("Generation status="+std::to_string(result.status));
        if(result.status==2) {
            if(result.required<=first_capacity||result.written!=first_capacity)
                throw std::runtime_error("Invalid overflow/count response");
            allocation=std::max<size_t>(size_t(result.required)*24,8);
            if(allocation>128*1024*1024)throw std::runtime_error("Output exceeds 128 MiB budget");
            const uint32_t required=result.required;
            output=xrt::bo(device,allocation,xrt::bo::flags::normal,0);
            result=run(ip,input,output,nx,ny,nz,required,false);
            ++generation_passes;
            if(result.required!=required)throw std::runtime_error("Count changed on generation retry");
        }
        if(result.status||result.written!=result.required)throw std::runtime_error("Incomplete generation");
        const size_t out_bytes=size_t(result.written)*24;
        // Synchronize only the valid prefix, especially for sparse airway masks.
        if(out_bytes)output.sync(XCL_BO_SYNC_BO_FROM_DEVICE,out_bytes,0);
        const double runtime=elapsed(start);
        std::ofstream mesh(argv[6],std::ios::binary);
        mesh.write(output.map<const char*>(),out_bytes);
        if (!mesh) throw std::runtime_error("Cannot write vertices");
        std::ofstream report(argv[7]);
        report << "{\n  \"runtime\": \"native XRT C++ user-managed IP\",\n"
               << "  \"triangles\": " << result.written << ",\n"
               << "  \"count_seconds\": 0,\n"
               << "  \"generation_passes\": " << generation_passes << ",\n"
               << "  \"initial_capacity_triangles\": " << first_capacity << ",\n"
               << "  \"output_allocated_bytes\": " << allocation << ",\n"
               << "  \"output_valid_bytes\": " << out_bytes << ",\n"
               << "  \"generate_seconds\": " << (generation_passes==1 ? result.seconds : first_seconds+result.seconds) << ",\n"
               << "  \"host_seconds_excluding_load_and_files\": " << runtime << ",\n"
               << "  \"input_address\": " << input.address() << ",\n"
               << "  \"output_address\": " << output.address() << "\n}\n";
        if (!report) throw std::runtime_error("Cannot write report");
        std::cout << "Triangles=" << result.written << ", host seconds=" << runtime << std::endl;
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "ERROR: " << e.what() << std::endl;
        return 1;
    }
}
