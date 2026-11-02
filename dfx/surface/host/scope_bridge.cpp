#include "runtime.hpp"
using namespace medical;
struct Scope {
 Session session;std::unique_ptr<xrt::bo> in,out;size_t in_cap=0,out_cap=0;
};
static thread_local std::string error;
extern "C" const char* scope_error(){return error.c_str();}
extern "C" void* scope_open(){try{return new Scope();}catch(const std::exception&e){error=e.what();return nullptr;}}
extern "C" void scope_close(void* p){delete static_cast<Scope*>(p);}
extern "C" int scope_transfer(void* handle,const void* source,void* destination,unsigned in_words,unsigned out_words,unsigned operation,double* hardware,double* total){try{
 auto begin=Clock::now();require(handle&&source&&destination&&in_words&&out_words,"Scope null/bounds");
 require((operation==0&&in_words==11777&&out_words==1)||(operation==1&&in_words==1&&out_words>=9&&out_words<=40961),"Surface transfer bounds");
 const auto* p=static_cast<const int32_t*>(source);
 if(operation==0){
  require(p[0]>=2&&p[0]<=256&&p[1]>=2&&p[1]<=192&&p[2]>=2&&p[2]<=128&&uint32_t(p[4])==0x53554632&&p[5]>=0&&p[5]<=4096,"Surface sparse scene header");
  for(int j=6;j<15;++j)require(p[j]>=-32767&&p[j]<=32767,"Surface normal matrix overflow");
  const auto* maps=reinterpret_cast<const uint16_t*>(p+16);
  for(unsigned i=0;i<3072*32;++i)require(maps[i]<=p[5],"Surface brick ID out of bounds");
 }else{
  require(p[0]>=16&&p[0]<=640&&p[0]%16==0&&p[1]>=4&&p[1]<=512&&p[2]>=1&&p[2]<=1023&&out_words==1+unsigned(p[0]*p[1])/8,"Surface frame header");
  for(int axis=0;axis<3;++axis)for(int corner=0;corner<4;++corner){
   int64_t horizontal=(corner&1)?int64_t(p[0]-1)*p[10+axis]:0;
   int64_t vertical=(corner&2)?int64_t(p[1]-1)*p[13+axis]:0;
   int64_t first=int64_t(p[7+axis])+horizontal,d=first+vertical;
   require(horizontal>=INT32_MIN&&horizontal<=INT32_MAX&&vertical>=INT32_MIN&&vertical<=INT32_MAX&&first>=INT32_MIN&&first<=INT32_MAX,"Surface ray setup integer overflow");
   int64_t end=int64_t(p[4+axis])+int64_t(p[2]+1)*d;
   require(d>=-33554431&&d<=33554431&&p[4+axis]>=INT32_MIN+65536&&p[4+axis]<=INT32_MAX-65536&&end>=INT32_MIN+65536&&end<=INT32_MAX-65536,"Surface ray integer overflow");
  }
 }
 auto& h=*static_cast<Scope*>(handle);auto& s=h.session;std::lock_guard<std::recursive_mutex> guard(s.operation_mutex);s.select("scope");
 size_t ib=size_t(in_words)*64,ob=size_t(out_words)*64;
 if(h.in_cap<ib){h.in=std::make_unique<xrt::bo>(s.buffer(ib));h.in_cap=ib;}
 if(h.out_cap<ob){h.out=std::make_unique<xrt::bo>(s.buffer(ob));h.out_cap=ob;}
 memcpy(h.in->map<void*>(),source,ib);h.in->sync(XCL_BO_SYNC_BO_TO_DEVICE,ib,0);
 for(auto pair:{std::make_pair(s.reader.get(),h.in->address()),std::make_pair(s.writer.get(),h.out->address())}){
  require(pair.first->read_register(0)&4,"Scope DMA not idle");pair.first->write_register(0x10,uint32_t(pair.second));pair.first->write_register(0x14,uint32_t(pair.second>>32));
 }
 s.reader->write_register(0x20,in_words);s.writer->write_register(0x20,out_words);
 s.arg(0x10,operation);s.arg(0x18,in_words);s.arg(0x20,out_words);require(s.ip->read_register(0)&4,"Scope core not idle");
 unsigned transactions=s.gpio->read_register(8)>>16;
 std::signal(SIGINT,SIG_IGN);std::signal(SIGTERM,SIG_IGN);auto start=Clock::now();
 try{
  s.writer->write_register(0,1);s.ip->write_register(0,1);s.reader->write_register(0,1);
  bool rd=false,wd=false,cd=false;
  while(!rd||!wd||!cd){if(!rd)rd=s.reader->read_register(0)&2;if(!wd)wd=s.writer->read_register(0)&2;if(!cd)cd=s.ip->read_register(0)&2;if(seconds(start)>10)retain("Scope AXIS completion timeout");if(!rd||!wd||!cd)std::this_thread::sleep_for(std::chrono::microseconds(20));}
 }catch(const std::exception&e){retain(e.what());}
 *hardware=seconds(start);require(s.writer->read_register(0x28)==0,"Scope AXIS framing (KEEP/STRB/USER/LAST)");s.wait_status(0xffff0000,((transactions+1)&65535)<<16);
 require(s.ip->read_register(0x28)==0,"Scope core reported invalid input");
 h.out->sync(XCL_BO_SYNC_BO_FROM_DEVICE,ob,0);memcpy(destination,h.out->map<const void*>(),ob);
 require(static_cast<const uint32_t*>(destination)[0]==0,"Scope acknowledgement");
 *total=seconds(begin);return 0;
}catch(const std::exception&e){error=e.what();return -1;}}
