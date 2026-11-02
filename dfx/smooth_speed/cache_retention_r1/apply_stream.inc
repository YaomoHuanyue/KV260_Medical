// R5 keeps the ordered sixteen FP64 accumulators local to the compute actor.
// The successor writes both point output and the final accumulator packet.
// FIFO bindings follow AMD UG1399 bind_storage; dadd latency follows bind_op.
// https://docs.amd.com/r/2025.2-English/ug1399-vitis-hls/pragma-HLS-bind_storage
struct SmoothApplyPacket {SmoothPoint point,mean,initial;uint32_t frozen;};
struct SmoothTotalsPacket {double values[16];};

// No manual coords transaction overlaps another coords port in DATAFLOW.
// Uncached source points are fully staged before the compute/write actors start.
static void read_apply_inputs(const SmoothPoint* staged,const SmoothPoint* cached_points,
    const SmoothPoint* mean,const SmoothPoint* initial,const uint32_t* fixed,
    uint32_t base,uint32_t count,bool cached,int expand,hls::stream<SmoothApplyPacket>& packets){
#pragma HLS inline off
    read_apply_tile:for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
        SmoothApplyPacket packet;
        packet.point=cached?cached_points[(base+j)&32767]:staged[j];
        packet.mean=mean[j];packet.initial=expand?initial[j]:SmoothPoint{0,0,0,0};
        packet.frozen=expand?fixed[j]:0;packets.write(packet);
    }
}
static void calculate_apply_outputs(uint32_t base,uint32_t count,int expand,
    float coefficient,float limit,SmoothTotalsPacket initial_totals,
    hls::stream<SmoothApplyPacket>& packets,hls::stream<SmoothPoint>& outputs,
    hls::stream<SmoothTotalsPacket>& totals_out) {
#pragma HLS inline off
    double partial[16];
#pragma HLS array_partition variable=partial complete
    for(unsigned i=0;i<16;++i) {
#pragma HLS unroll
        partial[i]=initial_totals.values[i];
    }
    calculate_apply_tile:for(uint32_t j=0;j<count;++j) {
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=1024
#pragma HLS dependence variable=partial inter true distance=16
        SmoothApplyPacket packet=packets.read();
        SmoothPoint delta=sub(packet.mean,packet.point),result;
        if(!expand) {
            result=delta;unsigned slot=(base+j)&15;
            double next=partial[slot]+double(norm(delta));
#pragma HLS bind_op variable=next op=dadd impl=fabric latency=12
            partial[slot]=next;
        } else {
            SmoothPoint trial=sub(packet.point,scale(delta,coefficient));
            SmoothPoint displacement=sub(trial,packet.initial);float length=norm(displacement);
            float factor=length>limit?limit/length:1.f;
            trial=add(packet.initial,scale(displacement,factor));
            result=packet.frozen?packet.initial:trial;
        }
        outputs.write(result);
    }
    SmoothTotalsPacket final_totals;
    for(unsigned i=0;i<16;++i) {
#pragma HLS unroll
        final_totals.values[i]=partial[i];
    }
    totals_out.write(final_totals);
}

