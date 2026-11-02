#pragma once
#include <cstdint>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>

namespace quality_packet {
constexpr unsigned SCENE_WORDS=23041,DIR_WORDS=512,LEAF_WORDS=2048;
inline void require(bool condition,const char* reason){if(!condition)throw std::invalid_argument(reason);}
template<class T> inline T value(const uint8_t* bytes,size_t offset){T result;std::memcpy(&result,bytes+offset,sizeof(T));return result;}
// This entry point is also compiled and tested without XRT or /dev/mem.
inline void validate(const void* source,unsigned input_words,unsigned output_words,unsigned operation){
 require(source,"Null packet");const auto* bytes=static_cast<const uint8_t*>(source);
 require((operation==0&&input_words==SCENE_WORDS&&output_words==1)||
         (operation==1&&input_words==1&&output_words>=9&&output_words<=40961),"Packet length/operation");
 int32_t p[16];std::memcpy(p,bytes,sizeof(p));require(p[3]>=0,"Negative request token");
 if(operation==0){
  unsigned pages=uint32_t(p[15])&255,bits=(uint32_t(p[15])>>8)&255;
  require(p[0]>=2&&p[0]<=384&&p[1]>=2&&p[1]<=320&&p[2]>=2&&p[2]<=512&&
          uint32_t(p[4])==0x53514733&&p[5]>=0&&p[5]<=10240&&pages<=128&&
          (bits==5||bits==6)&&!(uint32_t(p[15])>>16),"Quality scene header");
  for(unsigned j=6;j<15;++j)require(p[j]>=-32767&&p[j]<=32767,"Normal matrix range");
  const size_t directory=64,leaves=directory+DIR_WORDS*64,field=leaves+LEAF_WORDS*64;
  for(unsigned word=0;word<DIR_WORDS;++word){
   uint64_t first=value<uint64_t>(bytes,directory+word*64);
   for(unsigned bank=0;bank<8;++bank){
    uint64_t copy=value<uint64_t>(bytes,directory+word*64+bank*8);
    require(copy==first,"Divergent directory banks");
    for(unsigned slot=0;slot<4;++slot)require(((copy>>(slot*16))&65535)<=pages,"Page ID range");
   }
  }
  for(size_t offset=leaves;offset<field;offset+=2)require(value<uint16_t>(bytes,offset)<=p[5],"Brick ID range");
  for(size_t offset=field;offset<size_t(SCENE_WORDS)*64;offset+=2){
   unsigned packed=value<uint16_t>(bytes,offset);int scalar=packed&8191;if(scalar&4096)scalar-=8192;
   require(!(packed&49152)&&scalar>=-(4<<bits)&&(!(packed&8192)||scalar>0),"Signed field/target/reserved bits");
  }
 }else{
  require(p[0]>=16&&p[0]<=640&&p[0]%16==0&&p[1]>=4&&p[1]<=512&&p[2]>=1&&p[2]<=1023&&
          output_words==1+unsigned(p[0]*p[1])/8,"Frame header/output size");
  for(unsigned axis=0;axis<3;++axis)for(unsigned corner=0;corner<4;++corner){
   int64_t horizontal=(corner&1)?int64_t(p[0]-1)*p[10+axis]:0;
   int64_t vertical=(corner&2)?int64_t(p[1]-1)*p[13+axis]:0;
   int64_t first=int64_t(p[7+axis])+horizontal,delta=first+vertical;
   require(horizontal>=INT32_MIN&&horizontal<=INT32_MAX&&vertical>=INT32_MIN&&vertical<=INT32_MAX&&
           first>=INT32_MIN&&first<=INT32_MAX,"Ray setup integer overflow");
   int64_t end=int64_t(p[4+axis])+int64_t(p[2]+1)*delta;
   require(delta>=-33554431&&delta<=33554431&&p[4+axis]>=INT32_MIN+65536&&p[4+axis]<=INT32_MAX-65536&&
           end>=INT32_MIN+65536&&end<=INT32_MAX-65536,"Ray/refinement integer overflow");
  }
 }
}
inline bool intact_guard(const uint8_t* data,size_t count){
 for(size_t index=0;index<count;++index)if(data[index]!=0xa5)return false;return true;
}
}
