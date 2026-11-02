#pragma once
#include <xrt/xrt_bo.h>
#include <csignal>
namespace medical {
struct Session;
inline std::function<void(Session&)> emulate;
inline unsigned starts=0,loads=0;
inline bool bad_shape_readback=false;
inline bool bad_reader_readback=false;
struct Session {
 std::recursive_mutex operation_mutex;
 std::array<uint32_t,12288/4> registers{};
 std::string current;
 Session(){registers[0]=registers[0x1000/4]=registers[0x2000/4]=4;}
 void select(const std::string& value){if(current!=value){current=value;++loads;}}
 xrt::bo buffer(size_t bytes,xrt::bo::flags){return xrt::bo(bytes);}
};
inline std::shared_ptr<Session> shared_session(){static std::weak_ptr<Session> previous;auto p=previous.lock();if(!p){p=std::make_shared<Session>();previous=p;}return p;}
struct RegisterView {
 Session& session;unsigned base;
 RegisterView(Session& s,unsigned b):session(s),base(b){}
 uint32_t read_register(unsigned offset){
  if(offset>=4096)throw std::runtime_error("Register bounds");
  auto& word=session.registers[(base+offset)/4];auto value=word;
  if(offset==0)word&=~2u;
  if(base==0x2000&&offset==0x80&&bad_shape_readback)return 0;
  if(base==0&&offset==0x60&&bad_reader_readback)return value^1;
  return value;
 }
 void write_register(unsigned offset,uint32_t value){
  if(offset>=4096)throw std::runtime_error("Register bounds");
  session.registers[(base+offset)/4]=value;
  if(base==0&&offset==0&&(value&1)){
   if(!(session.registers[0x1000/4]&1)||!(session.registers[0x2000/4]&1))throw std::runtime_error("Producer started before consumers");
   ++starts;if(!emulate)throw std::runtime_error("Missing HLS-C emulator");emulate(session);
   session.registers[0]=session.registers[0x1000/4]=session.registers[0x2000/4]=6;
  }
 }
};
[[noreturn]] inline void retain(const std::string& why){throw std::runtime_error("DMA allocations must be retained: "+why);}
}
