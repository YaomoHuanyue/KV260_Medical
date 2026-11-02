#pragma once
#include <stdexcept>
#include <string>
namespace smooth_d9_hw {
inline void require(bool b,const std::string& s){if(!b)throw std::runtime_error(s);}
inline void require(bool b,const char* s){if(!b)throw std::runtime_error(s);}
}
