#include "../shared_pipeline_r6.hpp"

extern "C" void ct_writer_pool(Stream<P256>& sums,W256* output,uint32_t count,uint32_t& status,
 const W256* parameters,uint32_t mode,uint32_t channels,uint32_t output_scale_bits,uint32_t output_zero,
 W256* pool_output,const W256* pool_lut,uint32_t pool_shape){
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=memory depth=1024 max_read_burst_length=16 max_write_burst_length=64 num_read_outstanding=2 num_write_outstanding=2
#pragma HLS INTERFACE m_axi port=parameters offset=slave bundle=memory depth=24 max_read_burst_length=16 max_write_burst_length=64 num_read_outstanding=2 num_write_outstanding=2
#pragma HLS INTERFACE m_axi port=pool_output offset=slave bundle=memory depth=1024 max_read_burst_length=16 max_write_burst_length=64 num_read_outstanding=2 num_write_outstanding=2
#pragma HLS INTERFACE m_axi port=pool_lut offset=slave bundle=memory depth=8 max_read_burst_length=16 max_write_burst_length=64 num_read_outstanding=2 num_write_outstanding=2
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
 else if((mode==1||mode==2||mode==3)&&channels>=1&&channels<=64&&
          (mode!=3||count<=ct_pool_fusion::max_words)){
  quant_shared_pipeline_r6(sums,output,pool_output,parameters,pool_lut,count,channels,output_scale_bits,
      int32_t(output_zero),pool_shape&65535,pool_shape>>16,mode==2,mode==3,status);
 }
 else status=2;
}
