#pragma once
#include "runtime.hpp"
#include <mutex>
namespace edtvolume8 {
// All adapters in this shared object retain the same device, static CUs and BO
// context. Callers serialize hardware work; CPU preprocessing may overlap it.
inline std::shared_ptr<Session> shared_session(){
 static std::mutex mutex;static std::weak_ptr<Session> previous;
 std::lock_guard<std::mutex> lock(mutex);auto result=previous.lock();
 if(!result){result=std::make_shared<Session>();previous=result;}return result;
}
struct RegisterView {
 Session& session;unsigned base;
 RegisterView(Session& s,unsigned b):session(s),base(b){}
 uint32_t read_register(unsigned offset){require(offset<4096,"Register offset");return session.ip->read_register(base+offset);}
 void write_register(unsigned offset,uint32_t value){require(offset<4096,"Register offset");session.ip->write_register(base+offset,value);}
};
struct Handle {
 std::shared_ptr<Session> session=shared_session();
 std::unique_ptr<xrt::bo> input,output;size_t in_capacity=0,out_capacity=0;
 bool output_cacheable=false;
 std::vector<uint64_t> scene;unsigned scene_generation=0;
};
}
