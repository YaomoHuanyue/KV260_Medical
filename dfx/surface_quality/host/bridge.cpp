#include "runtime.hpp"
#include "packet_validator.hpp"
#include <array>
namespace {
using namespace quality9;
constexpr size_t GUARD=4096;
struct Quality {
 Session session;
 std::unique_ptr<xrt::bo> input,output;size_t input_capacity=0,output_capacity=0;
 bool loaded=false;uint32_t scene_token=0;double phases[7]{};
 void allocate(size_t in_bytes,size_t out_bytes){
  if(input_capacity<in_bytes+2*GUARD){input=std::make_unique<xrt::bo>(session.buffer(in_bytes+2*GUARD,xrt::bo::flags::cacheable));input_capacity=in_bytes+2*GUARD;}
  if(output_capacity<out_bytes+2*GUARD){output=std::make_unique<xrt::bo>(session.buffer(out_bytes+2*GUARD,xrt::bo::flags::cacheable));output_capacity=out_bytes+2*GUARD;}
 }
};
thread_local std::string error;
void dma_arg(xrt::ip& dma,unsigned offset,uint32_t v){dma.write_register(offset,v);require(dma.read_register(offset)==v,"Static DMA argument readback");}
}
extern "C" const char* quality_error(){return error.c_str();}
extern "C" void* quality_open(){try{return new Quality;}catch(const std::exception& e){error=e.what();return nullptr;}}
extern "C" void quality_close(void* handle){delete static_cast<Quality*>(handle);}
extern "C" double quality_phase(void* handle,unsigned index){return handle&&index<7?static_cast<Quality*>(handle)->phases[index]:-1;}
extern "C" int quality_transfer(void* handle,const void* source,void* destination,unsigned in_words,unsigned out_words,
 unsigned operation,double* hardware,double* total){
 try{
  auto begin=Clock::now(),phase=begin;require(handle&&destination&&hardware&&total,"Null quality transfer");
  quality_packet::validate(source,in_words,out_words,operation);
  auto& h=*static_cast<Quality*>(handle);auto& s=h.session;
  std::lock_guard<std::recursive_mutex> lock(s.operation_mutex);h.phases[0]=seconds(phase);
  require(operation==0||h.loaded,"No scene loaded in this context");
  int32_t request[16];std::memcpy(request,source,sizeof(request));
  size_t ib=size_t(in_words)*64,ob=size_t(out_words)*64;phase=Clock::now();h.allocate(ib,ob);
  auto input=h.input->map<uint8_t*>();auto output=h.output->map<uint8_t*>();
  std::memset(input,0xa5,GUARD);std::memset(input+GUARD+ib,0xa5,GUARD);std::memcpy(input+GUARD,source,ib);
  std::memset(output,0xa5,GUARD);std::memset(output+GUARD,0xcd,ob);std::memset(output+GUARD+ob,0xa5,GUARD);
  h.phases[1]=seconds(phase);phase=Clock::now();
  h.input->sync(XCL_BO_SYNC_BO_TO_DEVICE,ib+2*GUARD,0);h.output->sync(XCL_BO_SYNC_BO_TO_DEVICE,ob+2*GUARD,0);
  h.phases[2]=seconds(phase);phase=Clock::now();s.select("quality");h.phases[3]=seconds(phase);
  require(!(s.gpio->read_register(8)&1)&&(s.ip->read_register(0)&4),"Quality RM not ready");
  for(auto entry:{std::make_pair(s.reader.get(),h.input->address()+GUARD),std::make_pair(s.writer.get(),h.output->address()+GUARD)}){
   require((entry.second&63)==0&&(entry.first->read_register(0)&4),"Static DMA not idle/aligned");
   dma_arg(*entry.first,0x10,uint32_t(entry.second));dma_arg(*entry.first,0x14,uint32_t(entry.second>>32));
  }
  dma_arg(*s.reader,0x20,in_words);dma_arg(*s.writer,0x20,out_words);
  s.arg(0x10,operation);s.arg(0x18,in_words);s.arg(0x20,out_words);
  if(operation==0)h.loaded=false;
  unsigned transactions=s.gpio->read_register(8)>>16;SignalGuard active_dma;
  auto start=Clock::now();
  try{
   s.writer->write_register(0,1);s.ip->write_register(0,1);s.reader->write_register(0,1);
   bool rd=false,wd=false,cd=false;
   while(!rd||!wd||!cd){
    if(!rd)rd=s.reader->read_register(0)&2;if(!wd)wd=s.writer->read_register(0)&2;if(!cd)cd=s.ip->read_register(0)&2;
    if(seconds(start)>20)retain("Quality AXIS completion timeout");
    if(!rd||!wd||!cd)std::this_thread::sleep_for(std::chrono::microseconds(20));
   }
  }catch(const std::exception& e){retain(e.what());}
  *hardware=seconds(start);h.phases[4]=*hardware;
  require(s.writer->read_register(0x28)==0,"Quality AXIS KEEP/STRB/USER/LAST");
  s.wait_status(0xffff0000,((transactions+1)&65535)<<16);
  require(s.ip->read_register(0x28)==0,"Quality core status");
  phase=Clock::now();h.input->sync(XCL_BO_SYNC_BO_FROM_DEVICE,ib+2*GUARD,0);h.output->sync(XCL_BO_SYNC_BO_FROM_DEVICE,ob+2*GUARD,0);
  h.phases[5]=seconds(phase);phase=Clock::now();
  for(auto entry:{std::make_pair(input,ib),std::make_pair(output,ob)}){
   require(quality_packet::intact_guard(entry.first,GUARD)&&quality_packet::intact_guard(entry.first+GUARD+entry.second,GUARD),"Quality DMA guard damaged");
  }
  require(std::memcmp(input+GUARD,source,ib)==0,"Quality input altered by DMA");
  uint32_t ack[16];std::memcpy(ack,output+GUARD,sizeof(ack));
  uint32_t expected_scene=operation==0?uint32_t(request[3]):h.scene_token;
  require(ack[0]==0&&ack[1]==uint32_t(request[3])&&ack[2]==expected_scene,"Quality acknowledgement/token mismatch");
  for(unsigned j=3;j<16;++j)require(ack[j]==0,"Quality acknowledgement reserved bits");
  std::memcpy(destination,output+GUARD,ob);h.phases[6]=seconds(phase);
  if(operation==0){h.scene_token=ack[2];h.loaded=true;}
  *total=seconds(begin);return 0;
 }catch(const std::exception& e){error=e.what();return 1;}
}
extern "C" int quality_return_to_scope(void* handle){
 try{
  require(handle,"Null quality context");auto& h=*static_cast<Quality*>(handle);auto& s=h.session;
  std::lock_guard<std::recursive_mutex> lock(s.operation_mutex);h.loaded=false;
  s.select("mc");s.echo();s.select("scope");return 0;
 }catch(const std::exception& e){error=e.what();return 1;}
}
