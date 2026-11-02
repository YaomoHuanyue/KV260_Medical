#include "kernel.hpp"
#include <exception>
extern "C" int tensor_reader_native(const W256* input,const W256* skip,const W256* tables,
 W256* data,uint32_t* keep,uint32_t* strb,uint8_t* last,uint32_t capacity,uint32_t* count,uint32_t* status,
 uint32_t h,uint32_t w,uint32_t ci,uint32_t k,uint32_t mode,uint32_t ca,uint32_t cb,uint32_t fa,uint32_t fb){
 try{
  Stream<P256> pixels;*count=0;
  ct_tensor_reader(input,pixels,h,w,ci,k,skip,tables,mode,ca,cb,fa,fb,*status);
  while(!pixels.empty()){
   if(*count>=capacity)return -2;
   auto p=pixels.read();unsigned i=(*count)++;data[i]=p.data;keep[i]=p.keep;strb[i]=p.strb;last[i]=p.last;
  }
  return 0;
 }catch(const std::exception&){return -1;}
}
