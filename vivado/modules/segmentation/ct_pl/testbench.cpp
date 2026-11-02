#include "stream_types.hpp"
#include <vector>
#include <iostream>
#include <random>
#include <stdexcept>
void test(unsigned h,unsigned w,unsigned ci,unsigned co,unsigned k){
 std::mt19937 gen(h*1000+w*10+ci+co+k);unsigned cg=(ci+7)/8,ig=(ci+3)/4,og=(co+7)/8;
 std::vector<int8_t> x(h*w*ci),weights(co*ci*k*k);
 for(auto&v:x)v=int8_t(gen()%256-128);for(auto&v:weights)v=int8_t(gen()%256-128);
 // RTL co-simulation wrappers snapshot the declared AXI depths, including the
 // unused tail of small test cases. Allocate those tails as real zeroed memory.
 std::vector<W256> input(1024+(h*w*cg+3)/4);std::vector<W256> packed(1152),output(1024+h*w*og);
 for(unsigned p=0;p<h*w;p++)for(unsigned c=0;c<ci;c++)setbyte(input[(p*cg*8+c)/32],(p*cg*8+c)%32,x[p*ci+c]);
 for(unsigned o=0;o<co;o++)for(unsigned c=0;c<ci;c++)for(unsigned y=0;y<k;y++)for(unsigned z=0;z<k;z++)setbyte(packed[((o/8*k+y)*k+z)*ig+c/4],o%8*4+c%4,weights[((o*ci+c)*k+y)*k+z]);
 Stream<P256> a;Stream<P256>b;uint32_t status=999,writer=999;std::vector<W256> parameters(16);
 ct_reader(input.data(),a,h,w,ci,k);ct_conv(packed.data(),a,b,h,w,ci,co,k,status);ct_writer(b,output.data(),h*w*og,writer,parameters.data());
 if(status||writer||!a.empty()||!b.empty())throw std::runtime_error("status/frame error");
 for(unsigned y=0;y<h;y++)for(unsigned z=0;z<w;z++)for(unsigned o=0;o<og*8;o++){
  int32_t expected=0;if(o<co)for(unsigned c=0;c<ci;c++)for(unsigned ky=0;ky<k;ky++)for(unsigned kx=0;kx<k;kx++){
   int iy=int(y+ky)-int(k/2),ix=int(z+kx)-int(k/2);
   if(iy>=0&&iy<int(h)&&ix>=0&&ix<int(w))expected+=int32_t(x[(iy*w+ix)*ci+c])*int32_t(weights[((o*ci+c)*k+ky)*k+kx]);
  }
  if(lane(output[(y*w+z)*og+o/8],o%8)!=expected)throw std::runtime_error("integer convolution mismatch");
 }
 std::cout<<"PASS "<<h<<"x"<<w<<" ci="<<ci<<" co="<<co<<" k="<<k<<std::endl;
}
int main(){try{
 test(3,5,5,3,3);test(2,4,8,16,1);
 test(3,5,16,8,3);test(3,5,32,32,3);test(3,5,64,64,3);
#ifdef CT_READER_TEST
 test(8,11,5,8,3);test(1,1,64,64,3);test(2,512,5,8,3);
#endif
#ifdef CT_NATIVE
 for(unsigned k:{1,3})for(unsigned ci:{1,5,8,16,32,64})for(unsigned co:{3,8,32,64})test(3,7,ci,co,k);
 for(unsigned k:{1,3})for(unsigned ci:{17,33,63})test(2,5,ci,13,k);
 test(1,1,64,64,3);test(2,512,5,8,3);
#endif
 return 0;}catch(const std::exception&e){std::cerr<<e.what()<<std::endl;return 1;}}
