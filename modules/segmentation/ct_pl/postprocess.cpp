#include "postprocess.hpp"
extern "C" void ct_quantize_acc(const int32_t* acc,int8_t* output,unsigned pixels,unsigned channels,
 const int32_t* bias,const float* scale,float qscale,int zero){
 quantize_acc(acc,output,pixels,channels,bias,scale,qscale,zero);
}
