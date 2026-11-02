#include "../../ct_pl/stream_types.hpp"
#include <cstring>
#include <vector>
extern "C" void ct_writer_pool(Stream<P256>&,W256*,uint32_t,uint32_t&,const W256*,uint32_t,uint32_t,uint32_t,uint32_t,W256*,const W256*,uint32_t);

extern "C" int ct_native_pool(const W256* packets,W256* full,W256* pooled,
 const W256* parameters,const W256* lut,unsigned h,unsigned w,unsigned channels,uint32_t scale_bits,uint32_t zero){
 try{
  if(!packets||!full||!pooled||!parameters||!lut||h<2||h>512||w<2||w>512||(h&1)||(w&1)||channels<8||channels>64||(channels&(channels-1)))return -2;
  const unsigned count=h*w*(channels/8),full_words=(count+3)/4,pool_words=(count/4+3)/4;
  Stream<P256> sums;
  for(unsigned i=0;i<count;++i){P256 p;p.data=packets[i];p.keep=p.strb=0xffffffffu;p.last=i+1==count;sums.write(p);}
  P256 next;setlane(next.data,0,0x12345678);sums.write(next);
  std::vector<W256> actual(full_words+1),small(pool_words+1);
  for(auto* v:{&actual,&small})for(auto& p:*v)for(unsigned j=0;j<8;++j)setlane(p,j,int32_t(0xa5a5a5a5u));
  uint32_t status=99;
  ct_writer_pool(sums,actual.data(),count,status,parameters,3,channels,scale_bits,zero,small.data(),lut,(w<<16)|h);
  if(status)return int(status);
  if(lane(sums.read().data,0)!=0x12345678||!sums.empty())return -3;
  for(unsigned j=0;j<8;++j)if(uint32_t(lane(actual[full_words],j))!=0xa5a5a5a5u||uint32_t(lane(small[pool_words],j))!=0xa5a5a5a5u)return -4;
  std::memcpy(full,actual.data(),full_words*32);std::memcpy(pooled,small.data(),pool_words*32);return 0;
 }catch(...){return -1;}
}
