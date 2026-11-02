#include "routed_movers.hpp"

// EDT and route jobs execute serially, so they share one DDR reader/writer pair.
// The inactive AXIS port is neither read nor written and cannot stall the job.
extern "C" void nav_reader_split(const Word* input,Stream<Packet>& edt,Stream<Packet>& route,uint32_t count,uint32_t select){
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=memory depth=2048 max_read_burst_length=64 num_read_outstanding=8
#pragma HLS INTERFACE axis port=edt register_mode=both
#pragma HLS INTERFACE axis port=route register_mode=both
#pragma HLS INTERFACE s_axilite port=input bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=count bundle=control offset=0x20
#pragma HLS INTERFACE s_axilite port=select bundle=control offset=0x28
#pragma HLS INTERFACE s_axilite port=return bundle=control
    for(uint32_t i=0;i<count;++i){
#pragma HLS PIPELINE II=1
        Packet p=packet(input[i],i,count);
        if(select==0)edt.write(p);else route.write(p);
    }
}

extern "C" void nav_writer_merge(Stream<Packet>& edt,Stream<Packet>& route,Word* output,uint32_t capacity,uint32_t& status,uint32_t& written,uint32_t select){
#pragma HLS INTERFACE axis port=edt register_mode=both
#pragma HLS INTERFACE axis port=route register_mode=both
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=memory depth=8706 max_write_burst_length=64 num_write_outstanding=8
#pragma HLS INTERFACE s_axilite port=output bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=capacity bundle=control offset=0x20
#pragma HLS INTERFACE s_axilite port=status bundle=control offset=0x28
#pragma HLS INTERFACE s_axilite port=written bundle=control offset=0x30
#pragma HLS INTERFACE s_axilite port=select bundle=control offset=0x38
#pragma HLS INTERFACE s_axilite port=return bundle=control
    uint32_t errors=0,count=0;bool last=false;
    for(uint32_t i=0;i<capacity;++i){
#pragma HLS PIPELINE II=1
        Packet p;
        if(select==0)p=edt.read();else p=route.read();
        if(p.keep!=~uint64_t(0)||p.strb!=~uint64_t(0)||bool(p.user)!=(i==0))errors|=2;
        output[i]=p.data;count=i+1;
        if(p.last){last=true;break;}
    }
    status=errors|uint32_t(!last);written=count;
}
