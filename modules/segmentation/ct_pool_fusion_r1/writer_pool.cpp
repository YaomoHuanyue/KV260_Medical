// Candidate inside the existing C5 DFX RM, not a separately switched pool RM.
// Reuse every original quantizer, LUT, packing and DDR-write helper unchanged.
#include "../ct_pl/conv.cpp"
#include "pool_stream.hpp"

static void quant_pool_pipeline(Stream<P256>& sums,W256* output,W256* pool_output,
 const W256* parameters,const W256* pool_lut,unsigned count,unsigned channels,
 uint32_t scale_bits,int32_t zero,unsigned height,unsigned width,uint32_t& status){
#pragma HLS INLINE off
 Stream<W64> quantized,full,pooled;
 Stream<W256> full_packed,pool_packed;
#pragma HLS STREAM variable=quantized depth=64
#pragma HLS STREAM variable=full depth=64
#pragma HLS STREAM variable=pooled depth=64
#pragma HLS STREAM variable=full_packed depth=64
#pragma HLS STREAM variable=pool_packed depth=64
 const unsigned pool_words=ct_pool_fusion::valid(count,height,width,channels)?count/4:0;
 uint32_t quant_status=0,pool_status=0;
#pragma HLS DATAFLOW
 quantized_sums(sums,quantized,parameters,count,channels,scale_bits,zero,false,quant_status);
 ct_pool_fusion::forward_pool(quantized,full,pooled,pool_lut,count,height,width,channels,pool_status);
 pack_quantized(full,full_packed,count);write_words(full_packed,output,(count+3)/4);
 pack_quantized(pooled,pool_packed,pool_words);write_words(pool_packed,pool_output,(pool_words+3)/4);
 status=quant_status|pool_status;
}

extern "C" void ct_writer_pool(Stream<P256>& sums,W256* output,uint32_t count,uint32_t& status,
 const W256* parameters,uint32_t mode,uint32_t channels,uint32_t output_scale_bits,uint32_t output_zero,
 W256* pool_output,const W256* pool_lut,uint32_t pool_shape){
// pool_shape low16=height, high16=width. count is eight-channel words.
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=memory depth=1024 max_write_burst_length=64
#pragma HLS INTERFACE m_axi port=parameters offset=slave bundle=memory depth=24 max_read_burst_length=16
#pragma HLS INTERFACE m_axi port=pool_output offset=slave bundle=memory depth=1024 max_write_burst_length=64
#pragma HLS INTERFACE m_axi port=pool_lut offset=slave bundle=memory depth=8 max_read_burst_length=8
#pragma HLS INTERFACE axis port=sums register_mode=both
#pragma HLS INTERFACE s_axilite port=output bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=count bundle=control offset=0x20
#pragma HLS INTERFACE s_axilite port=status bundle=control offset=0x28
#pragma HLS INTERFACE s_axilite port=parameters bundle=control offset=0x30
#pragma HLS INTERFACE s_axilite port=mode bundle=control offset=0x40
#pragma HLS INTERFACE s_axilite port=channels bundle=control offset=0x48
#pragma HLS INTERFACE s_axilite port=output_scale_bits bundle=control offset=0x50
#pragma HLS INTERFACE s_axilite port=output_zero bundle=control offset=0x58
#pragma HLS INTERFACE s_axilite port=pool_output bundle=control offset=0x60
#pragma HLS INTERFACE s_axilite port=pool_lut bundle=control offset=0x70
#pragma HLS INTERFACE s_axilite port=pool_shape bundle=control offset=0x80
#pragma HLS INTERFACE s_axilite port=return bundle=control
 if(mode==0)raw_write_pipeline(sums,output,count,status);
 else if((mode==1||mode==2)&&channels>=1&&channels<=64)
  quant_write_pipeline(sums,output,parameters,count,channels,output_scale_bits,int32_t(output_zero),mode==2,status);
 else if(mode==3&&channels>=1&&channels<=64&&count<=ct_pool_fusion::max_words)
  quant_pool_pipeline(sums,output,pool_output,parameters,pool_lut,count,channels,output_scale_bits,
      int32_t(output_zero),pool_shape&65535,pool_shape>>16,status);
 else status=2;
}
