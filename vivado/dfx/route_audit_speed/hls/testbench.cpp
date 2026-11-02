#include "route.hpp"
#include <fstream>
#include <vector>
#include <iostream>
#include <cstdlib>
#include <cmath>
#include <stdexcept>
#include <hls_math.h>
#include "audit.hpp"
static std::vector<Word> load(std::string name){
 const char*dir=std::getenv("ROUTE_AUDIT_FIXTURE_ROOT");if(!dir)throw std::runtime_error("Fixture environment missing");std::ifstream f(std::string(dir)+name,std::ios::binary);if(!f)throw std::runtime_error("Missing "+name);f.seekg(0,std::ios::end);auto size=f.tellg();f.seekg(0);std::vector<Word>v(size_t(size)/64);for(auto&w:v)for(unsigned j=0;j<8;++j){uint64_t b;f.read(reinterpret_cast<char*>(&b),8);lane(w,j,b);}return v;
}
static double real(uint64_t b){double x;std::memcpy(&x,&b,8);return x;}
static std::vector<Word> run(const std::vector<Word>&source,unsigned operation,unsigned count){
 Stream<Packet>a,b;for(unsigned i=0;i<source.size();++i)a.write(packet(source[i],i,source.size()));uint32_t status=0;nav_route(a,b,operation,source.size(),operation?ROUTE_OUTPUT_WORDS:1,status);if(status)throw std::runtime_error("Core status "+std::to_string(status));std::vector<Word>out;for(unsigned i=0;i<count;++i){auto p=b.read();if(bool(p.user)!=(i==0)||bool(p.last)!=(i+1==count)||p.keep!=~uint64_t(0)||p.strb!=~uint64_t(0))throw std::runtime_error("Framing");out.push_back(p.data);}if(!a.empty()||!b.empty())throw std::runtime_error("Not drained");return out;
}
int main(){try{
 for(auto&w:load("acos_cases.bin")){double x=real(lane(w,0)),a=audit_acos(x),b=real(lane(w,1));if(a<0||std::abs(a-b)>2e-12+2e-12*b){std::cerr.precision(17);std::cerr<<"ACOS check x="<<x<<" got="<<a<<" expected="<<b<<"\n";
  auto input=audit_turn(x,0,true);AuditInteger ax=AuditInteger(1)<<60,ay=input.y,az=0;int64_t nx=int64_t(1)<<60,ny=int64_t(std::sqrt((1-std::abs(x))/(1+std::abs(x)))*1152921504606846976.),nz=0;
  std::cerr<<"Input y ap="<<ay.to_int64()<<" native="<<ny<<" x="<<ax.to_int64()<<" sizeof int64="<<sizeof(int64_t)<<"\n";
  for(unsigned j=0;j<56;++j){int64_t oldx=nx,oldy=ny,delta=audit_angle_table[j];if(oldy>0){nx=oldx+(oldy>>j);ny=oldy-(oldx>>j);nz+=delta;}else if(oldy<0){nx=oldx-(oldy>>j);ny=oldy+(oldx>>j);nz-=delta;}audit_rotation(ax,ay,az,j);if(ax.to_int64()!=nx||ay.to_int64()!=ny||az.to_int64()!=nz){std::cerr<<"Mismatch j="<<j<<" ap "<<ax.to_int64()<<","<<ay.to_int64()<<","<<az.to_int64()<<" native "<<nx<<","<<ny<<","<<nz<<"\n";break;}}
  std::cerr<<"z double="<<az.to_double()<<" int64="<<az.to_int64()<<" native_z="<<nz<<"\n";
  throw std::runtime_error("Small-angle acos regression");}}
 auto scene=load("scene.bin");run(scene,0,1);
 for(const auto&name:{"default","default_audit","virtual","virtual_audit","unsmoothed","unsmoothed_audit","blocked","blocked_audit"}){
  auto source=load(std::string(name)+".input.bin"),expected=load(std::string(name)+".expected.bin"),got=run(source,1,expected.size());unsigned ids=(unsigned(lane(expected[0],2))+7)/8;
  for(unsigned i=0;i<got.size();++i)for(unsigned j=0;j<8;++j){auto x=lane(got[i],j),y=lane(expected[i],j);
   if(i==0||(i>=2&&i<2+ids)){if(x!=y)throw std::runtime_error(std::string(name)+" integer mismatch");}
   else{double a=real(x),b=real(y);if(std::isinf(a)||std::isinf(b)){if(a!=b){std::cerr<<name<<" row="<<i<<" lane="<<j<<" got="<<a<<" expected="<<b<<"\n";throw std::runtime_error("Infinity mismatch");}}else if(!std::isfinite(a)||std::abs(a-b)>1e-7+2e-9*std::abs(b))throw std::runtime_error(std::string(name)+" geometry/audit mismatch");}
  }std::cout<<"PASS "<<name<<", points="<<lane(got[0],1)<<"\n";
 }
 for(const auto&name:{"own_CT","ties","stream_tail_3","stream_tail_4","stream_tail_5","stream_tail_7","stream_tail_8","stream_tail_9","stream_tail_17"}){
  auto source=load(std::string(name)+".input.bin"),expected=load(std::string(name)+".expected.bin"),got=run(source,2,expected.size());
  for(unsigned i=0;i<got.size();++i)for(unsigned j=0;j<8;++j){auto x=lane(got[i],j),y=lane(expected[i],j);
   if(!i){if(x!=y)throw std::runtime_error("Diagnostic header mismatch");}
   else{double a=real(x),b=real(y);if(std::isinf(a)||std::isinf(b)){if(a!=b)throw std::runtime_error("Diagnostic infinity mismatch");}else if(!std::isfinite(a)||std::abs(a-b)>1e-7+2e-9*std::abs(b))throw std::runtime_error(std::string(name)+" audit mismatch");}
  }std::cout<<"PASS "<<name<<" raw audit\n";
 }
 for(unsigned check=0;check<2;++check){
  unsigned count=check?1:2;Stream<Packet>a,b;Word h{};lane(h,0,AUDIT_QUERY_TAG);lane(h,1,check?(uint64_t(1)<<32):1);
  a.write(packet(h,0,count));
  if(!check){Word w{};double radius=double(std::numeric_limits<float>::max())*2;uint64_t raw;std::memcpy(&raw,&radius,8);lane(w,4,raw);a.write(packet(w,1,count));}
  uint32_t status=0;nav_route(a,b,2,count,ROUTE_OUTPUT_WORDS,status);
  if(!(status&2)||!a.empty())throw std::runtime_error("Malformed diagnostic was accepted");
  auto response=b.read();if(!(lane(response.data,0)&2)||lane(response.data,1)!=0||!response.last||!b.empty())throw std::runtime_error("Malformed diagnostic framing");
 }
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
