#include "types.hpp"
extern "C" void nav_reader(const Word* input,Stream<Packet>& output,uint32_t count){
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=memory depth=2048 max_read_burst_length=64 num_read_outstanding=8
#pragma HLS INTERFACE axis port=output register_mode=both
#pragma HLS INTERFACE s_axilite port=input bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=count bundle=control offset=0x20
#pragma HLS INTERFACE s_axilite port=return bundle=control
    for(uint32_t i=0;i<count;++i){
#pragma HLS PIPELINE II=1
        output.write(packet(input[i],i,count));
    }
}
extern "C" void nav_writer(Stream<Packet>& input,Word* output,uint32_t count,uint32_t& status){
#pragma HLS INTERFACE axis port=input register_mode=both
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=memory depth=2048 max_write_burst_length=64 num_write_outstanding=8
#pragma HLS INTERFACE s_axilite port=output bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=count bundle=control offset=0x20
#pragma HLS INTERFACE s_axilite port=status bundle=control offset=0x28
#pragma HLS INTERFACE s_axilite port=return bundle=control
    uint32_t errors=0;
    for(uint32_t i=0;i<count;++i){
#pragma HLS PIPELINE II=1
        Packet p=input.read();
        if(p.keep!=~uint64_t(0)||p.strb!=~uint64_t(0)||bool(p.last)!=(i+1==count)||bool(p.user)!=(i==0))errors|=2;
        output[i]=p.data;
    }
    status=errors;
}
extern "C" void nav_route_writer(Stream<Packet>& input,Word* output,uint32_t capacity,uint32_t& status,uint32_t& written){
#pragma HLS INTERFACE axis port=input register_mode=both
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=memory depth=8706 max_write_burst_length=64 num_write_outstanding=8
#pragma HLS INTERFACE s_axilite port=output bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=capacity bundle=control offset=0x20
#pragma HLS INTERFACE s_axilite port=status bundle=control offset=0x28
#pragma HLS INTERFACE s_axilite port=written bundle=control offset=0x30
#pragma HLS INTERFACE s_axilite port=return bundle=control
    uint32_t errors=0,count=0;bool last=false;
    for(uint32_t i=0;i<capacity;++i){
#pragma HLS PIPELINE II=1
        Packet p=input.read();
        if(p.keep!=~uint64_t(0)||p.strb!=~uint64_t(0)||bool(p.user)!=(i==0))errors|=2;
        output[i]=p.data;count=i+1;
        if(p.last){last=true;break;}
    }
    status=errors|uint32_t(!last);written=count;
}
