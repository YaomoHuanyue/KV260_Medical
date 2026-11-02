#include "stream_types.hpp"
#include <vector>
extern "C" int ct_native(const W64* input,const W256* weights,W256* output,unsigned h,unsigned w,unsigned ci,unsigned co,unsigned k){
 try{unsigned n=h*w*((ci+7)/8);std::vector<W256> wide((n+3)/4);
  for(unsigned i=0;i<n;i++)setword64(wide[i/4],i%4,input[i]);
  Stream<P256>a;Stream<P256>b;uint32_t status=99,writer=99;
  ct_reader(wide.data(),a,h,w,ci,k);ct_conv(weights,a,b,h,w,ci,co,k,status);ct_writer(b,output,h*w*((co+7)/8),writer);
  return status||writer||!a.empty()||!b.empty();
 }catch(...){return -1;}
}
extern "C" int ct_native_quant(const W256* packets,W256* output,const W256* parameters,unsigned count,unsigned channels,uint32_t scale_bits,uint32_t zero){
 try{Stream<P256> sums;for(unsigned i=0;i<count;i++){P256 p;p.data=packets[i];p.keep=0xffffffffu;p.strb=0xffffffffu;p.last=i+1==count;sums.write(p);}
  uint32_t status=99;ct_writer(sums,output,count,status,parameters,1,channels,scale_bits,zero);return status||!sums.empty();
 }catch(...){return -1;}
}
extern "C" int ct_native_fused(const W256* packets,W256* output,const W256* parameters,unsigned count,unsigned channels,uint32_t scale_bits,uint32_t zero){
 try{Stream<P256> sums;for(unsigned i=0;i<count;i++){P256 p;p.data=packets[i];p.keep=0xffffffffu;p.strb=0xffffffffu;p.last=i+1==count;sums.write(p);}
  uint32_t status=99;ct_writer(sums,output,count,status,parameters,2,channels,scale_bits,zero);return status||!sums.empty();
 }catch(...){return -1;}
}
