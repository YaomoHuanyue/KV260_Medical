#pragma once
#include "../axis_kernel.hpp"
#include <cstdio>
#include <cstdlib>

static void fixture_require(bool ok,const char* text){
    if(!ok){std::printf("FULL AXIS fixture failure: %s\n",text);std::exit(91);}
}
// The immutable reference's attempt count determines the required payload
// stimulus only. All numeric decisions and five bank checks remain original.
// Cosimulation can then independently stall both AXIS directions.
static void fixture_smooth(const PointWord* original,const uint32_t* rows,
    const EdgeWord* graph,const uint32_t* frozen,const FaceWord* faces,
    PointMemory current,PointMemory half,PointMemory candidate,PointMemory lap,
    PointMemory next,uint32_t* report,uint32_t nv,uint32_t nf,uint32_t nnz,
    float limit,uint32_t iterations,const uint32_t* expected){
    GraphInput input;GraphOutput output;
    const uint32_t passes=nnz?(fixture_require(expected!=nullptr,"missing independent attempt count"),1+2*expected[4]):0;
    const uint32_t beats=(nnz+7)/8;
    for(uint32_t pass=0;pass<passes;++pass){
        for(uint32_t beat=0;beat<beats;++beat){
            smooth_graph_axis::Word word{};word.data=0;
            for(unsigned lane=0;lane<8;++lane){uint32_t index=beat*8+lane;if(index<nnz)word.data.range(lane*64+63,lane*64)=graph[index];}
            word.keep=word.strb=~uint64_t(0);word.user=beat==0;word.last=beat+1==beats;input.write(word);
        }
    }
    const uint64_t owner=0x8000000012345000ULL;
    mesh_smooth_axis(input,output,original,rows,owner,frozen,faces,current,half,candidate,lap,next,report,nv,nf,nnz,limit,iterations);
    for(uint32_t frame=0;frame<=passes;++frame){
        fixture_require(!output.empty(),"missing REQUEST/FINAL");
        smooth_graph_axis::Word word=output.read();uint32_t f[16];
        for(unsigned j=0;j<16;++j)f[j]=word.data.range(j*32+31,j*32);
        fixture_require(word.keep==~uint64_t(0)&&word.strb==~uint64_t(0)&&word.user==1&&word.last==1,"output framing");
        fixture_require(f[0]==0x31474d53u&&f[1]==1&&f[2]==(frame<passes?1u:2u)&&f[3]==frame&&
            f[4]==nv&&f[5]==nnz&&f[6]==beats&&f[7]==(nv?0u:1u)&&
            (uint64_t(f[8])|(uint64_t(f[9])<<32))==owner&&f[10]==frame*beats&&
            !f[11]&&!f[12]&&!f[13]&&!f[14]&&!f[15],"exact header, address, sequence and consumed beats");
    }
    fixture_require(input.empty()&&output.empty(),"undeclared/unconsumed stream words");
    std::printf("PASS AXIS task nv=%u nnz=%u requests=%u graph_beats=%u FINAL=1 exact\n",nv,nnz,passes,passes*beats);
}
