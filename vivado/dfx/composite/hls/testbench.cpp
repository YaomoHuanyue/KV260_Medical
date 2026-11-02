#include "composite.hpp"
#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>
static std::vector<uint32_t> read(const std::string&name){
 const char*root=std::getenv("COMPOSITE_FIXTURE_ROOT");if(!root)throw std::runtime_error("COMPOSITE_FIXTURE_ROOT required");
 std::ifstream file(std::string(root)+name,std::ios::binary|std::ios::ate);
 if(!file||file.tellg()%4)throw std::runtime_error("Invalid independent reference fixture");
 std::vector<uint32_t> data(size_t(file.tellg())/4);file.seekg(0);file.read(reinterpret_cast<char*>(data.data()),data.size()*4);
 if(!file)throw std::runtime_error("Fixture read failed");return data;
}
int main(){
 try{
  for(unsigned pixels:{16u,528u,4096u}){
   auto source=read("pixels_"+std::to_string(pixels)+".input.bin");
   unsigned stride=source.size()/8;std::vector<CompositeWord> input(655360+16),output(81920+16);
   for(auto&word:input)word=0x19283746;for(auto&word:output)word=0xa9876543;
   for(unsigned index=0;index<source.size();++index)input[index/4].range((index%4)*32+31,(index%4)*32)=source[index];
   auto before=input;
   for(unsigned active:{0u,1u,2u,3u,4u}){
   auto expected=read(active?"active_"+std::to_string(active)+"_pixels_"+std::to_string(pixels)+".expected.bin":"pixels_"+std::to_string(pixels)+".expected.bin");
   unsigned status=9;
   depth_composite(input.data(),output.data(),pixels,stride/4,0xff201007,status,active);
   if(status||expected.size()!=pixels)return 1;
   for(unsigned index=0;index<pixels;++index)if(uint32_t(output[index/4].range((index%4)*32+31,(index%4)*32))!=expected[index]){
    std::cerr<<"RGBA differs at "<<pixels<<":"<<index<<"\n";return 2;
   }
   for(unsigned index=pixels/4;index<output.size();++index)if(output[index]!=0xa9876543){std::cerr<<"Output guard changed\n";return 3;}
   if(input!=before){std::cerr<<"Input or input padding changed\n";return 4;}
   std::cout<<"PASS composed "<<pixels<<" pixels, stride "<<stride<<", active layers "<<active<<"\n";
   }
  }
  std::vector<CompositeWord> input(655360+16),output(81920+16);
  for(auto&word:output)word=0x12345678;
  for(unsigned pixels:{0u,15u,COMPOSITE_PIXELS+16u}){
   unsigned status=9;depth_composite(input.data(),output.data(),pixels,1,0,status,0);
   if(status!=2)return 5;
   for(auto word:output)if(word!=0x12345678)return 6;
  }
  unsigned status=9;depth_composite(input.data(),output.data(),16,4,0,status,5);
  if(status!=2)return 8;for(auto word:output)if(word!=0x12345678)return 9;
  std::cout<<"PASS invalid parameter and active-layer rejection\n";return 0;
 }catch(const std::exception&error){std::cerr<<error.what()<<"\n";return 7;}
}
