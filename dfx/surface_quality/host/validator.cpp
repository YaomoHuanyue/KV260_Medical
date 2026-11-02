#include "packet_validator.hpp"
static thread_local std::string error;
extern "C" const char* quality_validation_error(){return error.c_str();}
extern "C" int quality_validate(const void* source,unsigned input_words,unsigned output_words,unsigned operation){
 try{quality_packet::validate(source,input_words,output_words,operation);return 0;}
 catch(const std::exception& exception){error=exception.what();return 1;}
}
extern "C" int quality_guard_intact(const uint8_t* data,size_t count){return data&&quality_packet::intact_guard(data,count);}
