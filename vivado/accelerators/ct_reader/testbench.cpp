// Keep the original full159 bench and its golden model completely unchanged.
#define main original_main
#include "../../modules/segmentation/axis_tensor_reader_r3/HLS_r1/testbench.cpp"
#undef main

namespace join16_tests {
static unsigned raw(unsigned branch,unsigned pixel,unsigned channel){
 if(pixel==0&&channel==0)return branch?127u:128u;
 if(pixel==0&&channel==15)return branch?128u:127u;
 return ((pixel*37u+channel*19u+branch*83u)^((pixel>>1)*7u+channel*11u))&255u;
}

static std::vector<W256> input(unsigned pixels,unsigned branch){
 std::vector<W256> result((pixels+1)/2+2);
 for(auto& word:result)for(unsigned j=0;j<32;j++)setbyte(word,j,int8_t(branch?0x6b:0xd3));
 for(unsigned j=0;j<32;j++){
  setbyte(result.front(),j,int8_t(0xa7));
  setbyte(result.back(),j,int8_t(0x5b));
 }
 for(unsigned pixel=0;pixel<pixels;pixel++)for(unsigned c=0;c<16;c++)
  setbyte(result[1+pixel/2],(pixel&1)*16+c,int8_t(raw(branch,pixel,c)));
 return result;
}

static void unchanged(const std::vector<W256>& before,const std::vector<W256>& after){
 if(before.size()!=after.size())throw std::runtime_error("join16 input length changed");
 for(unsigned i=0;i<before.size();i++)for(unsigned j=0;j<32;j++)
  if(byte256(before[i],j)!=byte256(after[i],j))
   throw std::runtime_error("join16 source/LUT/guard changed");
}

static void one(unsigned index,unsigned h,unsigned w,unsigned kernel){
 const unsigned pixels=h*w;
 auto a=input(pixels,0),b=input(pixels,1);
 std::vector<W256> lut(18);
 int8_t table[2][256];
 for(unsigned j=0;j<32;j++){
  setbyte(lut.front(),j,int8_t(0xc3));
  setbyte(lut.back(),j,int8_t(0x3c));
 }
 for(unsigned i=0;i<256;i++){
  table[0][i]=int8_t((i*13u+17u)&255u);
  table[1][i]=int8_t(((i*29u+91u)^0xa6u)&255u);
 }
 for(unsigned branch=0;branch<2;branch++)for(unsigned i=0;i<256;i++)
  setbyte(lut[1+branch*8+i/32],i%32,table[branch][i]);
 const auto a_before=a,b_before=b,lut_before=lut;
 Stream<P256> output;
 uint32_t status=0xabcdefu;
 ct_tensor_reader(a.data()+1,output,h,w,32,kernel,b.data()+1,lut.data()+1,
                  2,16,16,1,1,status);
 if(status!=0)throw std::runtime_error("join16 valid shape rejected");
 const unsigned count=kernel==1?pixels:4*(h+2)*(w+2);
 for(unsigned i=0;i<count;i++){
  if(output.empty())throw std::runtime_error("join16 missing packet");
  const P256 packet=output.read();
  const uint32_t keep=kernel==1?0xffffffffu:255u;
  if(uint32_t(packet.keep)!=keep||uint32_t(packet.strb)!=keep||bool(packet.last)!=(i+1==count))
   throw std::runtime_error("join16 keep/strb/TLAST mismatch");
  for(unsigned j=0;j<32;j++){
   unsigned expected=0;
   if(kernel==1){
    // Plain pixel/channel oracle; it does not call either transform or framer.
    const unsigned branch=j/16,channel=j%16;
    expected=uint8_t(table[branch][raw(branch,i,channel)]);
   }else{
    const unsigned group=i%4,padded_pixel=i/4;
    const unsigned y=padded_pixel/(w+2),x=padded_pixel%(w+2);
    if(j<8&&y>=1&&y<=h&&x>=1&&x<=w){
     const unsigned channel=group*8+j,branch=channel/16;
     expected=uint8_t(table[branch][raw(branch,(y-1)*w+x-1,channel%16)]);
    }
   }
   if(uint8_t(byte256(packet.data,j))!=expected)
    throw std::runtime_error("join16 data/zero padding mismatch");
  }
 }
 if(!output.empty())throw std::runtime_error("join16 extra packets");
 unchanged(a_before,a);unchanged(b_before,b);unchanged(lut_before,lut);
 std::printf("CT_READER_JOIN16_PASS case=%u h=%u w=%u kernel=%u packets=%u\n",
             index,h,w,kernel,count);
}

static void legacy_follow(){
 std::array<W256,3> source{};
 for(unsigned j=0;j<32;j++){
  setbyte(source.front(),j,int8_t(0xa7));
  setbyte(source.back(),j,int8_t(0x5b));
 }
 for(unsigned j=0;j<24;j++)setbyte(source[1],j,int8_t((j*31u+9u)&255u));
 const auto before=source;
 Stream<P256> output;uint32_t status=0xabcdefu;
 ct_tensor_reader(source.data()+1,output,1,3,5,1,nullptr,nullptr,0,5,0,1,1,status);
 if(status||output.empty())throw std::runtime_error("legacy follower missing packet");
 const P256 packet=output.read();
 if(uint32_t(packet.keep)!=0x00ffffffu||uint32_t(packet.strb)!=0x00ffffffu||!bool(packet.last))
  throw std::runtime_error("legacy follower sidebands changed");
 for(unsigned j=0;j<32;j++)if(byte256(packet.data,j)!=byte256(before[1],j))
  throw std::runtime_error("legacy follower bytes changed");
 if(!output.empty())throw std::runtime_error("legacy follower extra packet");
 for(unsigned i=0;i<3;i++)for(unsigned j=0;j<32;j++)
  if(byte256(source[i],j)!=byte256(before[i],j))throw std::runtime_error("legacy follower source changed");
 std::puts("CT_READER_JOIN16_LEGACY_FOLLOW_PASS packets=1");
}
}

int main(){
 if(original_main()!=0)return 1;
 try{
  const unsigned shapes[][2]={{1,1},{1,7},{3,5},{8,16},{1,127},{1,128},{1,129},{3,129}};
  unsigned index=0;
  for(const auto& shape:shapes)for(unsigned kernel:{1u,3u})
   join16_tests::one(index++,shape[0],shape[1],kernel);
  if(index!=16)throw std::runtime_error("join16 coverage changed");
  join16_tests::legacy_follow();
  std::puts("CT_READER_JOIN16_ALL_PASS cases=16 legacy_follow=1 original159_preserved=1");
  return 0;
 }catch(const std::exception& error){
  std::fprintf(stderr,"CT_READER_JOIN16_FAIL %s\n",error.what());
  return 1;
 }
}
