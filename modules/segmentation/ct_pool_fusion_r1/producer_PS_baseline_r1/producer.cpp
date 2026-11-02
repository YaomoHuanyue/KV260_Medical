// Optimized PS comparison only: no XRT, FPGA access or production fallback.
#include "../../ct_pl/postprocess.hpp"
#include <array>
#include <condition_variable>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

static thread_local std::string last_error;
struct Producer {
 unsigned ci,co,k,h,w,padded,threads,mode,generation=0,remaining=0;
 float qscale;int zero;bool stop=false;
 std::vector<int8_t> weights;std::vector<int32_t> bias;std::vector<float> scale;
 std::array<uint8_t,256> table;
 const int8_t* input=nullptr;int8_t* full=nullptr;int8_t* pooled=nullptr;
 std::mutex mutex;std::condition_variable start,done;std::vector<std::thread> workers;
 Producer(const int8_t* original,const int32_t* b,const float* s,float qs,int qz,
          const uint8_t* lut,unsigned ic,unsigned oc,unsigned kernel,unsigned height,
          unsigned width,unsigned nt,unsigned algorithm):ci(ic),co(oc),k(kernel),h(height),
          w(width),padded((ic+7)/8*8),threads(nt),mode(algorithm),qscale(qs),zero(qz){
  if(!original||!b||!s||!lut||!ci||ci>64||!co||co>64||co%8||
     (k!=1&&k!=3)||h<2||h>512||w<2||w>512||h%2||w%2||
     (threads!=1&&threads!=4)||mode>1||!std::isfinite(qscale)||qscale<=0||zero< -128||zero>127)
   throw std::runtime_error("Invalid producer parameters");
#if !defined(__aarch64__)
  if(mode==1)throw std::runtime_error("NEON comparison requires actual aarch64");
#endif
  bias.assign(b,b+co);scale.assign(s,s+co);std::copy(lut,lut+256,table.begin());
  for(float value:scale)if(!std::isfinite(value))throw std::runtime_error("Invalid scale");
  weights.resize(size_t(co)*ci*k*k);
  for(unsigned group=0;group<co/8;group++)for(unsigned ky=0;ky<k;ky++)for(unsigned kx=0;kx<k;kx++)
   for(unsigned c=0;c<ci;c++)for(unsigned lane=0;lane<8;lane++)
    weights[((((group*k+ky)*k+kx)*ci+c)*8+lane)]=original[(((group*8+lane)*ci+c)*k+ky)*k+kx];
  if(threads>1)for(unsigned id=0;id<threads;id++)workers.emplace_back([this,id]{
   unsigned seen=0;std::unique_lock<std::mutex> lock(mutex);
   for(;;){start.wait(lock,[&]{return stop||generation!=seen;});if(stop)return;seen=generation;
    lock.unlock();rows(id*(h/2)/threads,(id+1)*(h/2)/threads);lock.lock();
    if(--remaining==0)done.notify_one();
   }
  });
 }
 ~Producer(){if(!workers.empty()){{std::lock_guard<std::mutex> lock(mutex);stop=true;}start.notify_all();for(auto& t:workers)t.join();}}
 void rows(unsigned begin,unsigned end){
  const int padding=int(k/2);
  for(unsigned y=begin;y<end;y++)for(unsigned x=0;x<w/2;x++)for(unsigned group=0;group<co/8;group++){
   alignas(16) int32_t acc[32]={};
#if defined(__aarch64__)
   int32x4_t a0=vdupq_n_s32(0),a1=a0,a2=a0,a3=a0,b0=a0,b1=a0,b2=a0,b3=a0;
#endif
   for(unsigned ky=0;ky<k;ky++)for(unsigned kx=0;kx<k;kx++){
    const int8_t* src[4]={};
    for(unsigned p=0;p<4;p++){
     int sy=int(y*2+(p>>1)+ky)-padding,sx=int(x*2+(p&1)+kx)-padding;
     if(sy>=0&&sx>=0&&sy<int(h)&&sx<int(w))src[p]=input+(size_t(sy)*w+sx)*padded;
    }
    const auto* wp=weights.data()+(((group*k+ky)*k+kx)*ci)*8;
    for(unsigned c=0;c<ci;c++,wp+=8){
     int8_t q[4];for(unsigned p=0;p<4;p++)q[p]=src[p]?src[p][c]:0;
#if defined(__aarch64__)
     if(mode==1){
      auto ww=vld1_s8(wp);
      auto p0=vmull_s8(ww,vdup_n_s8(q[0]));auto p1=vmull_s8(ww,vdup_n_s8(q[1]));
      auto p2=vmull_s8(ww,vdup_n_s8(q[2]));auto p3=vmull_s8(ww,vdup_n_s8(q[3]));
      a0=vaddw_s16(a0,vget_low_s16(p0));b0=vaddw_s16(b0,vget_high_s16(p0));
      a1=vaddw_s16(a1,vget_low_s16(p1));b1=vaddw_s16(b1,vget_high_s16(p1));
      a2=vaddw_s16(a2,vget_low_s16(p2));b2=vaddw_s16(b2,vget_high_s16(p2));
      a3=vaddw_s16(a3,vget_low_s16(p3));b3=vaddw_s16(b3,vget_high_s16(p3));
     }else
#endif
     for(unsigned p=0;p<4;p++)for(unsigned lane=0;lane<8;lane++)
      acc[p*8+lane]=int32_t(uint32_t(acc[p*8+lane])+uint32_t(int(q[p])*int(wp[lane])));
    }
   }
#if defined(__aarch64__)
   if(mode==1){
    vst1q_s32(acc,a0);vst1q_s32(acc+4,b0);vst1q_s32(acc+8,a1);vst1q_s32(acc+12,b1);
    vst1q_s32(acc+16,a2);vst1q_s32(acc+20,b2);vst1q_s32(acc+24,a3);vst1q_s32(acc+28,b3);
   }
#endif
   int8_t quantized[32];quantize_acc(acc,quantized,4,8,bias.data()+group*8,scale.data()+group*8,qscale,zero);
   for(unsigned p=0;p<4;p++)std::memcpy(full+((size_t(y*2+(p>>1))*w+x*2+(p&1))*co+group*8),quantized+p*8,8);
   for(unsigned lane=0;lane<8;lane++){
    int8_t maximum=quantized[lane];for(unsigned p=1;p<4;p++)maximum=std::max(maximum,quantized[p*8+lane]);
    pooled[(size_t(y)*(w/2)+x)*co+group*8+lane]=int8_t(table[uint8_t(maximum)]);
   }
  }
 }
 void execute(const int8_t* in,int8_t* out,int8_t* pool){
  if(!in||!out||!pool)throw std::runtime_error("Null producer buffer");
  input=in;full=out;pooled=pool;
  if(threads==1){rows(0,h/2);return;}
  std::unique_lock<std::mutex> lock(mutex);remaining=threads;++generation;start.notify_all();
  done.wait(lock,[&]{return remaining==0;});
 }
};
extern "C" const char* producer_error(){return last_error.c_str();}
extern "C" unsigned producer_neon(){
#if defined(__aarch64__)
 return 1;
#else
 return 0;
#endif
}
extern "C" void* producer_create(const int8_t* weights,const int32_t* bias,const float* scale,
 float qscale,int zero,const uint8_t* table,unsigned ci,unsigned co,unsigned k,unsigned h,unsigned w,unsigned threads,unsigned mode){
 try{return new Producer(weights,bias,scale,qscale,zero,table,ci,co,k,h,w,threads,mode);}
 catch(const std::exception& e){last_error=e.what();return nullptr;}
}
extern "C" int producer_execute(void* handle,const int8_t* input,int8_t* full,int8_t* pool){
 try{if(!handle)throw std::runtime_error("Null producer context");static_cast<Producer*>(handle)->execute(input,full,pool);return 0;}
 catch(const std::exception& e){last_error=e.what();return -1;}
}
extern "C" void producer_close(void* handle){delete static_cast<Producer*>(handle);}
