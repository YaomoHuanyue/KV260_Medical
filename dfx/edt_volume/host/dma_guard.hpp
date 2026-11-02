#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace edtvolume8 {
// Check every guard byte without constructing an error string per byte.
// memcpy permits unaligned pointers and does not read beyond the given range.
inline bool intact_dma_guard(const uint8_t* data,size_t length){
 if(!data)return length==0;
 constexpr uint64_t expected=0xa5a5a5a5a5a5a5a5ULL;
 uint64_t difference=0;size_t i=0;
 for(;length-i>=sizeof(uint64_t);i+=sizeof(uint64_t)){
  uint64_t word;std::memcpy(&word,data+i,sizeof(word));difference|=word^expected;
 }
 for(;i<length;++i)difference|=uint64_t(data[i]^0xa5u);
 return difference==0;
}
}