static void write_apply_outputs(PointMemory current,PointMemory candidate,
    PointMemory lap,PointMemory next_lap,uint32_t output_bank,uint32_t base,uint32_t count,
    hls::stream<SmoothPoint>& outputs,hls::stream<SmoothTotalsPacket>& totals_in,
    double totals[16]) {
#pragma HLS inline off
#pragma HLS array_partition variable=totals complete
    if(output_bank==0) {
    apply_current_groups:for(uint32_t offset=0;offset<count;){
        uint32_t length=bounded_burst_count(base+offset,count-offset);
        SM_WRITE_BEGIN(current,base+offset,length);
        apply_current_words:for(uint32_t k=0;k<length;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=64
            uint32_t j=base+offset+k;
            SM_WRITE_WORD(current,j,pack_point(outputs.read()));
        }
        SM_WRITE_END(current);
        offset+=length;
    }

    }
    else if(output_bank==2) {
    apply_candidate_groups:for(uint32_t offset=0;offset<count;){
        uint32_t length=bounded_burst_count(base+offset,count-offset);
        SM_WRITE_BEGIN(candidate,base+offset,length);
        apply_candidate_words:for(uint32_t k=0;k<length;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=64
            uint32_t j=base+offset+k;
            SM_WRITE_WORD(candidate,j,pack_point(outputs.read()));
        }
        SM_WRITE_END(candidate);
        offset+=length;
    }

    }
    else if(output_bank==3) {
    apply_lap_groups:for(uint32_t offset=0;offset<count;){
        uint32_t length=bounded_burst_count(base+offset,count-offset);
        SM_WRITE_BEGIN(lap,base+offset,length);
        apply_lap_words:for(uint32_t k=0;k<length;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=64
            uint32_t j=base+offset+k;
            SM_WRITE_WORD(lap,j,pack_point(outputs.read()));
        }
        SM_WRITE_END(lap);
        offset+=length;
    }

    }
    else {
    apply_next_lap_groups:for(uint32_t offset=0;offset<count;){
        uint32_t length=bounded_burst_count(base+offset,count-offset);
        SM_WRITE_BEGIN(next_lap,base+offset,length);
        apply_next_lap_words:for(uint32_t k=0;k<length;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=64
            uint32_t j=base+offset+k;
            SM_WRITE_WORD(next_lap,j,pack_point(outputs.read()));
        }
        SM_WRITE_END(next_lap);
        offset+=length;
    }

    }
    SmoothTotalsPacket final_totals=totals_in.read();
    for(unsigned i=0;i<16;++i) {
#pragma HLS unroll
        totals[i]=final_totals.values[i];
    }
}

static void apply_pipeline(PointMemory current,PointMemory half,PointMemory candidate,
    PointMemory lap,PointMemory next_lap,uint32_t source_bank,uint32_t output_bank,
    const SmoothPoint* staged,const SmoothPoint* cached_points,const SmoothPoint* mean,
    const SmoothPoint* initial,const uint32_t* fixed,
    uint32_t base,uint32_t count,bool cached,int expand,float coefficient,float limit,
    SmoothTotalsPacket initial_totals,double totals[16]) {
#pragma HLS inline off
#pragma HLS DATAFLOW
    hls::stream<SmoothApplyPacket> input_packets;
    hls::stream<SmoothPoint> output_packets;
    hls::stream<SmoothTotalsPacket> total_packets;
#pragma HLS stream variable=input_packets depth=64
#pragma HLS stream variable=output_packets depth=64
#pragma HLS stream variable=total_packets depth=2
#pragma HLS bind_storage variable=input_packets type=fifo impl=bram
#pragma HLS bind_storage variable=output_packets type=fifo impl=bram
#pragma HLS bind_storage variable=total_packets type=fifo impl=srl
#pragma HLS aggregate variable=input_packets compact=bit
#pragma HLS aggregate variable=output_packets compact=bit
#pragma HLS aggregate variable=total_packets compact=bit
    read_apply_inputs(staged,cached_points,mean,initial,fixed,base,count,cached,expand,input_packets);
    calculate_apply_outputs(base,count,expand,coefficient,limit,initial_totals,
                            input_packets,output_packets,total_packets);
    write_apply_outputs(current,candidate,lap,next_lap,output_bank,base,count,output_packets,total_packets,totals);
}

static void apply_store_tile(PointMemory current,PointMemory half,PointMemory candidate,
    PointMemory lap,PointMemory next_lap,uint32_t source_bank,uint32_t output_bank,
    const SmoothPoint* cached_points,const SmoothPoint* mean,
    const SmoothPoint* initial,const uint32_t* fixed,
    uint32_t base,uint32_t count,bool cached,int expand,
    float coefficient,float limit,double totals[16]) {
#pragma HLS inline off
#pragma HLS array_partition variable=totals complete
    SmoothPoint staged[256];
#pragma HLS aggregate variable=staged compact=bit
#pragma HLS bind_storage variable=staged type=ram_2p impl=bram
    if(!cached){
        if(source_bank==0)load_local_current(current,staged,base,count);
        else if(source_bank==1)load_local_half(half,staged,base,count);
        else load_local_candidate(candidate,staged,base,count);
    }
    SmoothTotalsPacket initial_totals;
    for(unsigned i=0;i<16;++i) {
#pragma HLS unroll
        initial_totals.values[i]=totals[i];
    }
    apply_pipeline(current,half,candidate,lap,next_lap,source_bank,output_bank,staged,cached_points,mean,initial,fixed,base,count,cached,expand,
                   coefficient,limit,initial_totals,totals);
}
