#pragma once
#include <array>
#include <cstring>
#include <fstream>
#include <stdexcept>
#include <string>

namespace routeaudit5 {
// Compare every byte, including length, without byte-by-byte iterator growth
// or two full-size allocations. This has no hardware or firmware side effects.
inline bool same_file(const std::string& left,const std::string& right){
 std::ifstream a(left,std::ios::binary),b(right,std::ios::binary);
 if(!a||!b)throw std::runtime_error("Cannot compare installed identity: "+left+" / "+right);
 std::array<char,65536> x{},y{};
 for(;;){
  a.read(x.data(),x.size());b.read(y.data(),y.size());
  if(a.bad()||b.bad()||(a.fail()&&!a.eof())||(b.fail()&&!b.eof()))throw std::runtime_error("Installed identity read failed");
  auto nx=a.gcount(),ny=b.gcount();
  if(nx!=ny)return false;
  if(nx==0)return true;
  if(std::memcmp(x.data(),y.data(),size_t(nx))!=0)return false;
 }
}
}
