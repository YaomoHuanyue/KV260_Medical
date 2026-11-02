#include "stream_types.hpp"
#include <vector>
#include <random>
#include <iostream>
#include <cmath>
#include <algorithm>
#include <stdexcept>
uint32_t bits(float f){union{float f;uint32_t u;}x;x.f=f;return x.u;}
void check(unsigned count,unsigned channels,unsigned mode,int zero){
 std::mt19937 rng(count*17+channels);Stream<P256> sums;
 std::vector<W256> params(24),output(1024+count),packets(count);
 unsigned padded=((channels+7)/8)*8;std::vector<int32_t> bias(padded);std::vector<float> scale(padded);
 for(unsigned c=0;c<padded;c++){
  bias[c]=int(rng()%61)-30;scale[c]=(c%3==0?0.5f:(c%3==1?0.003731f:0.041923f));
  setlane(params[c/4],(c%4)*2,bias[c]);setlane(params[c/4],(c%4)*2+1,int32_t(bits(scale[c])));
 }
 for(unsigned i=0;i<count;i++){
  P256 p;
  for(unsigned j=0;j<8;j++)setlane(p.data,j,count<5?int32_t(int(j)-4):int32_t(int(rng()%100001)-50000));
  p.keep=0xffffffffu;p.strb=0xffffffffu;p.last=i+1==count;packets[i]=p.data;sums.write(p);
 }
 uint32_t status=99;float qscale=count<5?1.f:0.125736f;
 ct_writer(sums,output.data(),count,status,params.data(),mode,channels,bits(qscale),uint32_t(zero));
 if(status||!sums.empty())throw std::runtime_error("status/stream failure");
 for(unsigned i=0;i<count;i++)for(unsigned j=0;j<8;j++){
  if(mode==0){if(lane(output[i],j)!=lane(packets[i],j))throw std::runtime_error("raw mismatch");}
  else{
   unsigned c=(i%(padded/8))*8+j;
   int32_t acc=lane(packets[i],j)+bias[c];float f=float(acc)*scale[c];f=f/qscale;
   int expected=int(std::max(-128.f,std::min(127.f,std::nearbyintf(f)+float(zero))));
   if(int(byte256(output[i/4],(i%4)*8+j))!=expected)throw std::runtime_error("quantized mismatch");
  }
 }
 if(mode==1)for(unsigned i=count*8;i<((count+3)/4)*32;i++)if(byte256(output[i/32],i%32)!=0)throw std::runtime_error("tail padding mismatch");
 std::cout<<"PASS writer count="<<count<<" channels="<<channels<<" mode="<<mode<<" zero="<<zero<<std::endl;
}
static void check_real(const uint32_t* params,const uint32_t* acc,const int* expected,unsigned count,unsigned channels,uint32_t scale,int zero){
 Stream<P256> sums;std::vector<W256> parameters(24),output(1024+count);
 unsigned padded=((channels+7)/8)*8;
 for(unsigned i=0;i<padded*2;i++)setlane(parameters[i/8],i%8,int32_t(params[i]));
 for(unsigned i=0;i<count;i++){P256 p;for(unsigned j=0;j<8;j++)setlane(p.data,j,int32_t(acc[i*8+j]));p.keep=0xffffffffu;p.strb=0xffffffffu;p.last=i+1==count;sums.write(p);}
 uint32_t status=99;ct_writer(sums,output.data(),count,status,parameters.data(),1,channels,scale,uint32_t(zero));
 if(status||!sums.empty())throw std::runtime_error("real vector status");
 for(unsigned i=0;i<count*8;i++)if(int(byte256(output[i/32],i%32))!=expected[i])throw std::runtime_error("real model quantization mismatch");
 std::cout<<"PASS real writer count="<<count<<" channels="<<channels<<std::endl;
}
#include "build/writer_real_vectors.hpp"
int main(){try{
 check(3,8,0,0);check(1,3,1,0);check(2,13,1,-7);check(3,8,1,127);check(4,16,1,-128);
 check(11,8,1,0);check(64,64,1,0);check(1024,16,1,-3);check(5,8,0,0);
 real_vectors();
#ifdef CT_NATIVE
 for(unsigned c:{1,3,8,13,16,32,64})for(unsigned n:{1,3,5,33,77})for(int z:{-128,-7,0,127})check(n,c,1,z);
#endif
 return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<std::endl;return 1;}}
