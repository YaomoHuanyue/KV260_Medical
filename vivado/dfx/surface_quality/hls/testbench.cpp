#include "scope.hpp"
#ifndef FIXTURE_ROOT
#define FIXTURE_ROOT "fixtures/"
#endif
#include <fstream>
#include <iostream>
#include <vector>
#include <stdexcept>
#include <cstring>
#include <cstdlib>
#include <algorithm>

static std::vector<unsigned char> read(const std::string& path) {
 std::ifstream f(path,std::ios::binary);
 if(!f)throw std::runtime_error("Cannot read "+path);
 return {std::istreambuf_iterator<char>(f),{}};
}
enum Framing { NORMAL, BAD_LAST, BAD_USER, BAD_KEEP, BAD_STRB };
static unsigned transactions=0;
static std::vector<uint32_t> run(const std::vector<unsigned char>& bytes,
 unsigned op,unsigned outwords,Framing framing=NORMAL) {
 if(bytes.empty()||bytes.size()%64||!outwords)throw std::runtime_error("Invalid test transaction");
 hls::stream<ScopeAxis> in,out;
 const unsigned count=bytes.size()/64;
 for(unsigned i=0;i<count;++i) {
  ScopeAxis w;w.data=0;w.keep=-1;w.strb=-1;w.user=i==0;w.last=i+1==count;
  if(framing==BAD_LAST&&i+1==count)w.last=0;
  if(framing==BAD_USER&&i==0)w.user=0;
  if(framing==BAD_KEEP&&i==0)w.keep[63]=0;
  if(framing==BAD_STRB&&i==0)w.strb[63]=0;
  for(int j=0;j<64;++j)w.data.range(j*8+7,j*8)=bytes[i*64+j];
  in.write(w);
 }
 unsigned status=999;scope_visual(in,out,op,count,outwords,status);++transactions;
 if(!in.empty())throw std::runtime_error("Input undrained");
 std::vector<uint32_t> result;
 for(unsigned i=0;i<outwords;++i) {
  if(out.empty())throw std::runtime_error("Missing output");
  auto w=out.read();
  if(bool(w.last)!=(i+1==outwords)||bool(w.user)!=(i==0)||
     w.keep!=ap_uint<64>(-1)||w.strb!=ap_uint<64>(-1))throw std::runtime_error("Output framing");
  for(int j=0;j<16;++j)result.push_back(w.data.range(j*32+31,j*32));
 }
 if(!out.empty()||result[0]!=status)throw std::runtime_error("Output/status mismatch");
 if(status&&std::any_of(result.begin()+16,result.end(),[](uint32_t v){return v!=0;}))
  throw std::runtime_error("Error payload was not zero-filled");
 return result;
}
static void expect_status(const std::vector<uint32_t>& result,unsigned status,const std::string& name) {
 if(result[0]!=status)throw std::runtime_error(name+": status "+std::to_string(result[0])+" expected "+std::to_string(status));
}
static void upload(const std::vector<unsigned char>& scene) {
 auto ack=run(scene,0,1);expect_status(ack,0,"Upload");
 if(ack[2]!=123)throw std::runtime_error("Scene token mismatch");
}
static void compare(const std::string& name,const std::vector<unsigned char>& request,
 const std::vector<unsigned char>& expected) {
 auto image=run(request,1,1+expected.size()/64);expect_status(image,0,name);
 if(image[1]!=777||image[2]!=123)throw std::runtime_error("Frame token mismatch");
 if(memcmp(image.data()+16,expected.data(),expected.size())) {
  for(unsigned i=0;i<expected.size()/4;++i) {
   uint32_t v;memcpy(&v,expected.data()+i*4,4);
   if(image[16+i]!=v){std::cerr<<name<<" word "<<i<<" got "<<std::hex<<image[16+i]<<" expected "<<v<<std::dec<<'\n';break;}
  }
  throw std::runtime_error("Dense reference mismatch");
 }
}
int main() {try {
 const std::string root=std::getenv("SURFACE_FIXTURE_ROOT")?std::getenv("SURFACE_FIXTURE_ROOT"):FIXTURE_ROOT;
 std::ifstream cases(root+"cases.txt");if(!cases)throw std::runtime_error("Cases list missing");
 unsigned cases_passed=0;std::string name;
 while(cases>>name) {
  auto scene=read(root+name+".scene.bin"),request=read(root+name+".request.bin"),expected=read(root+name+".expected.bin");
  upload(scene);compare(name,request,expected);compare(name,request,expected);
  for(auto framing:{BAD_LAST,BAD_USER,BAD_KEEP,BAD_STRB})
   expect_status(run(request,1,1+expected.size()/64,framing),1,name+" input framing");
  compare(name,request,expected);++cases_passed;
  std::cout<<"PASS "<<name<<" repeated pixels/tokens and TLAST/TUSER/KEEP/STRB guards\n";
 }
 auto scene=read(root+"page_boundary_Q5.scene.bin"),request=read(root+"page_boundary_Q5.request.bin"),expected=read(root+"page_boundary_Q5.expected.bin");
 const unsigned words=1+expected.size()/64;
 std::ifstream guards(root+"guards.txt");if(!guards)throw std::runtime_error("Guards list missing");
 unsigned status,guards_passed=0;
 while(guards>>name>>status) {
  expect_status(run(read(root+name+".bin"),0,1),status,name);
  expect_status(run(request,1,words),3,name+" must unload scene");
  upload(scene);compare(name+" recovery",request,expected);++guards_passed;
  std::cout<<"PASS "<<name<<" rejected, unloaded and valid reload recovered\n";
 }
 for(auto framing:{BAD_LAST,BAD_USER,BAD_KEEP,BAD_STRB}) {
  expect_status(run(scene,0,1,framing),1,"Scene framing");
  expect_status(run(request,1,words),3,"Invalid scene framing must unload");
  upload(scene);compare("framing recovery",request,expected);
 }
 auto invalid=request;int32_t width=15;memcpy(invalid.data(),&width,4);
 expect_status(run(invalid,1,words),3,"Invalid frame width");
 expect_status(run(request,1,words+1),3,"Invalid output size");
 expect_status(run(request,99,1),4,"Unknown operation");
 compare("parameter recovery",request,expected);
 std::cout<<"PASS ALL "<<cases_passed<<" complete-field cases, "<<guards_passed<<" malformed scenes, "<<transactions<<" transactions\n";
 return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
