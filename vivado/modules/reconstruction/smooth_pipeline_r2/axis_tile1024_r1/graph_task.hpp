#pragma once
#include "mesh_smooth.hpp"
#ifdef SMOOTH_NATIVE
#define SM_GRAPH_AXIS_NATIVE
#endif
#include "axis_graph_reader.hpp"

using GraphInput=smooth_graph_axis::Stream;
#ifdef SMOOTH_NATIVE
struct GraphOutput {
    void* context;
    void (*writer)(void*,const smooth_graph_axis::Word&);
    void write(const smooth_graph_axis::Word& value){writer(context,value);}
};
#else
using GraphOutput=smooth_graph_axis::Stream;
#endif

struct GraphTask {
    GraphInput& input;GraphOutput& output;
    uint32_t nv,nnz,sequence,errors,total_beats;
    uint64_t graph_address;
    GraphTask(GraphInput& i,GraphOutput& o,uint32_t vertices,uint32_t edges,uint64_t address)
        :input(i),output(o),nv(vertices),nnz(edges),sequence(0),errors(0),total_beats(0),graph_address(address){}
    void header(uint32_t kind){
#pragma HLS inline
        smooth_graph_axis::Word word{};
#ifndef SMOOTH_NATIVE
        word.data=0;
#endif
        uint32_t fields[16]={0x31474d53u,1,kind,sequence,nv,nnz,(nnz+7)/8,errors,
            uint32_t(graph_address),uint32_t(graph_address>>32),total_beats,0,0,0,0,0};
        for(unsigned lane=0;lane<8;++lane){
#pragma HLS unroll
            const uint64_t value=uint64_t(fields[lane*2])|(uint64_t(fields[lane*2+1])<<32);
#ifdef SMOOTH_NATIVE
            word.data[lane]=value;
#else
            word.data.range(lane*64+63,lane*64)=value;
#endif
        }
        word.keep=word.strb=~uint64_t(0);word.user=1;word.last=1;
        output.write(word);
    }
    void request(){
#pragma HLS inline
        if(nnz){header(1);++sequence;}
    }
    void final(){
#pragma HLS inline
        header(2);
    }
};

class GraphPass {
    GraphTask& task;
    smooth_graph_axis::Reader reader;
    smooth_graph_axis::Quarter quarter;
    uint8_t lane;uint32_t delivered;
public:
    GraphPass(GraphTask& t):task(t),reader(t.input,t.nv,t.nnz),quarter{},lane(0),delivered(0){
#pragma HLS inline
        task.request();
    }
    smooth_graph_axis::Quarter next_up_to4(uint32_t expected_index,uint32_t maximum){
#pragma HLS inline
        if(expected_index!=delivered)task.errors|=256;
        if(lane==quarter.count){quarter=reader.next4();lane=0;}
        smooth_graph_axis::Quarter result{};
#pragma HLS array_partition variable=result.edges complete
        uint32_t available=quarter.count-lane;
        result.count=uint8_t(maximum<available?maximum:available);
        if(!result.count){
            // Malformed CSR must still advance a bounded loader and report an
            // error, rather than loop forever after the declared input drains.
            result.count=uint8_t(maximum<4?maximum:4);task.errors|=256;
        }else{
            copy_quarter:for(unsigned j=0;j<4;++j){
#pragma HLS unroll
                if(j<result.count)result.edges[j]=quarter.edges[lane+j];
            }
            lane+=result.count;
        }
        delivered+=result.count;return result;
    }
    SmoothEdge next(uint32_t expected_index){
#pragma HLS inline
        if(expected_index!=delivered)task.errors|=256;
        if(lane==quarter.count){quarter=reader.next4();lane=0;}
        uint64_t packed=0;
        if(lane<quarter.count)packed=quarter.edges[lane++];
        else task.errors|=256;
        ++delivered;
        union {uint32_t u;float f;} weight;weight.u=uint32_t(packed>>32);
        return {uint32_t(packed),weight.f};
    }
    void finish(){
#pragma HLS inline
        if(delivered!=task.nnz)task.errors|=256;
        // Drain the declared transfer even when a malformed CSR/control path
        // consumes fewer records. The host rejects every error FINAL frame.
        while(!reader.done()){
#pragma HLS pipeline II=1
            reader.next4();
        }
        task.errors|=reader.status();task.total_beats+=reader.consumed_beats();
    }
};
