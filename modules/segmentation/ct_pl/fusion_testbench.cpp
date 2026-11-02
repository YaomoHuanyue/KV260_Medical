#define main original_writer_tests
#include "writer_testbench.cpp"
#undef main

static void fusion_case(unsigned channels,unsigned count,unsigned seed,bool exhaustive=false){
 std::mt19937 rng(seed);Stream<P256> sums;
 unsigned padded=(channels+7)/8*8;
 // HLS co-simulation marshals the declared AXI depths, including short cases.
 std::vector<W256> parameters(24),output(1024+count);
 std::vector<int8_t> table(256);std::vector<int> expected;
 for(unsigned i=0;i<256;i++){
  table[i]=int8_t(rng());setbyte(parameters[padded/4+i/32],i%32,table[i]);
 }
 for(unsigned c=0;c<padded;c++){
  setlane(parameters[c/4],(c%4)*2,exhaustive?0:int32_t(c*3)-50);
  setlane(parameters[c/4],(c%4)*2+1,int32_t(bits(exhaustive?1.f:.5f)));
 }
 float qscale=exhaustive?1.f:.375f;int zero=exhaustive?0:-23;
 for(unsigned i=0;i<count;i++){
  P256 p;p.keep=0xffffffffu;p.strb=0xffffffffu;p.last=i+1==count;
  for(unsigned j=0;j<8;j++){
   unsigned c=(i%(padded/8))*8+j;
   int32_t acc=exhaustive?int32_t((i*8+j)%256)-128:int32_t(rng()%2001)-1000;
   setlane(p.data,j,acc);
   float f=float(acc+(exhaustive?0:int32_t(c*3)-50))*(exhaustive?1.f:.5f);f=f/qscale;
   int q=int(std::max(-128.f,std::min(127.f,std::nearbyintf(f)+float(zero))));
   expected.push_back(table[uint8_t(int8_t(q))]);
  }
  sums.write(p);
 }
 for(unsigned j=0;j<8;j++)setlane(output.back(),j,0x34567812);
 uint32_t status=99;
 ct_writer(sums,output.data(),count,status,parameters.data(),2,channels,bits(qscale),uint32_t(zero));
 if(status||!sums.empty())throw std::runtime_error("fusion stream failure");
 for(unsigned i=0;i<count*8;i++)if(int(byte256(output[i/32],i%32))!=expected[i])throw std::runtime_error("fusion mismatch");
 for(unsigned i=count*8;i<((count+3)/4)*32;i++)if(byte256(output[i/32],i%32)!=0)throw std::runtime_error("fusion tail padding");
 for(unsigned j=0;j<8;j++)if(lane(output.back(),j)!=0x34567812)throw std::runtime_error("fusion overwrite");
 std::cout<<"PASS fusion channels="<<channels<<" count="<<count<<" seed="<<seed<<std::endl;
}
int main(){try{
 if(original_writer_tests())return 1;
 fusion_case(8,32,1,true);fusion_case(3,1,2);fusion_case(13,5,3);
 fusion_case(16,1024,4);fusion_case(32,256,5);fusion_case(64,512,6);
 fusion_case(8,32,7,true);fusion_case(1,3,8);
#ifdef CT_NATIVE
 for(unsigned c:{1,3,8,13,16,32,63,64})for(unsigned n:{1,3,5,33,77})fusion_case(c,n,c*17+n);
#endif
 return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 1;}}
