#pragma once
#include <xrt/xrt_device.h>
#include <xrt/xrt_bo.h>
#include <experimental/xrt_ip.h>
#include <algorithm>
#include <chrono>
#include <csignal>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <mutex>
#include <regex>
#include <stdexcept>
#include <thread>
#include <vector>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <unistd.h>
namespace medical {
using Clock=std::chrono::steady_clock;
inline double seconds(Clock::time_point t){return std::chrono::duration<double>(Clock::now()-t).count();}
inline void require(bool b,const std::string& s){if(!b)throw std::runtime_error(s);}
inline std::string readfile(const std::filesystem::path& p){std::ifstream f(p,std::ios::binary);require(bool(f),"Cannot read "+p.string());return {std::istreambuf_iterator<char>(f),{}};}
inline void writefile(const std::filesystem::path& p,const std::string& s){std::ofstream f(p);f<<s;f.close();require(bool(f),"Cannot write "+p.string());}
template<class T> std::vector<T> read(const std::filesystem::path& file,size_t count){
 std::ifstream f(file,std::ios::binary|std::ios::ate);require(bool(f)&&f.tellg()==std::streamoff(count*sizeof(T)),"Input size mismatch: "+file.string());
 std::vector<T> v(count);f.seekg(0);f.read(reinterpret_cast<char*>(v.data()),count*sizeof(T));require(bool(f),"Input read failed");return v;
}
[[noreturn]] inline void retain(const std::string& why){std::cerr<<"FATAL DMA ACTIVE: "<<why<<". Buffers retained; reset board before stopping this process.\n"<<std::flush;for(;;)std::this_thread::sleep_for(std::chrono::seconds(10));}
class Mmio {
 volatile uint32_t* base=nullptr;int fd=-1;
 public:
 explicit Mmio(uint64_t address){fd=open("/dev/mem",O_RDWR|O_SYNC);require(fd>=0,"open /dev/mem");base=static_cast<volatile uint32_t*>(mmap(nullptr,65536,PROT_READ|PROT_WRITE,MAP_SHARED,fd,address));require(base!=MAP_FAILED,"mmap");}
 ~Mmio(){munmap(const_cast<uint32_t*>(base),65536);close(fd);}
 uint32_t read_register(unsigned offset){__sync_synchronize();uint32_t v=base[offset/4];__sync_synchronize();return v;}
 void write_register(unsigned offset,uint32_t v){__sync_synchronize();base[offset/4]=v;__sync_synchronize();}
};
struct Session {
 std::recursive_mutex operation_mutex;
 int lock=-1;std::string boot;std::unique_ptr<xrt::device> device;std::unique_ptr<xrt::ip> reader,writer;
 std::unique_ptr<Mmio> gpio,ip;std::unique_ptr<xrt::bo> sentinel,echo_output;std::string current;
 std::vector<uint32_t> expected,snapshot;
 unsigned switches=0;double load_seconds=0,switch_seconds=0;std::ofstream switch_log;
 Session(){
  lock=open("/tmp/kv260-ct-pl.lock",O_RDONLY);require(lock>=0&&flock(lock,LOCK_EX|LOCK_NB)==0,"PL already in use");
  require(readfile("/sys/firmware/devicetree/base/fpga-region/firmware-name").find("dfx_medical.bin")==0,"Wrong static shell; no MMIO/XRT access");
  std::string manifest=readfile("release/manifest.json"),active=readfile("/run/kv260-dfx-medical-loaded.sha256");std::smatch match;
  require(std::regex_search(manifest,match,std::regex("\"bit_bin_sha256\"\\s*:\\s*\"([0-9a-f]{64})\""))&&active==match[1].str()+"\n","Static shell hash mismatch");
  require(readfile("release/dfx_medical.xclbin")==readfile("/lib/firmware/xilinx/kv260-dfx-medical/dfx_medical.xclbin"),"Metadata mismatch");
  for(auto name:{"mc","smooth","ct","edt","route"})require(readfile(std::string("release/medical_")+name+"_partial.bin")==readfile(std::string("/lib/firmware/medical_")+name+"_partial.bin"),"Partial identity mismatch");
  require(readfile("../surface/release/medical_surface_partial.bin")==readfile("/lib/firmware/medical_surface_partial.bin"),"Scope partial identity mismatch");
  boot=readfile("/proc/sys/kernel/random/boot_id");gpio=std::make_unique<Mmio>(0x80000000);ip=std::make_unique<Mmio>(0x80030000);
  device=std::make_unique<xrt::device>(0);auto uuid=device->load_xclbin("release/dfx_medical.xclbin");
  reader=std::make_unique<xrt::ip>(*device,uuid,"dfx_reader:dfx_reader");writer=std::make_unique<xrt::ip>(*device,uuid,"dfx_writer:dfx_writer");
  sentinel=std::make_unique<xrt::bo>(buffer(1048576));expected.resize(1048576/4);snapshot.resize(expected.size());
  for(unsigned j=0;j<expected.size();++j){expected[j]=j*2654435761u+0x19283746u;}
  std::memcpy(sentinel->map<void*>(),expected.data(),1048576);
  sentinel->sync(XCL_BO_SYNC_BO_TO_DEVICE);
  switch_log.open(std::string("../surface/results/switches_")+std::to_string(getpid())+".csv");switch_log<<"switch,rm,partial_ms,switch_ms,static_transactions,sentinel_address\n";
 }
 void wait_status(uint32_t mask,uint32_t value){auto t=Clock::now();while((gpio->read_register(8)&mask)!=value){require(seconds(t)<2,"Shutdown/identity timeout");std::this_thread::sleep_for(std::chrono::microseconds(20));}}
 void quiesce(){
  auto state=gpio->read_register(8);
  if(!(state&1)){
   unsigned identity=(state>>8)&255;require(identity>=0xc1&&identity<=0xc6,"Unknown active RM; control access refused");
   if(identity==0xc5){require(ip->read_register(0x1000)&4,"CT convolution not idle");require(ip->read_register(0x2000)&4,"CT writer not idle");}
   require(ip->read_register(0)&4,"Algorithm not idle; isolation refused");
  }
  require(reader->read_register(0)&4,"Reader not idle");require(writer->read_register(0)&4,"Writer not idle");
  gpio->write_register(0,3);wait_status(15,13);
 }
 void select(const std::string& name){
  std::lock_guard<std::recursive_mutex> guard(operation_mutex);
  unsigned identity=name=="mc"?0xc1:name=="smooth"?0xc2:name=="edt"?0xc3:name=="route"?0xc4:name=="ct"?0xc5:name=="scope"?0xc6:0;require(identity,"Unknown RM");load_seconds=0;switch_seconds=0;
  if(current==name)return;
  auto total=Clock::now();quiesce();uint32_t count=gpio->read_register(8)>>16;auto address=sentinel->address();
  auto start=Clock::now();writefile("/sys/class/fpga_manager/fpga0/flags","1");writefile("/sys/class/fpga_manager/fpga0/firmware","medical_"+(name=="scope"?std::string("surface"):name)+"_partial.bin");load_seconds=seconds(start);
  require(readfile("/sys/class/fpga_manager/fpga0/state")=="operating\n","FPGA manager state");
  require((gpio->read_register(8)&15)==13&&gpio->read_register(8)>>16==count,"Static state lost");
  sentinel->sync(XCL_BO_SYNC_BO_FROM_DEVICE);
  // Bulk-copy the uncached BO before checking; preserve full-byte coverage.
  std::memcpy(snapshot.data(),sentinel->map<const void*>(),1048576);
  require(std::memcmp(snapshot.data(),expected.data(),1048576)==0,"DDR sentinel damaged");
  require(address==sentinel->address()&&boot==readfile("/proc/sys/kernel/random/boot_id"),"Context/boot changed");
  gpio->write_register(0,2);wait_status(0xff0f,identity<<8);require(ip->read_register(0)&4,"New RM not idle");
  current=name;++switches;switch_seconds=seconds(total);
  switch_log<<switches<<','<<name<<','<<load_seconds*1000<<','<<switch_seconds*1000<<','<<count<<','<<address<<'\n';switch_log.flush();
 }
 xrt::bo buffer(size_t bytes,xrt::bo::flags flags=xrt::bo::flags::normal){
  // This kernel allocates single-page coherent BOs in high DDR; multi-page
  // BOs use the low CMA pool. Keep the physical range check as the final gate.
  size_t page=size_t(sysconf(_SC_PAGESIZE));require(page>0&&page<=65536,"Invalid page size");
  size_t allocation=std::max(bytes,2*page);
  auto b=xrt::bo(*device,allocation,flags,0);
  require(b.address()+allocation<=0x80000000ULL,"BO outside mapped low DDR bank: "+std::to_string(b.address()));return b;
 }
 void pointer(unsigned offset,const xrt::bo& b){uint64_t a=b.address();require(a%64==0,"BO alignment");arg(offset,uint32_t(a));arg(offset+4,uint32_t(a>>32));}
 void arg(unsigned offset,uint32_t value){ip->write_register(offset,value);require(ip->read_register(offset)==value,"Argument readback mismatch");}
 double execute(double timeout){
  require(!(gpio->read_register(8)&1)&&(ip->read_register(0)&4),"RM not ready");
  std::signal(SIGINT,SIG_IGN);std::signal(SIGTERM,SIG_IGN);auto t=Clock::now();
  try {ip->write_register(0,1);while(!(ip->read_register(0)&2)){if(seconds(t)>timeout)retain("Completion timeout");std::this_thread::sleep_for(std::chrono::microseconds(100));}}
  catch(const std::exception& e){retain(e.what());}
  return seconds(t);
 }
 void echo(){
  require((current=="mc"||current=="smooth"||current=="ct")&&!(gpio->read_register(8)&1),"Select medical RM before stream test");
  if(!echo_output)echo_output=std::make_unique<xrt::bo>(buffer(1048576));
  for(auto entry:{std::make_pair(reader.get(),sentinel->address()),std::make_pair(writer.get(),echo_output->address())}){
   require(entry.first->read_register(0)&4,"DMA not idle");entry.first->write_register(0x10,uint32_t(entry.second));entry.first->write_register(0x14,uint32_t(entry.second>>32));entry.first->write_register(0x20,1048576/64);
  }
  unsigned count=gpio->read_register(8)>>16;auto t=Clock::now();
  try{
   writer->write_register(0,1);reader->write_register(0,1);bool rd=false,wd=false;
   while(!rd||!wd){if(!rd)rd=reader->read_register(0)&2;if(!wd)wd=writer->read_register(0)&2;if(seconds(t)>10)retain("Static DMA timeout");std::this_thread::sleep_for(std::chrono::microseconds(20));}
  }catch(const std::exception& e){retain(e.what());}
  require(writer->read_register(0x28)==0,"AXIS framing mismatch");wait_status(0xffff0000,((count+1)&65535)<<16);
  echo_output->sync(XCL_BO_SYNC_BO_FROM_DEVICE);
  std::memcpy(snapshot.data(),echo_output->map<const void*>(),1048576);
  require(std::memcmp(snapshot.data(),expected.data(),1048576)==0,"AXIS echo mismatch");
 }
 ~Session(){
  if(gpio&&reader&&writer){try{quiesce();}catch(...){}}
  echo_output.reset();sentinel.reset();writer.reset();reader.reset();device.reset();
  if(lock>=0)close(lock);
 }
};
}
