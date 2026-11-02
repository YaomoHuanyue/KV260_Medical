#include <xrt/xrt_device.h>
#include <xrt/xrt_bo.h>
#if __has_include(<xrt/xrt_xclbin.h>)
#include <xrt/xrt_xclbin.h>
#else
#include <experimental/xrt_xclbin.h>
#endif
#include <experimental/xrt_ip.h>
#include <sys/file.h>
#include <fcntl.h>
#include <unistd.h>
#include <algorithm>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <cstdio>
#include <cstdlib>
#include <atomic>
#include <mutex>
#include <array>
#include "postprocess.hpp"
using Clock=std::chrono::steady_clock;
static thread_local std::string error;
static double seconds(Clock::time_point t){return std::chrono::duration<double>(Clock::now()-t).count();}
static void ptr(xrt::ip& ip,unsigned off,uint64_t value){ip.write_register(off,uint32_t(value));ip.write_register(off+4,uint32_t(value>>32));}
struct Context;
struct OutputBuffer {
 Context* owner;std::unique_ptr<xrt::bo> bo;bool leased=false,ps_written=true;
};
struct Context {
 std::atomic<unsigned> references{1};
 std::mutex output_mutex;
 std::vector<std::unique_ptr<OutputBuffer>> output_pool;
 int lock=-1,hardware_lock=-1;
 std::unique_ptr<xrt::device> device;
 std::unique_ptr<xrt::ip> reader,conv,writer;
 std::unique_ptr<xrt::bo> input,output;
 size_t in_capacity=0,out_capacity=0;
 xrt::bo::flags bo_flags=xrt::bo::flags::cacheable;
 std::vector<xrt::bo> weights;
 std::vector<std::unique_ptr<xrt::bo>> quant_params;
 std::vector<std::vector<int8_t>> activation_luts;
 bool pl_quantization=false;
 bool adaptive_wait=false;
 bool skip_clean_sync=false;
 unsigned poll_us=50;
 std::vector<double> predicted_wait;
 std::vector<std::array<unsigned,5>> predicted_shape;
 uint64_t skipped_sync[4]={}; // input calls/bytes, output preparation calls/bytes
 double last_seconds=0,phases[7]={};
 ~Context(){writer.reset();conv.reset();reader.reset();input.reset();output.reset();output_pool.clear();quant_params.clear();weights.clear();device.reset();if(hardware_lock>=0){flock(hardware_lock,LOCK_UN);close(hardware_lock);}if(lock>=0){flock(lock,LOCK_UN);close(lock);}}
};
static void release_context(Context* c){if(c->references.fetch_sub(1)==1)delete c;}
extern "C" void* ct_output_acquire(void* handle,size_t bytes){
 try{
  auto& c=*static_cast<Context*>(handle);
  if(!bytes||bytes>512u*512u*64u)throw std::runtime_error("Invalid quantized output allocation");
  bytes=(bytes+31)&~size_t(31); // Wide DMA owns its complete final beat.
  std::lock_guard<std::mutex> guard(c.output_mutex);OutputBuffer* chosen=nullptr;
  for(auto& p:c.output_pool)if(!p->leased&&p->bo->size()>=bytes&&(!chosen||p->bo->size()<chosen->bo->size()))chosen=p.get();
  if(!chosen){
   auto p=std::make_unique<OutputBuffer>();p->owner=&c;p->bo=std::make_unique<xrt::bo>(*c.device,bytes,c.bo_flags,0);
   chosen=p.get();c.output_pool.push_back(std::move(p));
  }
  chosen->leased=true;c.references.fetch_add(1);return chosen;
 }catch(const std::exception&e){error=e.what();return nullptr;}
}
extern "C" void* ct_output_map(void* output){
 try{return static_cast<OutputBuffer*>(output)->bo->map<void*>();}
 catch(const std::exception&e){error=e.what();return nullptr;}
}
extern "C" void ct_output_mark_ps_written(void* output){
 auto* p=static_cast<OutputBuffer*>(output);
 std::lock_guard<std::mutex> guard(p->owner->output_mutex);p->ps_written=true;
}
extern "C" void ct_output_release(void* output){
 auto* p=static_cast<OutputBuffer*>(output);auto* c=p->owner;
 {std::lock_guard<std::mutex> guard(c->output_mutex);p->leased=false;}
 release_context(c);
}
extern "C" size_t ct_output_pool_bytes(void* handle){
 auto& c=*static_cast<Context*>(handle);size_t bytes=0;
 std::lock_guard<std::mutex> guard(c.output_mutex);
 for(auto& p:c.output_pool)bytes+=p->bo->size();return bytes;
}
static void wait(xrt::ip& ip,Clock::time_point begin,unsigned poll_us=50,double predicted=0){
 bool tail_started=false;auto spin_end=begin;
 while(!(ip.read_register(0)&2)){
  if(seconds(begin)>60){
   // Active PL DMA must never outlive the BO allocations. Hold this process until reset.
   std::fprintf(stderr,"FATAL CT PL timeout: allocations retained. Reset board before terminating this process.\n");std::fflush(stderr);
   if(const char* path=std::getenv("CT_PL_STATUS_PATH")){
    std::ofstream state(path);
    state<<"{\"status\":\"hardware_blocked\",\"error\":\"PL timeout; DMA buffers retained. Reset board before terminating this process.\",\"pid\":"<<getpid()<<"}\n";
   }
   for(;;)std::this_thread::sleep_for(std::chrono::seconds(30));
  }
  if(predicted>0){
   // Sleep through previously measured compute, leaving 120 us for the tail.
   // This is only a scheduling hint: completion is always read from hardware.
   const auto tail=begin+std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(std::max(0.,predicted-.000120)));
   if(Clock::now()<tail){std::this_thread::sleep_until(tail);continue;}
   if(!tail_started){tail_started=true;spin_end=Clock::now()+std::chrono::microseconds(80);}
   if(Clock::now()<spin_end)continue;
  }
  if(poll_us)std::this_thread::sleep_for(std::chrono::microseconds(poll_us));
  else std::this_thread::yield();
 }
}
extern "C" const char* ct_error(){return error.c_str();}
extern "C" void* ct_open(const char* xclbin){
 try{
  auto ctx=std::make_unique<Context>();
  ctx->skip_clean_sync=std::getenv("CT_PL_CLEAN_BO")&&std::string(std::getenv("CT_PL_CLEAN_BO"))=="1";
  if(const char* mode=std::getenv("CT_PL_WAIT_MODE")){
   if(std::string(mode)=="adaptive")ctx->adaptive_wait=true;
   else if(std::string(mode)!="sleep")throw std::runtime_error("CT_PL_WAIT_MODE must be sleep or adaptive");
  }
  if(const char* value=std::getenv("CT_PL_POLL_US")){
   char* end=nullptr;unsigned long us=std::strtoul(value,&end,10);
   if(!*value||*end||us>1000)throw std::runtime_error("CT_PL_POLL_US must be an integer from 0 to 1000");
   ctx->poll_us=unsigned(us);
  }else if(ctx->adaptive_wait)ctx->poll_us=10;
  if(const char* mode=std::getenv("CT_PL_BO_MODE")){
   if(std::string(mode)=="normal")ctx->bo_flags=xrt::bo::flags::normal;
   else if(std::string(mode)!="cacheable")throw std::runtime_error("CT_PL_BO_MODE must be normal or cacheable");
  }
  ctx->lock=open("/tmp/kv260-ct-pl.lock",O_CREAT|O_RDWR,0600);
  if(ctx->lock<0||flock(ctx->lock,LOCK_EX|LOCK_NB))throw std::runtime_error("Another CT PL process owns the accelerator");
  auto common_lock=std::filesystem::absolute(xclbin).parent_path().parent_path().parent_path()/"outputs/xrt/.hardware.lock";
  ctx->hardware_lock=open(common_lock.c_str(),O_CREAT|O_RDWR,0600);
  if(ctx->hardware_lock<0||flock(ctx->hardware_lock,LOCK_EX|LOCK_NB))throw std::runtime_error("Another hardware client is active");
  std::ifstream f("/sys/firmware/devicetree/base/fpga-region/firmware-name",std::ios::binary);std::string fw;std::getline(f,fw,'\0');
  if(fw!="ct_segmentation.bit.bin")throw std::runtime_error("Independent CT firmware is not loaded");
  if(!std::filesystem::exists("/sys/bus/platform/devices/axi:mc_platform/driver")||!std::filesystem::exists("/sys/bus/platform/devices/axi:mc_afi/driver"))throw std::runtime_error("Platform clock/reset/AFI driver unavailable");
  ctx->device=std::make_unique<xrt::device>(0);
  xrt::xclbin image(xclbin);auto loaded=ctx->device->get_xclbin_uuid().to_string();
  if(loaded!="00000000-0000-0000-0000-000000000000"&&loaded!=image.get_uuid().to_string())throw std::runtime_error("A different XCLBIN is still registered: reboot into the CT firmware; live metadata replacement is disabled");
  auto uuid=ctx->device->load_xclbin(image);
  ctx->reader=std::make_unique<xrt::ip>(*ctx->device,uuid,"ct_reader:ct_reader_0");
  ctx->conv=std::make_unique<xrt::ip>(*ctx->device,uuid,"ct_conv:ct_conv_0");
  ctx->writer=std::make_unique<xrt::ip>(*ctx->device,uuid,"ct_writer:ct_writer_0");
  for(auto ip:{ctx->reader.get(),ctx->conv.get(),ctx->writer.get()})if(!(ip->read_register(0)&4))throw std::runtime_error("CT IP is not idle");
  return ctx.release();
 }catch(const std::exception&e){error=e.what();return nullptr;}
}
extern "C" int ct_add_weights(void* handle,const void* data,size_t bytes){
 try{auto& c=*static_cast<Context*>(handle);if(bytes==0||bytes>36864||bytes%32)throw std::runtime_error("Invalid packed weights");
  c.weights.emplace_back(*c.device,bytes,c.bo_flags,0);auto& b=c.weights.back();std::memcpy(b.map<void*>(),data,bytes);b.sync(XCL_BO_SYNC_BO_TO_DEVICE);return int(c.weights.size()-1);
 }catch(const std::exception&e){error=e.what();return -1;}
}
extern "C" void ct_set_writer_quantization(void* handle,unsigned enabled){static_cast<Context*>(handle)->pl_quantization=enabled!=0;}
extern "C" int ct_set_activation_lut(void* handle,int id,const int8_t* table){
 try{
  auto& c=*static_cast<Context*>(handle);
  if(!c.pl_quantization||id<0||size_t(id)>=c.weights.size()||!table)throw std::runtime_error("Invalid activation LUT");
  if(c.quant_params.size()>size_t(id)&&c.quant_params[id])throw std::runtime_error("Cannot change activation after parameter upload");
  if(c.activation_luts.size()<=size_t(id))c.activation_luts.resize(id+1);
  c.activation_luts[id].assign(table,table+256);return 0;
 }catch(const std::exception&e){error=e.what();return -1;}
}
static int execute(void* handle,int id,const void* input,void* output,unsigned h,unsigned w,unsigned ci,unsigned co,unsigned k,const int32_t* bias=nullptr,const float* scale=nullptr,float qscale=1,int zero=0,OutputBuffer* mapped=nullptr){
 try{
  auto& c=*static_cast<Context*>(handle);
  std::fill(std::begin(c.phases),std::end(c.phases),0.);
  if(!h||h>512||!w||w>512||!ci||ci>64||!co||co>64||(k!=1&&k!=3)||id<0||size_t(id)>=c.weights.size())throw std::runtime_error("Unsupported convolution shape");
  bool quantized=c.pl_quantization&&bias;
  bool activation_lut=quantized&&c.activation_luts.size()>size_t(id)&&!c.activation_luts[id].empty();
  size_t packets=size_t(h)*w*((co+7)/8);
  size_t inbytes=size_t(h)*w*((ci+7)/8)*8,outbytes=quantized?((packets+3)/4)*32:packets*32;
  size_t dma_inbytes=(inbytes+31)&~size_t(31);
  if(c.weights[id].size()!=size_t((ci+3)/4)*((co+7)/8)*k*k*32)throw std::runtime_error("Weights do not match shape");
  xrt::bo* source=nullptr;OutputBuffer* source_buffer=nullptr;
  if(mapped){
   std::lock_guard<std::mutex> guard(c.output_mutex);
   for(auto& p:c.output_pool)if(p->leased&&p.get()!=mapped&&p->bo->size()>=dma_inbytes&&p->bo->map<void*>()==input){source=p->bo.get();source_buffer=p.get();break;}
  }
  if(!source&&dma_inbytes>c.in_capacity){c.input=std::make_unique<xrt::bo>(*c.device,dma_inbytes,c.bo_flags,0);c.in_capacity=dma_inbytes;}
  if(mapped&&(!quantized||mapped->owner!=&c||!mapped->leased||mapped->bo->size()<outbytes))throw std::runtime_error("Invalid mapped output lease");
  if(!mapped&&outbytes>c.out_capacity){c.output=std::make_unique<xrt::bo>(*c.device,outbytes,c.bo_flags,0);c.out_capacity=outbytes;}
  auto& target=mapped?*mapped->bo:*c.output;
  auto phase=Clock::now();
  if(!source){source=c.input.get();std::memcpy(source->map<void*>(),input,inbytes);}
  if(dma_inbytes>inbytes){std::memset(static_cast<char*>(source->map<void*>())+inbytes,0,dma_inbytes-inbytes);if(source_buffer)source_buffer->ps_written=true;}
  c.phases[0]=seconds(phase);
  phase=Clock::now();
  if(!c.skip_clean_sync||!source_buffer||source_buffer->ps_written)source->sync(XCL_BO_SYNC_BO_TO_DEVICE,dma_inbytes,0);
  else{c.skipped_sync[0]++;c.skipped_sync[1]+=dma_inbytes;}
  c.phases[1]=seconds(phase);
  // A recycled pool buffer may contain dirty PS-transform cache lines. Flush
  // them before DMA starts, otherwise a later eviction can overwrite PL data.
  // The normal FROM_DEVICE synchronization still follows DMA completion.
  phase=Clock::now();
  if(mapped){
   if(!c.skip_clean_sync||mapped->ps_written)target.sync(XCL_BO_SYNC_BO_TO_DEVICE,outbytes,0);
   else{c.skipped_sync[2]++;c.skipped_sync[3]+=outbytes;}
  }
  c.phases[6]=seconds(phase);
  phase=Clock::now();
  auto&r=*c.reader;auto&v=*c.conv;auto&o=*c.writer;
  ptr(r,0x10,source->address());r.write_register(0x20,h);r.write_register(0x28,w);r.write_register(0x30,ci);r.write_register(0x38,k);
  ptr(v,0x10,c.weights[id].address());v.write_register(0x20,h);v.write_register(0x28,w);v.write_register(0x30,ci);v.write_register(0x38,co);v.write_register(0x40,k);
  ptr(o,0x10,target.address());o.write_register(0x20,packets);
  if(c.pl_quantization){
   o.write_register(0x40,quantized?(activation_lut?2:1):0);
   if(quantized){
    if(c.quant_params.size()<=size_t(id))c.quant_params.resize(id+1);
    if(!c.quant_params[id]){
     const unsigned padded=((co+7)/8)*8;auto p=std::make_unique<xrt::bo>(*c.device,padded*8+(activation_lut?256:0),c.bo_flags,0);
     auto dst=p->map<uint32_t*>();
     for(unsigned j=0;j<padded;j++){std::memcpy(dst+j*2,bias+j,4);std::memcpy(dst+j*2+1,scale+j,4);}
     if(activation_lut)std::memcpy(reinterpret_cast<int8_t*>(dst)+padded*8,c.activation_luts[id].data(),256);
     p->sync(XCL_BO_SYNC_BO_TO_DEVICE);c.quant_params[id]=std::move(p);
    }
    uint32_t bits;std::memcpy(&bits,&qscale,4);
    ptr(o,0x30,c.quant_params[id]->address());o.write_register(0x48,co);o.write_register(0x50,bits);o.write_register(0x58,uint32_t(zero));
   }
  }
  if(r.read_register(0x20)!=h||v.read_register(0x38)!=co||o.read_register(0x20)!=packets||r.read_register(0x10)!=uint32_t(source->address())||v.read_register(0x14)!=uint32_t(c.weights[id].address()>>32))throw std::runtime_error("Control register readback mismatch");
  r.read_register(0);v.read_register(0);o.read_register(0);
  c.phases[2]=seconds(phase);
  auto start=Clock::now();o.write_register(0,1);v.write_register(0,1);r.write_register(0,1);
  if(c.predicted_wait.size()<=size_t(id)){c.predicted_wait.resize(id+1);c.predicted_shape.resize(id+1);}
  const std::array<unsigned,5> shape={h,w,ci,co,k};
  const double predicted=c.adaptive_wait&&c.predicted_shape[id]==shape?c.predicted_wait[id]:0;
  wait(o,start,c.poll_us,predicted);wait(v,start,c.poll_us);wait(r,start,c.poll_us);c.last_seconds=seconds(start);
  if(c.predicted_shape[id]!=shape||!c.predicted_wait[id])c.predicted_wait[id]=c.last_seconds;
  else c.predicted_wait[id]=std::min(c.predicted_wait[id],c.last_seconds);
  c.predicted_shape[id]=shape;
  c.phases[3]=c.last_seconds;
  if(v.read_register(0x48)||o.read_register(0x28))throw std::runtime_error("AXIS packet validation failed");
  phase=Clock::now();target.sync(XCL_BO_SYNC_BO_FROM_DEVICE,outbytes,0);c.phases[4]=seconds(phase);
  if(mapped)mapped->ps_written=false;
  phase=Clock::now();if(output)std::memcpy(output,target.map<void*>(),quantized?packets*8:outbytes);c.phases[5]=seconds(phase);return 0;
 }catch(const std::exception&e){error=e.what();return -1;}
}
extern "C" int ct_execute(void* handle,int id,const void* input,void* output,unsigned h,unsigned w,unsigned ci,unsigned co,unsigned k){return execute(handle,id,input,output,h,w,ci,co,k);}
extern "C" int ct_execute_quantized(void* handle,int id,const void* input,void* output,unsigned h,unsigned w,unsigned ci,unsigned co,unsigned k,const int32_t* bias,const float* scale,float qscale,int zero){
 try{
 if(!(qscale>0)||!std::isfinite(qscale)||zero<-128||zero>127){error="Invalid output quantization";return -1;}
 auto& c=*static_cast<Context*>(handle);
 if(c.pl_quantization)return execute(handle,id,input,output,h,w,ci,co,k,bias,scale,qscale,zero);
 int result=ct_execute(handle,id,input,nullptr,h,w,ci,co,k);
 if(result)return result;
 quantize_acc(c.output->map<int32_t*>(),static_cast<int8_t*>(output),h*w,((co+7)/8)*8,bias,scale,qscale,zero);
 return 0;
 }catch(const std::exception&e){error=e.what();return -1;}
}
extern "C" double ct_last_seconds(void* handle){return static_cast<Context*>(handle)->last_seconds;}
extern "C" int ct_execute_mapped(void* handle,int id,const void* input,void* output,unsigned h,unsigned w,unsigned ci,unsigned co,unsigned k,const int32_t* bias,const float* scale,float qscale,int zero){
 if(!(qscale>0)||!std::isfinite(qscale)||zero<-128||zero>127){error="Invalid output quantization";return -1;}
 return execute(handle,id,input,nullptr,h,w,ci,co,k,bias,scale,qscale,zero,static_cast<OutputBuffer*>(output));
}
extern "C" double ct_last_phase(void* handle,unsigned index){return index<7?static_cast<Context*>(handle)->phases[index]:0.;}
extern "C" uint64_t ct_skipped_sync(void* handle,unsigned index){return index<4?static_cast<Context*>(handle)->skipped_sync[index]:0;}
extern "C" void ct_close(void* handle){release_context(static_cast<Context*>(handle));}
