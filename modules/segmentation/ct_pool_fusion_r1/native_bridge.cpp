#define CT_NATIVE
#include "writer_pool.cpp"
#include <cstring>
#include <stdexcept>
#include <vector>

extern "C" int pool_stream_native(const uint64_t* words,unsigned count,unsigned h,unsigned w,unsigned c,
 const uint8_t* lut,uint64_t* full,uint64_t* pooled,uint32_t* summary){
 try{
  if(!lut||!full||!pooled||!summary||count>ct_pool_fusion::max_words||(!words&&count))return -2;
  W256 table[8]{};for(unsigned i=0;i<256;++i)setbyte(table[i/32],i%32,int8_t(lut[i]));
  Stream<W64> input,original,small;
  for(unsigned i=0;i<count;++i)input.write(words[i]);
  constexpr uint64_t next=0x1234FEDC9876ABCDULL;input.write(next);
  uint32_t status=0;ct_pool_fusion::forward_pool(input,original,small,table,count,h,w,c,status);
  unsigned a=0,b=0;
  while(!original.empty()){if(a>=count)return -3;full[a++]=original.read();}
  while(!small.empty()){if(b>=(count+3)/4)return -4;pooled[b++]=small.read();}
  if(input.read()!=next||!input.empty())return -5;
  summary[0]=status;summary[1]=a;summary[2]=b;summary[3]=1;return 0;
 }catch(...){return -1;}
}

extern "C" int pool_writer_native(const int32_t* accumulators,unsigned count,unsigned h,unsigned w,unsigned c,
 const int32_t* bias,const float* scales,float qscale,int zero,const uint8_t* lut,unsigned mode,unsigned fault,
 uint8_t* full,uint8_t* pooled,uint32_t* summary){
 try{
  if(!accumulators||!bias||!scales||!lut||!full||!pooled||!summary||!c||c>64||count>ct_pool_fusion::max_words||mode>3)return -2;
  const unsigned groups=(c+7)/8;
  std::vector<W256> parameters(groups*2+8);
  for(unsigned channel=0;channel<groups*8;++channel){
   const unsigned block=channel/4,part=channel%4;uint32_t scale=0;
   const float value=channel<c?scales[channel]:0;std::memcpy(&scale,&value,4);
   setlane(parameters[block],2*part,channel<c?bias[channel]:0);setlane(parameters[block],2*part+1,int32_t(scale));
  }
  W256 table[8]{};
  for(unsigned i=0;i<256;++i){
   setbyte(table[i/32],i%32,int8_t(lut[i]));
   setbyte(parameters[groups*2+i/32],i%32,int8_t(lut[i]));
  }
  Stream<P256> input,reference;
  for(unsigned i=0;i<count;++i){
   P256 packet;for(unsigned lane=0;lane<8;++lane)setlane(packet.data,lane,accumulators[i*8+lane]);
   packet.keep=packet.strb=0xffffffffu;packet.last=(i+1==count);
   if(i==0&&fault&1)packet.keep^=1;
   if(i+1==count&&fault&2)packet.strb^=0x80000000u;
   if(i==0&&fault&4)packet.last=!packet.last;
   input.write(packet);reference.write(packet);
  }
  P256 next;setlane(next.data,0,0x12345678);input.write(next);reference.write(next);
  const unsigned full_words=mode==0?count:(count+3)/4;
  const unsigned pool_words=mode==3&&ct_pool_fusion::valid(count,h,w,c)?((count/4)+3)/4:0;
  std::vector<W256> actual(full_words+1),baseline(full_words+1),small(pool_words+1);
  for(auto* target:{&actual,&baseline,&small})for(auto& word:*target)for(unsigned j=0;j<8;++j)setlane(word,j,int32_t(0xA5A5A5A5u));
  uint32_t scale_bits=0;std::memcpy(&scale_bits,&qscale,4);uint32_t status=0,old_status=0;
  ct_writer_pool(input,actual.data(),count,status,parameters.data(),mode,c,scale_bits,uint32_t(zero),
      small.data(),table,(w<<16)|h);
  ct_writer(reference,baseline.data(),count,old_status,parameters.data(),mode==3?1:mode,c,scale_bits,uint32_t(zero));
  if(std::memcmp(actual.data(),baseline.data(),full_words*sizeof(W256)))return -6;
  const unsigned expected_status=old_status|(mode==3&&!ct_pool_fusion::valid(count,h,w,c)?4:0);
  if(status!=expected_status)return -7;
  for(auto* word:{&actual[full_words],&small[pool_words]})for(unsigned j=0;j<8;++j)if(uint32_t(lane(*word,j))!=0xA5A5A5A5u)return -8;
  if(lane(input.read().data,0)!=0x12345678||!input.empty()||lane(reference.read().data,0)!=0x12345678||!reference.empty())return -9;
  std::memcpy(full,actual.data(),full_words*sizeof(W256));std::memcpy(pooled,small.data(),pool_words*sizeof(W256));
  summary[0]=status;summary[1]=full_words*32;summary[2]=pool_words*32;summary[3]=1;return 0;
 }catch(...){return -1;}
}
