#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>
enum {XCL_BO_SYNC_BO_TO_DEVICE=0,XCL_BO_SYNC_BO_FROM_DEVICE=1};
namespace mock {
inline unsigned blocks_alive=0;
inline uint64_t next_address=0x1234000000ULL;
struct Block {
 uint64_t address;std::vector<uint8_t> cpu,device;bool dirty=true;
 explicit Block(size_t bytes):address(next_address),cpu(bytes,0xa5),device(bytes,0x5a){next_address+=(bytes+4095)&~size_t(4095);++blocks_alive;}
 ~Block(){--blocks_alive;}
};
inline std::map<uint64_t,std::weak_ptr<Block>> regions;
inline std::shared_ptr<Block> find(uint64_t address){auto p=regions.at(address).lock();if(!p)throw std::runtime_error("DMA uses a freed buffer");return p;}
}
namespace xrt {
class device {};
class bo {
 std::shared_ptr<mock::Block> block;
 public:
 enum class flags {cacheable,normal};
 explicit bo(size_t n):block(std::make_shared<mock::Block>(n)){mock::regions[block->address]=block;}
 template<class T>T map(){return reinterpret_cast<T>(block->cpu.data());}
 size_t size()const{return block->cpu.size();}
 uint64_t address()const{return block->address;}
 void sync(int direction,size_t bytes=0,size_t offset=0){
  if(!bytes)bytes=size();if(offset+bytes>size())throw std::runtime_error("BO sync out of bounds");
  if(direction==XCL_BO_SYNC_BO_TO_DEVICE){std::memcpy(block->device.data()+offset,block->cpu.data()+offset,bytes);block->dirty=false;}
  else if(direction==XCL_BO_SYNC_BO_FROM_DEVICE){
   // Model a delayed dirty CPU eviction overwriting DMA output. The host must
   // flush recycled dirty output before start, then invalidate both outputs.
   if(block->dirty)std::memcpy(block->device.data(),block->cpu.data(),size());
   std::memcpy(block->cpu.data()+offset,block->device.data()+offset,bytes);block->dirty=false;
  }else throw std::runtime_error("Unknown BO sync direction");
 }
};
}
