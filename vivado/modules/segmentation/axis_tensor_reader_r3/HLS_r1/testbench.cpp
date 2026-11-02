// Test-only software. No test interfaces, generators or checks enter the PL top.
#include "../kernel.hpp"
#include "test_model_tables.hpp"
#include <array>
#include <cstdio>
#include <stdexcept>
#include <vector>

struct Case { unsigned h,w,ca,cb,fa,fb,k,mode,ci; bool invalid; };
static unsigned number=0,valid=0,invalid=0;
static unsigned pattern(unsigned branch,unsigned y,unsigned x,unsigned c,unsigned seed){
 unsigned v=(y*1103515245u)^(x*2654435761u)^(c*2246822519u)^(seed*3266489917u)^(branch*668265263u);
 v^=v>>15;v*=2246822519u;v^=v>>13;return (v^(v>>16))&255u;
}
static std::vector<W256> source(unsigned h,unsigned w,unsigned channels,unsigned branch,unsigned seed){
 unsigned groups=(channels+7)/8;
 std::vector<W256> result((h*w*groups+3)/4+2);
 for(auto& word:result)for(unsigned j=0;j<32;j++)setbyte(word,j,0);
 for(unsigned j=0;j<32;j++){setbyte(result.front(),j,int8_t(0xa7));setbyte(result.back(),j,int8_t(0x5b));}
 for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++)for(unsigned c=0;c<channels;c++){
  unsigned i=(y*w+x)*groups*8+c;setbyte(result[1+i/32],i%32,int8_t(pattern(branch,y,x,c,seed)));
 }
 return result;
}
static void same(const std::vector<W256>& a,const std::vector<W256>& b){
 if(a.size()!=b.size())throw std::runtime_error("source size changed");
 for(unsigned i=0;i<a.size();i++)for(unsigned j=0;j<32;j++)
  if(byte256(a[i],j)!=byte256(b[i],j))throw std::runtime_error("DDR source, LUT or guard changed");
}
static unsigned expected_byte(const Case& c,unsigned y,unsigned x,unsigned channel,unsigned seed,const int8_t tables[2][256]){
 if(channel>=c.ci)return 0;
 if(c.mode==0)return pattern(0,y,x,channel,seed);
 unsigned branch=channel<c.ca?0:1,local=branch?channel-c.ca:channel,factor=branch?c.fb:c.fa;
 unsigned raw=pattern(branch,y/factor,x/factor,local,seed);
 return uint8_t(tables[branch][raw]);
}
static void run(Case c,const int8_t tables[2][256]){
 unsigned seed=947923u+number;
 Stream<P256> packets;uint32_t status=0xabcdefu;
 if(c.invalid){
  ct_tensor_reader(nullptr,packets,c.h,c.w,c.ci,c.k,nullptr,nullptr,c.mode,c.ca,c.cb,c.fa,c.fb,status);
  if(status!=1||!packets.empty())throw std::runtime_error("malformed configuration read DDR or emitted a packet");
  std::printf("TENSOR_READER_FULL_PASS case=%u invalid=1 packets=0\n",number++);invalid++;return;
 }
 auto a=source(c.h/c.fa,c.w/c.fa,c.ca,0,seed);
 auto b=source(c.cb?c.h/c.fb:1,c.cb?c.w/c.fb:1,c.cb?c.cb:1,1,seed);
 std::vector<W256> lut(18);
 for(unsigned j=0;j<32;j++){setbyte(lut.front(),j,int8_t(0xc3));setbyte(lut.back(),j,int8_t(0x3c));}
 for(unsigned branch=0;branch<2;branch++)for(unsigned j=0;j<256;j++)setbyte(lut[1+branch*8+j/32],j%32,tables[branch][j]);
 auto acopy=a,bcopy=b,lcopy=lut;
 ct_tensor_reader(a.data()+1,packets,c.h,c.w,c.ci,c.k,b.data()+1,lut.data()+1,c.mode,c.ca,c.cb,c.fa,c.fb,status);
 if(status!=0)throw std::runtime_error("valid configuration rejected");
 unsigned groups=(c.ci+7)/8,bytes=c.h*c.w*groups*8;
 unsigned count=c.k==1?(bytes+31)/32:(c.h+2)*(c.w+2)*groups;
 for(unsigned i=0;i<count;i++){
  if(packets.empty())throw std::runtime_error("missing output packet");
  P256 p=packets.read();unsigned remain=bytes-i*32;
  uint32_t keep=c.k==3?255u:(i+1<count||remain==32?0xffffffffu:((1u<<remain)-1));
  if(uint32_t(p.keep)!=keep||uint32_t(p.strb)!=keep||bool(p.last)!=(i+1==count))throw std::runtime_error("keep/strb/last differs");
  for(unsigned j=0;j<32;j++){
   unsigned wanted=0;
   if(c.k==1){
    unsigned at=i*32+j;
    if(at<bytes){unsigned pixel=at/(groups*8),channel=at%(groups*8);wanted=expected_byte(c,pixel/c.w,pixel%c.w,channel,seed,tables);}
   }else{
    unsigned group=i%groups,pixel=i/groups,y=pixel/(c.w+2),x=pixel%(c.w+2);
    if(j<8&&y>=1&&y<=c.h&&x>=1&&x<=c.w)wanted=expected_byte(c,y-1,x-1,group*8+j,seed,tables);
   }
   if(uint8_t(byte256(p.data,j))!=wanted)throw std::runtime_error("complete output data or zero padding differs");
  }
 }
 if(!packets.empty())throw std::runtime_error("extra output packets");
 same(a,acopy);same(b,bcopy);same(lut,lcopy);
 std::printf("TENSOR_READER_FULL_PASS case=%u invalid=0 packets=%u\n",number++,count);valid++;
}
int main(){
 try{
  int8_t tables[2][256];for(unsigned b=0;b<2;b++)for(unsigned i=0;i<256;i++)tables[b][i]=int8_t(i);
  const unsigned shape[][2]={{1,1},{1,7},{3,5},{8,16}},channels[]={1,5,8,9,31,32,63,64};
  for(unsigned k:{1u,3u})for(auto& s:shape)for(unsigned ci:channels)run({s[0],s[1],ci,0,1,1,k,0,ci,false},tables);
  const unsigned join[][2]={{1,0},{5,0},{16,0},{1,1},{7,9},{9,7},{31,33},{32,32},{63,1}};
  const unsigned factors[][2]={{1,1},{2,1},{1,2},{2,2}};
  for(unsigned k:{1u,3u})for(auto& ch:join)for(auto& f:factors){
   for(unsigned b=0;b<2;b++)for(unsigned i=0;i<256;i++)tables[b][i]=int8_t(pattern(b,number,i,b+3,919));
   run({8,12,ch[0],ch[1],f[0],f[1],k,ch[1]?2u:1u,ch[0]+ch[1],false},tables);
  }
  for(auto& model:model_cases)for(unsigned k:{1u,3u})run({model.h,model.w,model.ca,model.cb,model.fa,model.fb,k,2,model.ca+model.cb,false},model.tables);
  const Case bad[]={
   {0,12,5,0,1,1,1,1,5,true},{513,12,5,0,1,1,1,1,5,true},{8,0,5,0,1,1,1,1,5,true},{8,513,5,0,1,1,1,1,5,true},
   {8,12,5,0,1,1,2,1,5,true},{8,12,5,0,1,1,1,3,5,true},{8,12,0,0,1,1,1,1,0,true},{8,12,65,0,1,1,1,1,65,true},
   {8,12,5,1,1,1,1,1,6,true},{8,12,5,0,0,1,1,1,5,true},{8,12,5,0,3,1,1,1,5,true},{8,12,5,0,1,0,1,1,5,true},
   {8,12,5,0,1,4,1,1,5,true},{7,12,5,0,2,1,1,1,5,true},{8,11,5,0,2,1,1,1,5,true},{8,12,5,0,1,1,1,2,5,true},
   {8,12,5,0,1,1,1,1,6,true}};
  for(auto c:bad)run(c,tables);
  if(number!=159||valid!=142||invalid!=17)throw std::runtime_error("full test coverage changed");
  std::puts("ALL TENSOR READER 159 FULL FRAMES PASSED valid=142 invalid=17");return 0;
 }catch(const std::exception& e){std::fprintf(stderr,"TENSOR_READER_FAIL case=%u %s\n",number,e.what());return 1;}
}
