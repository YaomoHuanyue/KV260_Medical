#include "shared_session.hpp"
#include "dma_guard.hpp"
#include <array>
namespace {
using namespace edtvolume8;
constexpr size_t GUARD=4096;
thread_local std::string error;
struct VolumeHandle {
 std::shared_ptr<Session> session=shared_session();
 std::array<std::unique_ptr<xrt::bo>,4> bo;
 std::array<size_t,4> capacities{};
 double phases[5]{};
 void allocate(unsigned id,size_t payload){
  if(!bo[id]||capacities[id]<payload+GUARD){
   bo[id]=std::make_unique<xrt::bo>(session->buffer(payload+GUARD,id==0||id==3?xrt::bo::flags::cacheable:xrt::bo::flags::normal));
   capacities[id]=payload+GUARD;
  }
 }
};
}
extern "C" const char*volume_error(){return error.c_str();}
extern "C" void*volume_open(){try{return new VolumeHandle;}catch(const std::exception&e){error=e.what();return nullptr;}}
extern "C" void volume_close(void*raw){delete static_cast<VolumeHandle*>(raw);}
extern "C" double volume_phase(void*raw,unsigned id){return raw&&id<5?static_cast<VolumeHandle*>(raw)->phases[id]:-1;}
extern "C" int volume_same_context(void*volume,void*audit){
 return volume&&audit&&static_cast<VolumeHandle*>(volume)->session.get()==static_cast<edtvolume8::Handle*>(audit)->session.get();
}
extern "C" int volume_run(void*raw,const uint8_t*mask,float*distance,uint64_t*debug_squared,
 unsigned nz,unsigned ny,unsigned nx,uint32_t wz,uint32_t wy,uint32_t wx,double*hardware,double*total){
 try{
  require(raw&&mask&&distance&&hardware&&total&&nz&&ny&&nx&&nz<=1024&&ny<=1024&&nx<=1024&&uint64_t(nz)*ny*nx<=80000000&&wz&&wy&&wx,"Invalid volume job");
  auto&h=*static_cast<VolumeHandle*>(raw);auto&s=*h.session;std::lock_guard<std::recursive_mutex> lock(s.operation_mutex);
  auto begin=Clock::now();unsigned mask_pitch=(nx+63)/64*64,cost_pitch=(nx+7)/8*8,float_pitch=(nx+15)/16*16;
  size_t rows=size_t(nz)*ny;std::array<size_t,4> bytes={rows*mask_pitch,rows*cost_pitch*8,rows*cost_pitch*8,rows*float_pitch*4};
  for(unsigned id=0;id<4;++id)h.allocate(id,bytes[id]);
  auto source=h.bo[0]->map<uint8_t*>();auto phase=Clock::now();std::memset(source,0,bytes[0]);
  for(size_t row=0;row<rows;++row)std::memcpy(source+row*mask_pitch,mask+row*nx,nx);
  for(unsigned id=0;id<4;++id){
   std::memset(h.bo[id]->map<uint8_t*>()+bytes[id],0xa5,GUARD);
   if(id!=0)h.bo[id]->sync(XCL_BO_SYNC_BO_TO_DEVICE,GUARD,bytes[id]);
  }
  h.phases[0]=seconds(phase);phase=Clock::now();h.bo[0]->sync(XCL_BO_SYNC_BO_TO_DEVICE,bytes[0]+GUARD,0);
  h.phases[1]=seconds(phase);s.select("volume");
  unsigned counters=s.gpio->read_register(8)>>16;
  for(unsigned id=0;id<4;++id)s.pointer(0x10+id*12,*h.bo[id]);
  for(auto item:{std::make_pair(0x40u,nz),std::make_pair(0x48u,ny),std::make_pair(0x50u,nx),std::make_pair(0x58u,wz),std::make_pair(0x60u,wy),std::make_pair(0x68u,wx)})s.arg(item.first,item.second);
  *hardware=s.execute(120);h.phases[2]=*hardware;
  require(s.ip->read_register(0x70)==0,"Volume algorithm status failure");
  require((s.gpio->read_register(8)>>16)==counters,"Static transaction counter changed during volume compute");
  phase=Clock::now();h.bo[3]->sync(XCL_BO_SYNC_BO_FROM_DEVICE,bytes[3]+GUARD,0);
  for(unsigned id=0;id<3;++id)h.bo[id]->sync(XCL_BO_SYNC_BO_FROM_DEVICE,GUARD,bytes[id]);
  if(debug_squared)h.bo[1]->sync(XCL_BO_SYNC_BO_FROM_DEVICE,bytes[1],0);
  h.phases[3]=seconds(phase);phase=Clock::now();
  for(unsigned id=0;id<4;++id){auto guard=h.bo[id]->map<const uint8_t*>()+bytes[id];require(intact_dma_guard(guard,GUARD),"Volume DMA guard damaged");}
  auto field=h.bo[3]->map<const float*>();
  for(size_t row=0;row<rows;++row)std::memcpy(distance+row*nx,field+row*float_pitch,nx*4);
  if(debug_squared){auto values=h.bo[1]->map<const uint64_t*>();for(size_t row=0;row<rows;++row)std::memcpy(debug_squared+row*nx,values+row*cost_pitch,nx*8);}
  h.phases[4]=seconds(phase);*total=seconds(begin);return 0;
 }catch(const std::exception&e){error=e.what();return 1;}
}
extern "C" int volume_return_to_scope(void*raw){
 try{require(raw,"Invalid handle");auto&s=*static_cast<VolumeHandle*>(raw)->session;s.select("mc");s.echo();s.select("scope");return 0;}
 catch(const std::exception&e){error=e.what();return 1;}
}
