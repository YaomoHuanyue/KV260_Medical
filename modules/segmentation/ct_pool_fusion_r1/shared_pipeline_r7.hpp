#pragma once
// Metadata is loaded before DATAFLOW. No two streaming readers share m_axi.
// A single writer drains both branches in source order, so the pooled branch
// never waits for the complete full-resolution frame to finish writing.
#include "../ct_pl/conv.cpp"
#include "pool_stream.hpp"

static void pool_or_forward_r7(Stream<W64>& input,Stream<W64>& full,Stream<W64>& pooled,
 const W256* lut,unsigned count,unsigned height,unsigned width,unsigned channels,
 bool enabled,uint32_t& status){
#pragma HLS INLINE off
 if(enabled)ct_pool_fusion::forward_pool(input,full,pooled,lut,count,height,width,channels,status);
 else{
  for(unsigned i=0;i<count;++i){
#pragma HLS PIPELINE II=1
   full.write(input.read());
  }
  status=0;
 }
}

static void write_dual_outputs_r7(Stream<W64>& full,Stream<W64>& pooled,
 W256* output,W256* pool_output,unsigned count,unsigned width,unsigned channels,bool pooling){
#pragma HLS INLINE off
 W256 full_buffer[64],pool_buffer[64];
#pragma HLS BIND_STORAGE variable=full_buffer type=ram_1p impl=lutram
#pragma HLS BIND_STORAGE variable=pool_buffer type=ram_1p impl=lutram
 W256 pool_pack{};
 unsigned consumed=0,full_address=0,pool_address=0,pool_slot=0;
 unsigned group=0,x=0,y=0;
 const unsigned groups=(channels+7)/8;
 while(consumed<count){
  const unsigned remaining=count-consumed;
  const unsigned chunk=remaining<256?remaining:256;
  const unsigned full_words=(chunk+3)/4;
  unsigned full_slot=0,full_words_ready=0,pool_words=0;
  W256 full_pack{};
  for(unsigned i=0;i<chunk;++i){
#pragma HLS PIPELINE II=1
   const W64 value=full.read();
   setlane(full_pack,full_slot*2,int32_t(uint32_t(value)));
   setlane(full_pack,full_slot*2+1,int32_t(uint32_t(value>>32)));
   ++full_slot;
   if(full_slot==4||i+1==chunk){full_buffer[full_words_ready++]=full_pack;full_pack=W256{};full_slot=0;}
   if(pooling){
    if((y&1)&&(x&1)){
     const W64 value_pool=pooled.read();
     setlane(pool_pack,pool_slot*2,int32_t(uint32_t(value_pool)));
     setlane(pool_pack,pool_slot*2+1,int32_t(uint32_t(value_pool>>32)));
     ++pool_slot;
     if(pool_slot==4){pool_buffer[pool_words++]=pool_pack;pool_pack=W256{};pool_slot=0;}
    }
    if(++group==groups){group=0;if(++x==width){x=0;++y;}}
   }
  }
  consumed+=chunk;
  // A partial pooled word is retained across internal chunks. Padding is
  // written only at the actual end of the original transaction.
  if(consumed==count&&pool_slot){pool_buffer[pool_words++]=pool_pack;pool_pack=W256{};pool_slot=0;}
  // Affine contiguous loops separate memory requests from pixel predicates.
  // Both ports remain on the same existing C5 master, with one owner.
  for(unsigned j=0;j<full_words;++j){
#pragma HLS PIPELINE II=1
   output[full_address+j]=full_buffer[j];
  }
  full_address+=full_words;
  for(unsigned j=0;j<pool_words;++j){
#pragma HLS PIPELINE II=1
   pool_output[pool_address+j]=pool_buffer[j];
  }
  pool_address+=pool_words;
 }
}

static void merge_shared_status_r7(uint32_t quant_status,uint32_t pool_status,uint32_t& status){
#pragma HLS INLINE off
 status=quant_status|pool_status;
}

static void quant_stream_cached_r7(Stream<P256>& sums,W256* output,W256* pool_output,
 const W256* parameters,const W256* pool_lut,unsigned count,unsigned channels,
 uint32_t scale_bits,int32_t zero,unsigned height,unsigned width,bool activation,bool pooling,uint32_t& status){
#pragma HLS INLINE off
 Stream<W64> quantized,full,pooled;
#pragma HLS STREAM variable=quantized depth=64
#pragma HLS STREAM variable=full depth=64
#pragma HLS STREAM variable=pooled depth=64
 uint32_t quant_status,pool_status;
 const bool valid_pool=pooling&&ct_pool_fusion::valid(count,height,width,channels);
#pragma HLS DATAFLOW
 quantized_sums(sums,quantized,parameters,count,channels,scale_bits,zero,activation,quant_status);
 pool_or_forward_r7(quantized,full,pooled,pool_lut,count,height,width,channels,pooling,pool_status);
 write_dual_outputs_r7(full,pooled,output,pool_output,count,width,channels,valid_pool);
 merge_shared_status_r7(quant_status,pool_status,status);
}

static void quant_shared_pipeline_r7(Stream<P256>& sums,W256* output,W256* pool_output,
 const W256* parameters,const W256* pool_lut,unsigned count,unsigned channels,
 uint32_t scale_bits,int32_t zero,unsigned height,unsigned width,bool activation,bool pooling,uint32_t& status){
#pragma HLS INLINE off
 W256 parameters_cache[24],pool_lut_cache[8];
#pragma HLS BIND_STORAGE variable=parameters_cache type=ram_1p impl=lutram
#pragma HLS BIND_STORAGE variable=pool_lut_cache type=ram_1p impl=lutram
 const unsigned parameter_words=((channels+7)/8)*2+(activation?8:0);
 for(unsigned i=0;i<parameter_words;++i){
#pragma HLS PIPELINE II=1
  parameters_cache[i]=parameters[i];
 }
 if(pooling&&ct_pool_fusion::valid(count,height,width,channels)){
  for(unsigned i=0;i<8;++i){
#pragma HLS PIPELINE II=1
   pool_lut_cache[i]=pool_lut[i];
  }
 }
 quant_stream_cached_r7(sums,output,pool_output,parameters_cache,pool_lut_cache,count,channels,
     scale_bits,zero,height,width,activation,pooling,status);
}
