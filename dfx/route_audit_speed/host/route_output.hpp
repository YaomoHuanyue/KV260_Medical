#pragma once
#include <cstdint>
#include <cstring>
#include <stdexcept>

// DMA still writes the frozen 8706-word padded frame. Only CPU extraction
// skips its known zero padding; the public output remains fully initialized.
inline size_t route_output_words(const uint64_t header[8],unsigned operation){
 if(header[0])throw std::runtime_error("Route output header status");
 if(operation==0)return 1; // Scene upload acknowledgement; lane 1 is a token.
 if(header[1]>4096)throw std::runtime_error("Route output point count");
 if(operation==2){
  if(header[2]!=0x4155444954303031ULL)throw std::runtime_error("Audit output tag");
  return size_t(header[1])+1;
 }
 if(operation!=1||header[2]>4096)throw std::runtime_error("Route output ID count/operation");
 return 2+(size_t(header[2])+7)/8+2*size_t(header[1]);
}
inline size_t copy_route_output(void*destination,const void*source,size_t capacity_words,unsigned operation){
 if(!destination||!source||capacity_words!=8706)throw std::runtime_error("Route output capacity");
 uint64_t header[8];std::memcpy(header,source,64);
 size_t words=route_output_words(header,operation);
 if(words>capacity_words)throw std::runtime_error("Route output exceeds DMA capacity");
 std::memcpy(destination,source,words*64);
 std::memset(static_cast<unsigned char*>(destination)+words*64,0,(capacity_words-words)*64);
 return words;
}
