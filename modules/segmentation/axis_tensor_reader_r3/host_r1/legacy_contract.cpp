// Exercise the actual generated host against separate CPU/device allocations
// and the actual R6 HLS-C top. This is host testing, not real RTL or hardware.
#include "ct_tensor_bridge.cpp"
#include "../../ct_pool_fusion_r1/adapter_r7/writer_pool.cpp"
extern "C" void ct_tensor_reader(const W256*,Stream<P256>&,uint32_t,uint32_t,uint32_t,uint32_t,const W256*,const W256*,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t&);
#include <cassert>
#include <iostream>

static unsigned cases=0,refusals=0;
static uint64_t address(medical::Session& s,unsigned base,unsigned offset){return uint64_t(s.registers[(base+offset)/4])|(uint64_t(s.registers[(base+offset+4)/4])<<32);}
static void emulate(medical::Session& s){
 auto u=[&](unsigned b,unsigned o){return s.registers[(b+o)/4];};
 auto input=mock::find(address(s,0,0x10));auto weights=mock::find(address(s,0x1000,0x10));auto full=mock::find(address(s,0x2000,0x10));
 auto parameters=mock::find(address(s,0x2000,0x30));unsigned mode=u(0x2000,0x40);uint32_t conv_status=0,status=0,reader_status=0;
 Stream<P256> pixels,sums;
 std::shared_ptr<mock::Block> skip,reader_lut;
 if(u(0,0x60)){reader_lut=mock::find(address(s,0,0x50));if(u(0,0x70))skip=mock::find(address(s,0,0x40));}
 ct_tensor_reader(reinterpret_cast<const W256*>(input->device.data()),pixels,u(0,0x20),u(0,0x28),u(0,0x30),u(0,0x38),
  skip?reinterpret_cast<const W256*>(skip->device.data()):nullptr,reader_lut?reinterpret_cast<const W256*>(reader_lut->device.data()):nullptr,
  u(0,0x60),u(0,0x68),u(0,0x70),u(0,0x78),u(0,0x80),reader_status);
 s.registers[0x88/4]=reader_status;assert(!reader_status);
 ct_conv(reinterpret_cast<const W256*>(weights->device.data()),pixels,sums,u(0x1000,0x20),u(0x1000,0x28),u(0x1000,0x30),u(0x1000,0x38),u(0x1000,0x40),conv_status);
 std::shared_ptr<mock::Block> pooled,table;
 if(mode==3){pooled=mock::find(address(s,0x2000,0x60));table=mock::find(address(s,0x2000,0x70));}
 ct_writer_pool(sums,reinterpret_cast<W256*>(full->device.data()),u(0x2000,0x20),status,
  reinterpret_cast<const W256*>(parameters->device.data()),mode,u(0x2000,0x48),u(0x2000,0x50),u(0x2000,0x58),
  pooled?reinterpret_cast<W256*>(pooled->device.data()):nullptr,table?reinterpret_cast<const W256*>(table->device.data()):nullptr,u(0x2000,0x80));
 assert(!conv_status&&!status&&pixels.empty()&&sums.empty());s.registers[(0x1000+0x48)/4]=conv_status;s.registers[(0x2000+0x28)/4]=status;
}
static int weights(void* ctx,unsigned channels){
 const unsigned ig=(channels+3)/4,og=(channels+7)/8;std::vector<W256> packed(ig*og);
 for(unsigned c=0;c<channels;++c)setbyte(packed[(c/8)*ig+c/4],(c%8)*4+c%4,1);
 int id=ct_add_weights(ctx,packed.data(),packed.size()*32);assert(id>=0);return id;
}
static OutputBuffer* allocate(void* ctx,size_t n){auto p=static_cast<OutputBuffer*>(ct_output_acquire(ctx,n));assert(p);return p;}
static void dirty(OutputBuffer* p){ct_output_mark_ps_written(p);mock::find(p->bo->address())->dirty=true;}
static std::vector<int8_t> pooled_gold(const std::vector<int8_t>& full,unsigned h,unsigned w,unsigned c,const std::array<int8_t,256>& table){
 std::vector<int8_t> out(h/2*w/2*c);
 for(unsigned y=0;y<h/2;++y)for(unsigned x=0;x<w/2;++x)for(unsigned k=0;k<c;++k){
  int8_t v=-128;for(unsigned dy=0;dy<2;++dy)for(unsigned dx=0;dx<2;++dx)v=std::max(v,full[((2*y+dy)*w+2*x+dx)*c+k]);
  out[(y*(w/2)+x)*c+k]=table[uint8_t(v)];
 }return out;
}
static void exact(OutputBuffer* p,const std::vector<int8_t>& expected){assert(!std::memcmp(ct_output_map(p),expected.data(),expected.size()));++cases;}
static void numeric(unsigned h,unsigned w,unsigned c){
 void* ctx=ct_open("mock-only");assert(ctx);ct_set_writer_quantization(ctx,1);int id=weights(ctx,c);
 std::array<int8_t,256> table;for(unsigned i=0;i<256;++i)table[i]=int8_t(uint8_t(i*37+13));
 assert(ct_set_pool_lut(ctx,id,table.data())==0);assert(ct_set_pool_lut(ctx,id,table.data())==0);
 auto* input=allocate(ctx,h*w*c);auto* full=allocate(ctx,h*w*c);auto* pool=allocate(ctx,h*w*c/4);
 std::vector<int8_t> data(h*w*c);for(unsigned i=0;i<data.size();++i)data[i]=int8_t(uint8_t(i*79+cases));
 std::memcpy(ct_output_map(input),data.data(),data.size());dirty(input);
 std::vector<int32_t> bias(c);std::vector<float> scale(c,1);
 unsigned start=medical::starts,loads=medical::loads;
 assert(ct_execute_pool_mapped(ctx,id,ct_output_map(input),full,pool,h,w,c,c,1,bias.data(),scale.data(),1,0)==0);
 assert(medical::starts==start+1&&medical::loads==loads);exact(full,data);auto gold=pooled_gold(data,h,w,c,table);exact(pool,gold);
 assert(!full->ps_written&&!pool->ps_written);
 if(gold.size()%32){auto p=static_cast<uint8_t*>(ct_output_map(pool));for(size_t i=gold.size();i<pool->bo->size();++i)assert(p[i]==0);++cases;}
 // A live full-resolution skip must not be recycled while pooled data feeds
 // the next PL convolution. The original full buffer is checked afterwards.
 auto* next=allocate(ctx,gold.size());assert(next!=full&&next!=pool);
 auto* state=static_cast<Context*>(ctx);auto before=state->skipped_sync[0];
 assert(ct_execute_mapped(ctx,id,ct_output_map(pool),next,h/2,w/2,c,c,1,bias.data(),scale.data(),1,0)==0);
 if(gold.size()%32==0)assert(state->skipped_sync[0]>before);else{assert(state->skipped_sync[0]==before);assert(pool->ps_written);}
 exact(next,gold);exact(full,data);exact(pool,gold);
 // Dirty PS reuse must flush both destinations before DMA. The mock models
 // a delayed dirty CPU eviction that would corrupt omitted preparation.
 std::memset(ct_output_map(full),0x12,h*w*c);dirty(full);std::memset(ct_output_map(pool),0x34,pool->bo->size());dirty(pool);
 assert(ct_execute_pool_mapped(ctx,id,ct_output_map(input),full,pool,h,w,c,c,1,bias.data(),scale.data(),1,0)==0);
 exact(full,data);exact(pool,gold);
 ct_output_release(next);ct_output_release(input);
 // Closing the backend must keep the session and both leased BOs alive.
 unsigned live=mock::blocks_alive;ct_close(ctx);assert(mock::blocks_alive==live);exact(full,data);exact(pool,gold);
 ct_output_release(full);exact(pool,gold);ct_output_release(pool);assert(mock::blocks_alive==0);++cases;
}
static void rejected(){
 void* ctx=ct_open("mock-only");ct_set_writer_quantization(ctx,1);int id=weights(ctx,16);
 auto* input=allocate(ctx,8*8*16);auto* full=allocate(ctx,8*8*16);auto* pool=allocate(ctx,4*4*16);auto* short_pool=allocate(ctx,32);
 std::array<int8_t,256> table{};std::vector<int32_t> bias(16);std::vector<float> scale(16,1);
 auto call=[&](void* source,void* a,void* b,unsigned h,unsigned w,unsigned co,float qs=1){
  unsigned before=medical::starts;
  assert(ct_execute_pool_mapped(ctx,id,source,a,b,h,w,16,co,1,bias.data(),scale.data(),qs,0)!=0);
  assert(medical::starts==before);++refusals;
 };
 auto* source=ct_output_map(input);
 call(source,full,pool,8,8,16); // No configured LUT.
 assert(ct_set_pool_lut(ctx,id,table.data())==0);
 table[1]=1;assert(ct_set_pool_lut(ctx,id,table.data())!=0);++refusals;
 call(source,full,full,8,8,16);call(source,full,short_pool,8,8,16);
 call(source,full,pool,3,8,16);call(source,full,pool,8,3,16);call(source,full,pool,8,8,13);
 call(ct_output_map(full),full,pool,8,8,16);call(ct_output_map(pool),full,pool,8,8,16);call(source,full,pool,8,8,16,0);
 medical::bad_shape_readback=true;call(source,full,pool,8,8,16);medical::bad_shape_readback=false;
 void* other=ct_open("mock-only");auto* foreign=allocate(other,4*4*16);call(source,full,foreign,8,8,16);
 ct_output_release(foreign);ct_close(other);
 int activation_id=weights(ctx,16);assert(ct_set_activation_lut(ctx,activation_id,table.data())==0);
 unsigned before=medical::starts;assert(ct_set_pool_lut(ctx,activation_id,table.data())!=0);assert(medical::starts==before);++refusals;
 ct_output_release(input);ct_output_release(full);ct_output_release(pool);ct_output_release(short_pool);ct_close(ctx);assert(mock::blocks_alive==0);
}
int main(){
 medical::emulate=emulate;
 assert(ct_pool_abi()==0xc5000001u);
 for(unsigned c:{8u,16u,32u,64u})for(auto shape:{std::pair<unsigned,unsigned>{2,2},{4,6},{8,8}})numeric(shape.first,shape.second,c);
 for(unsigned i=0;i<16;++i)numeric(8,8,16);
 rejected();assert(mock::blocks_alive==0);
 std::cout<<"{\"status\":\"native_host_HLS_C_exact\",\"numeric_and_lifecycle_checks\":"<<cases
  <<",\"refusals_before_DMA\":"<<refusals<<",\"actual_HLS_C_convolution_writer_calls\":"<<medical::starts
  <<",\"actual_fake_DFX_loads\":"<<medical::loads<<",\"no_real_PL_or_XRT\":true}"<<std::endl;
 return 0;
}
