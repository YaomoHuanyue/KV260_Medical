#include "shared_session.hpp"
#include "route_output.hpp"
#include "route_readback.hpp"
#include <array>
#include <sys/resource.h>
using namespace edtvolume8;
static thread_local std::string error;
extern "C" const char* medical_error(){return error.c_str();}
extern "C" void* medical_open(){try{return new Handle();}catch(const std::exception& e){error=e.what();return nullptr;}}
extern "C" void medical_close(void* p){delete static_cast<Handle*>(p);}
extern "C" unsigned medical_switches(void* p){return static_cast<Handle*>(p)->session->switches;}
extern "C" int medical_select(void* p,const char* name){try{static_cast<Handle*>(p)->session->select(name);return 0;}catch(const std::exception& e){error=e.what();return -1;}}
extern "C" int medical_echo(void* p){try{auto& s=*static_cast<Handle*>(p)->session;std::lock_guard<std::recursive_mutex> guard(s.operation_mutex);s.echo();return 0;}catch(const std::exception& e){error=e.what();return -1;}}
extern "C" int medical_session_report(void* p,const char* path){try{
 auto& s=*static_cast<Handle*>(p)->session;struct rusage usage{};getrusage(RUSAGE_SELF,&usage);
 std::ofstream f(path);f<<"{\"partial_switches\":"<<s.switches<<",\"xrt_metadata_loads\":1,\"fixed_dma_cus\":2,\"peak_rss_kib\":"<<usage.ru_maxrss<<",\"boot_id\":\""<<s.boot.substr(0,s.boot.find('\n'))<<"\"}\n";require(bool(f),"Session report write");return 0;
}catch(const std::exception& e){error=e.what();return -1;}}

static double transfer(Handle& h,const void* src,void* dst,unsigned in_count,unsigned out_count,unsigned status_offset,unsigned route_copy=0){
 auto& s=*h.session;size_t ib=size_t(in_count)*64,ob=size_t(out_count)*64;
 require(ib&&ob&&ib<=640000000&&ob<=640000000,"AXIS transfer bounds");
 const auto readback=route_readback_plan(static_cast<const uint64_t*>(src),in_count,out_count,route_copy);
 require(readback.bytes&&readback.bytes<=ob,"CPU readback bounds");
 if(h.in_capacity<ib){h.input=std::make_unique<xrt::bo>(s.buffer(ib));h.in_capacity=ib;}
 const bool cacheable=route_copy!=0;
 if(h.out_capacity<ob||h.output_cacheable!=cacheable){
  h.output=std::make_unique<xrt::bo>(s.buffer(ob,cacheable?xrt::bo::flags::cacheable:xrt::bo::flags::normal));
  h.out_capacity=ob;h.output_cacheable=cacheable;
 }
 std::memcpy(h.input->map<void*>(),src,ib);h.input->sync(XCL_BO_SYNC_BO_TO_DEVICE,ib,0);
 for(auto item:{std::make_pair(s.reader.get(),h.input->address()),std::make_pair(s.writer.get(),h.output->address())}){
  require(item.first->read_register(0)&4,"Static DMA not idle");item.first->write_register(0x10,uint32_t(item.second));item.first->write_register(0x14,uint32_t(item.second>>32));
 }
 s.reader->write_register(0x20,in_count);s.writer->write_register(0x20,out_count);
 require(s.ip->read_register(0)&4,"Navigation core not idle");
 unsigned transactions=s.gpio->read_register(8)>>16;
 std::signal(SIGINT,SIG_IGN);std::signal(SIGTERM,SIG_IGN);
 auto start=Clock::now();
 try{
  s.writer->write_register(0,1);s.ip->write_register(0,1);s.reader->write_register(0,1);
  bool rd=false,wd=false,cd=false;
  while(!rd||!wd||!cd){
   if(!rd)rd=s.reader->read_register(0)&2;if(!wd)wd=s.writer->read_register(0)&2;if(!cd)cd=s.ip->read_register(0)&2;
   if(seconds(start)>60)retain("Navigation completion timeout");
   if(!rd||!wd||!cd)std::this_thread::sleep_for(std::chrono::microseconds(20));
  }
 }catch(const std::exception& e){retain(e.what());}
 double elapsed=seconds(start);
 require(s.writer->read_register(0x28)==0,"Navigation output framing");
 s.wait_status(0xffff0000,((transactions+1)&65535)<<16);
 require(s.ip->read_register(status_offset)==0,"Navigation core status");
 h.output->sync(XCL_BO_SYNC_BO_FROM_DEVICE,readback.bytes,0);
 validate_route_readback(readback,h.output->map<const uint64_t*>());
 if(route_copy)copy_route_output(dst,h.output->map<void*>(),out_count,route_copy-1);
 else std::memcpy(dst,h.output->map<void*>(),ob);
 return elapsed;
}

extern "C" int medical_edt(void* handle,const void* source,void* destination,unsigned length,unsigned groups,unsigned weight,unsigned mode,double* hardware,double* host){
 try{
  require(handle&&source&&destination&&length&&length<=1024&&groups&&groups<=131072&&weight&&mode<=1,"EDT job bounds");
  auto start=Clock::now();auto& h=*static_cast<Handle*>(handle);auto& s=*h.session;std::lock_guard<std::recursive_mutex> guard(s.operation_mutex);s.select("edt");
  s.arg(0x10,length);s.arg(0x18,groups);s.arg(0x20,weight);s.arg(0x28,mode);
  *hardware=transfer(h,source,destination,length*groups,length*groups,0x30);*host=seconds(start);return 0;
 }catch(const std::exception& e){error=e.what();return -1;}
}

static double route(Handle& h,const uint64_t* src,uint64_t* dst,unsigned count,unsigned operation){
 auto& s=*h.session;s.select("route");s.arg(0x10,operation);s.arg(0x18,count);s.arg(0x20,operation?8706:1);
 return transfer(h,src,dst,count,8706,0x28,operation+1);
}
extern "C" int medical_route(void* handle,const uint64_t* source,uint64_t* destination,unsigned count,unsigned operation,double* hardware,double* host,unsigned* reloaded){
 try{
  require(handle&&source&&destination&&count&&count<=131072&&operation<=2&&(operation!=0||count>=4),"Route job bounds");
  auto start=Clock::now();auto& h=*static_cast<Handle*>(handle);auto& s=*h.session;std::lock_guard<std::recursive_mutex> guard(s.operation_mutex);*reloaded=0;*hardware=0;
  if(operation==1){
   require(!h.scene.empty(),"Upload scene before route query");
   if(s.current!="route"||h.scene_generation!=s.switches){
    std::vector<uint64_t> ack(8706*8);*hardware+=route(h,h.scene.data(),ack.data(),h.scene.size()/8,0);
    require(ack[0]==0&&ack[1]==h.scene[3*8+7],"Scene reload token");h.scene_generation=s.switches;*reloaded=1;
   }
  }
  *hardware+=route(h,source,destination,count,operation);
  if(operation==0){require(destination[0]==0&&destination[1]==source[3*8+7],"Scene token");h.scene.assign(source,source+size_t(count)*8);h.scene_generation=s.switches;}
  *host=seconds(start);return 0;
 }catch(const std::exception& e){error=e.what();return -1;}
}
