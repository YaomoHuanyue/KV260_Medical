#pragma once
#include "graph_task.hpp"
extern "C" void mesh_smooth_axis(GraphInput& input,GraphOutput& output,
    const PointWord* original,const uint32_t* rows,uint64_t graph_address,const uint32_t* frozen,
    const FaceWord* faces,PointMemory current,PointMemory half,PointMemory candidate,
    PointMemory lap,PointMemory next_lap,uint32_t* report,uint32_t nv,uint32_t nf,
    uint32_t nnz,float limit,uint32_t iterations);
