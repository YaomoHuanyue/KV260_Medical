#pragma once
// Diagnostic-only access to the existing passive GPIO transfer monitor.
// No HLS control registers or GPIO direction registers are modified here.
#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>

class CTTrafficMonitor {
 using Clock=std::chrono::steady_clock;
 int fd=-1;volatile uint32_t* gpio=nullptr;
 unsigned sample_us;
 std::atomic<bool> stop{false},active{false};
 std::thread sampler;std::mutex mutex;
 std::array<uint32_t,17> before{},after{};
 std::array<uint64_t,84> result{};
 Clock::time_point begin_time;
 uint32_t read_page(unsigned page){
  gpio[0]=page;
#if defined(__aarch64__)
  asm volatile("dsb sy" ::: "memory");
#else
  std::atomic_thread_fence(std::memory_order_seq_cst);
#endif
  return gpio[2];
 }
 void sample(){
  while(!stop.load(std::memory_order_acquire)){
   if(active.load(std::memory_order_acquire)){
    std::lock_guard<std::mutex> lock(mutex);
    if(active.load(std::memory_order_acquire)){
     const uint32_t word=gpio[0];
     const uint64_t ns=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-begin_time).count();
     if(!result[17])result[18]=ns;
     result[19]=ns;result[17]++;
     for(unsigned i=0;i<16;i++)result[20+i*4+((word>>(i*2))&3)]++;
    }
   }
   std::this_thread::sleep_for(std::chrono::microseconds(sample_us));
  }
 }
public:
 explicit CTTrafficMonitor(unsigned period,volatile uint32_t* borrowed=nullptr):sample_us(period){
  if(borrowed)gpio=borrowed;
  else{
   fd=open("/dev/mem",O_RDWR|O_SYNC);
   if(fd<0)throw std::runtime_error("Cannot open passive GPIO monitor /dev/mem");
   void* mapping=mmap(nullptr,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0x80030000);
   if(mapping==MAP_FAILED){close(fd);fd=-1;throw std::runtime_error("Cannot map passive GPIO monitor");}
   gpio=static_cast<volatile uint32_t*>(mapping);
  }
  if(gpio[1]!=0xffffffffu){if(fd>=0){munmap(const_cast<uint32_t*>(gpio),4096);close(fd);}gpio=nullptr;fd=-1;throw std::runtime_error("GPIO monitor channel 1 is not input-only");}
  gpio[0]=0;
  if(sample_us)sampler=std::thread([this]{sample();});
 }
 ~CTTrafficMonitor(){
  stop.store(true,std::memory_order_release);
  if(sampler.joinable())sampler.join();
  if(gpio){gpio[0]=0;if(fd>=0)munmap(const_cast<uint32_t*>(gpio),4096);}
  if(fd>=0)close(fd);
 }
 void begin(){
  std::lock_guard<std::mutex> lock(mutex);
  result.fill(0);
  // Capture transfer counters while all IPs are idle, clock last.
  for(unsigned i=1;i<17;i++)before[i]=read_page(i);
  before[0]=read_page(0);begin_time=Clock::now();
  active.store(sample_us!=0,std::memory_order_release);
 }
 void finish(){
  active.store(false,std::memory_order_release);
  std::lock_guard<std::mutex> lock(mutex);
  after[0]=read_page(0);
  for(unsigned i=1;i<17;i++)after[i]=read_page(i);
  gpio[0]=0;
  for(unsigned i=0;i<17;i++)result[i]=uint32_t(after[i]-before[i]);
 }
 unsigned copy(uint64_t* target,unsigned capacity){
  if(capacity<result.size())return 0;
  std::lock_guard<std::mutex> lock(mutex);
  std::memcpy(target,result.data(),sizeof(result));return result.size();
 }
};
