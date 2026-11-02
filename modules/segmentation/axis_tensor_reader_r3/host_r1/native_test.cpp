// The fake device has separate CPU/device memory and runs actual HLS C tops.
// This verifies the host ABI; it is not RTL, XRT or a board speed measurement.
#define main original_host_contract
#include "legacy_contract.cpp"
#undef main

static unsigned reader_cases=0,reader_refusals=0;
static int reader_weights(void* ctx,unsigned ci,unsigned co,unsigned kernel){
 const unsigned ig=(ci+3)/4,og=(co+7)/8,center=kernel==3?4:0;
 std::vector<W256> packed(ig*og*kernel*kernel);
 for(unsigned c=0;c<ci;++c)setbyte(packed[((c/8)*kernel*kernel+center)*ig+c/4],(c%8)*4+c%4,1);
 int id=ct_add_weights(ctx,packed.data(),packed.size()*32);assert(id>=0);return id;
}
static std::vector<int8_t> pattern(unsigned h,unsigned w,unsigned c,unsigned seed){
 const unsigned stride=((c+7)/8)*8;std::vector<int8_t> a(h*w*stride);
 for(unsigned y=0;y<h;++y)for(unsigned x=0;x<w;++x)for(unsigned k=0;k<c;++k)
  a[(y*w+x)*stride+k]=int8_t(uint8_t(y*53+x*79+k*11+seed));
 return a;
}
static std::vector<int8_t> transformed(const std::vector<int8_t>& a,const std::vector<int8_t>& b,
 unsigned h,unsigned w,unsigned ca,unsigned cb,unsigned fa,unsigned fb,unsigned co,const std::array<int8_t,512>& table){
 std::vector<int8_t> out(h*w*co);
 for(unsigned y=0;y<h;++y)for(unsigned x=0;x<w;++x)for(unsigned c=0;c<ca+cb;++c){
  bool second=c>=ca;unsigned factor=second?fb:fa,channels=second?cb:ca,channel=second?c-ca:c;
  auto& src=second?b:a;auto value=src[((y/factor)*(w/factor)+x/factor)*((channels+7)/8)*8+channel];
  out[(y*w+x)*co+c]=table[(second?256:0)+uint8_t(value)];
 }return out;
}
static void reader_numeric(unsigned h,unsigned w,unsigned ca,unsigned cb,unsigned fa,unsigned fb,unsigned kernel,bool pooling){
 void* ctx=ct_open("mock-only");assert(ctx);ct_set_writer_quantization(ctx,1);
 const unsigned co=((ca+cb+7)/8)*8;int id=reader_weights(ctx,ca+cb,co,kernel);
 std::array<int8_t,512> table;for(unsigned j=0;j<512;++j)table[j]=int8_t(uint8_t(j*37+(j<256?19:113)));
 std::array<int8_t,256> pool_table;for(unsigned j=0;j<256;++j)pool_table[j]=int8_t(uint8_t(j*7+31));
 assert(ct_set_reader_lut(ctx,id,table.data(),cb?2:1)==0);assert(ct_set_reader_lut(ctx,id,table.data(),cb?2:1)==0);
 if(pooling)assert(ct_set_pool_lut(ctx,id,pool_table.data())==0);
 auto a=pattern(h/fa,w/fa,ca,17),b=cb?pattern(h/fb,w/fb,cb,61):std::vector<int8_t>{};
 auto* source=allocate(ctx,a.size());auto* skip=cb?allocate(ctx,b.size()):nullptr;
 auto* full=allocate(ctx,h*w*co);auto* pool=pooling?allocate(ctx,h*w*co/4):nullptr;
 std::memcpy(ct_output_map(source),a.data(),a.size());dirty(source);
 if(skip){std::memcpy(ct_output_map(skip),b.data(),b.size());dirty(skip);}
 auto gold=transformed(a,b,h,w,ca,cb,fa,fb,co,table);auto pool_gold=pooling?pooled_gold(gold,h,w,co,pool_table):std::vector<int8_t>{};
 std::vector<int32_t> bias(co);std::vector<float> scales(co,1);
 auto call=[&](){return ct_execute_reader_mapped(ctx,id,ct_output_map(source),skip?ct_output_map(skip):nullptr,full,pool,
  h,w,ca,cb,fa,fb,co,kernel,cb?2:1,bias.data(),scales.data(),1,0);};
 const auto starts=medical::starts;assert(call()==0);assert(medical::starts==starts+1);
 exact(full,gold);if(pool)exact(pool,pool_gold);exact(source,a);if(skip)exact(skip,b);
 auto& c=*static_cast<Context*>(ctx);assert(!c.input); // No full PS transform/copy buffer.
 assert(!full->ps_written&&(!pool||!pool->ps_written));
 // Inputs emulate clean outputs of a prior PL operation; no TO_DEVICE is needed.
 source->ps_written=false;if(skip)skip->ps_written=false;
 // Source A's partial final DMA beat is zero-padded by the retained host
 // contract and must be synchronized; aligned clean sources can skip it.
 const auto saved=c.skipped_sync[0];assert(call()==0);assert(c.skipped_sync[0]>=saved+(a.size()%32?0:1)+(cb?1:0));
 exact(full,gold);if(pool)exact(pool,pool_gold);
 // Reusing dirty CPU destinations must not allow delayed cache eviction to
 // overwrite the new PL output. Retain both full and pooled destination guards.
 std::memset(ct_output_map(full),0x37,full->bo->size());dirty(full);
 if(pool){std::memset(ct_output_map(pool),0x29,pool->bo->size());dirty(pool);}
 assert(call()==0);exact(full,gold);if(pool)exact(pool,pool_gold);
 // Every legacy invocation must clear the transformed reader mode/pointers.
 int plain=reader_weights(ctx,co,co,1);auto* legacy=allocate(ctx,h*w*co);
 assert(ct_execute_mapped(ctx,plain,ct_output_map(full),legacy,h,w,co,co,1,bias.data(),scales.data(),1,0)==0);
 assert(c.session->registers[0x60/4]==0&&address(*c.session,0,0x40)==0&&address(*c.session,0,0x50)==0);
 exact(legacy,gold);assert(call()==0);exact(full,gold);exact(source,a);if(skip)exact(skip,b);
 ct_output_release(legacy);ct_output_release(source);if(skip)ct_output_release(skip);
 unsigned alive=mock::blocks_alive;ct_close(ctx);assert(mock::blocks_alive==alive);
 exact(full,gold);ct_output_release(full);if(pool){exact(pool,pool_gold);ct_output_release(pool);}
 assert(mock::blocks_alive==0);++reader_cases;
}
static void reader_rejected(){
 void* ctx=ct_open("mock-only");ct_set_writer_quantization(ctx,1);int id=reader_weights(ctx,16,16,1);
 auto* src=allocate(ctx,8*12*8);auto* skip=allocate(ctx,8*12*8);auto* full=allocate(ctx,8*12*16);
 auto* pool=allocate(ctx,4*6*16);auto* short_bo=allocate(ctx,32);
 std::array<int8_t,512> table{};std::vector<int32_t> bias(16);std::vector<float> scales(16,1);
 auto refuse=[&](void* s,void* b,void* dst,void* po,unsigned h=8,unsigned w=12,unsigned ca=7,unsigned cb=9,
                 unsigned fa=1,unsigned fb=1,unsigned mode=2,float qs=1){
  const auto starts=medical::starts;
  assert(ct_execute_reader_mapped(ctx,id,s,b,dst,po,h,w,ca,cb,fa,fb,16,1,mode,bias.data(),scales.data(),qs,0)!=0);
  assert(medical::starts==starts);++reader_refusals;
 };
 auto* a=ct_output_map(src);auto* b=ct_output_map(skip);
 refuse(a,b,full,nullptr); // Missing LUT.
 assert(ct_set_reader_lut(ctx,id,table.data(),2)==0);table[0]=1;
 assert(ct_set_reader_lut(ctx,id,table.data(),2)!=0);++reader_refusals;table[0]=0;
 assert(ct_set_reader_lut(ctx,id,table.data(),1)!=0);++reader_refusals;
 // Source B requires padded16 channels, larger than the first source.
 refuse(a,b,full,nullptr);
 ct_output_release(skip);skip=allocate(ctx,8*12*16);b=ct_output_map(skip);
 refuse(a,b,src,nullptr);refuse(a,b,full,skip);refuse(a,b,full,full);
 refuse(a,b,short_bo,nullptr);refuse(a,ct_output_map(short_bo),full,nullptr);
 refuse(reinterpret_cast<void*>(1),b,full,nullptr);refuse(a,reinterpret_cast<void*>(1),full,nullptr);
 refuse(a,b,reinterpret_cast<void*>(1),nullptr);refuse(a,b,full,reinterpret_cast<void*>(1));
 refuse(a,nullptr,full,nullptr);refuse(a,b,full,nullptr,8,12,7,9,0,1);refuse(a,b,full,nullptr,8,12,7,9,1,3);
 refuse(a,b,full,nullptr,7,12,7,9,2,1);refuse(a,b,full,nullptr,8,11,7,9,1,2);
 refuse(a,b,full,nullptr,8,12,7,9,1,1,0);refuse(a,b,full,nullptr,8,12,7,9,1,1,3);
 refuse(a,b,full,nullptr,8,12,7,9,1,1,1);refuse(a,b,full,nullptr,8,12,7,9,1,1,2,0);
 void* other=ct_open("mock-only");auto* foreign=allocate(other,8*12*16);
 refuse(ct_output_map(foreign),b,full,nullptr);refuse(a,ct_output_map(foreign),full,nullptr);refuse(a,b,foreign,nullptr);
 ct_output_release(foreign);ct_close(other);
 auto* retired=allocate(ctx,8*12*16);auto* retired_ptr=ct_output_map(retired);ct_output_release(retired);
 refuse(retired_ptr,b,full,nullptr);refuse(a,retired_ptr,full,nullptr);refuse(a,b,retired,nullptr);
 // The previously live source is deliberately assigned an unaddressable DDR
 // range only inside this CPU mock; rejection must happen before DMA starts.
 auto region=mock::find(src->bo->address());auto original=region->address;region->address=0x80000000ULL;
 refuse(a,b,full,nullptr);region->address=original+1;refuse(a,b,full,nullptr);region->address=original;
 medical::bad_reader_readback=true;refuse(a,b,full,nullptr);medical::bad_reader_readback=false;
 region.reset(); // Drop the test's deliberate inspection pin before leak check.
 ct_output_release(src);ct_output_release(skip);ct_output_release(full);ct_output_release(pool);ct_output_release(short_bo);ct_close(ctx);
 assert(mock::blocks_alive==0);
}
static void status_after_drain(medical::Session& s){emulate(s);s.registers[0x88/4]=1;}
static void reader_status_contract(){
 void* ctx=ct_open("mock-only");ct_set_writer_quantization(ctx,1);int id=reader_weights(ctx,8,8,1);
 auto* a=allocate(ctx,8*8*8);auto* full=allocate(ctx,8*8*8);std::array<int8_t,256> lut{};
 std::vector<int32_t> bias(8);std::vector<float> scales(8,1);assert(ct_set_reader_lut(ctx,id,lut.data(),1)==0);
 medical::emulate=status_after_drain;unsigned starts=medical::starts;
 assert(ct_execute_reader_mapped(ctx,id,ct_output_map(a),nullptr,full,nullptr,8,8,8,0,1,1,8,1,1,bias.data(),scales.data(),1,0)!=0);
 assert(medical::starts==starts+1&&!static_cast<Context*>(ctx)->dma_active);
 medical::emulate=emulate;
 assert(ct_execute_reader_mapped(ctx,id,ct_output_map(a),nullptr,full,nullptr,8,8,8,0,1,1,8,1,1,bias.data(),scales.data(),1,0)==0);
 ct_output_release(a);ct_output_release(full);ct_close(ctx);assert(mock::blocks_alive==0);
}
int main(){
 assert(original_host_contract()==0);assert(cases==311&&refusals==13&&medical::starts==84);
 mock::next_address=0x10000000ULL;assert(ct_reader_abi()==0xc5030001u);
 for(auto shape:{std::pair<unsigned,unsigned>{8,12},{2,2}})
  for(auto channels:{std::pair<unsigned,unsigned>{1,0},{5,0},{16,0},{1,1},{7,9},{9,7},{31,33},{63,1}})
   for(unsigned fa:{1u,2u})for(unsigned kernel:{1u,3u})for(bool pool:{false,true})
    reader_numeric(shape.first,shape.second,channels.first,channels.second,fa,channels.second?3-fa:1,kernel,pool);
 reader_rejected();reader_status_contract();
 std::cout<<"{\"status\":\"reader_host_actual_HLS_C_contract_exact\",\"reader_full_numeric_lifetime_cases\":"<<reader_cases
  <<",\"reader_refusals_before_DMA\":"<<reader_refusals<<",\"legacy311_checks13_refusals84_calls_preserved\":true"
  <<",\"all_actual_HLS_C_pipeline_calls\":"<<medical::starts<<",\"no_real_PL_or_XRT\":true}"<<std::endl;
}
