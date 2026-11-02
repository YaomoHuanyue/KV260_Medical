#include "scope.hpp"
#ifndef FIXTURE_ROOT
#define FIXTURE_ROOT "V:/fixtures/"
#endif
#include <fstream>
#include <iostream>
#include <vector>
#include <stdexcept>
#include <cstring>
#include <cstdlib>
static std::vector<unsigned char> read(const std::string& path){std::ifstream f(path,std::ios::binary);if(!f)throw std::runtime_error(path);return {std::istreambuf_iterator<char>(f),{}};}
static std::vector<uint32_t> run(std::vector<unsigned char> bytes,unsigned op,unsigned outwords,bool corrupt=false){
 hls::stream<ScopeAxis> in,out;
 for(unsigned i=0;i<bytes.size()/64;++i){ScopeAxis w;w.data=0;w.keep=-1;w.strb=-1;w.user=i==0;w.last=i+1==bytes.size()/64&&!corrupt;for(int j=0;j<64;++j)w.data.range(j*8+7,j*8)=bytes[i*64+j];in.write(w);}
 unsigned status=999;scope_visual(in,out,op,bytes.size()/64,outwords,status);
 if(!in.empty())throw std::runtime_error("Input undrained");std::vector<uint32_t> result;
 for(unsigned i=0;i<outwords;++i){if(out.empty())throw std::runtime_error("Missing output");auto w=out.read();if(bool(w.last)!=(i+1==outwords)||bool(w.user)!=(i==0)||w.keep!=ap_uint<64>(-1)||w.strb!=ap_uint<64>(-1))throw std::runtime_error("Output framing");for(int j=0;j<16;++j)result.push_back(w.data.range(j*32+31,j*32));}
 if(!out.empty()||result[0]!=status)throw std::runtime_error("Output/status mismatch");return result;
}
int main(){try{
 for(auto name:{"tube","blocked","filled","empty","anisotropic","zero_normal"}){
  std::string base=std::string(std::getenv("SURFACE_FIXTURE_ROOT")?std::getenv("SURFACE_FIXTURE_ROOT"):FIXTURE_ROOT)+name;
  auto scene=read(base+".scene.bin"),request=read(base+".request.bin"),expected=read(base+".expected.bin");
  auto ack=run(scene,0,1);if(ack[0]||ack[2]!=123)throw std::runtime_error("Upload");
  for(int repeat=0;repeat<2;++repeat){auto image=run(request,1,1+expected.size()/64);if(image[0]||memcmp(image.data()+16,expected.data(),expected.size())){for(unsigned i=0;i<expected.size()/4;++i){uint32_t v;memcpy(&v,expected.data()+i*4,4);if(image[16+i]!=v){std::cerr<<name<<" pixel "<<i<<" got "<<std::hex<<image[16+i]<<" expected "<<v<<std::dec<<'\n';break;}}throw std::runtime_error("Reference mismatch");}}
  auto bad=run(request,1,1+expected.size()/64,true);if(!bad[0])throw std::runtime_error("Bad TLAST accepted");
  std::cout<<"PASS "<<name<<" repeated frame, scene reload and TLAST guard\n";
 }
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
