#pragma once
#include <cstdint>
struct SmoothPoint { float x,y,z,pad; };
struct SmoothEdge { uint32_t index; float weight; };
struct SmoothFace { uint32_t a,b,c,pad; };
#ifdef SMOOTH_NATIVE
using PointWord=SmoothPoint;using EdgeWord=SmoothEdge;using FaceWord=SmoothFace;
#else
#include <ap_int.h>
using PointWord=ap_uint<128>;using EdgeWord=ap_uint<64>;using FaceWord=ap_uint<128>;
#endif
// All five coords ports keep the same AXI bundle and 128-bit element type.
// Native qualification retains the public pointer ABI; HLS gets explicit requests.
#ifdef SMOOTH_NATIVE
using PointMemory=PointWord*;
#define SM_READ_BEGIN(memory,base,count) ((void)0)
#define SM_READ_WORD(memory,index) ((memory)[index])
#define SM_WRITE_BEGIN(memory,base,count) ((void)0)
#define SM_WRITE_WORD(memory,index,value) ((memory)[index]=(value))
#define SM_WRITE_END(memory) ((void)0)
#else
#include <hls_burst_maxi.h>
using PointMemory=hls::burst_maxi<PointWord>;
#define SM_READ_BEGIN(memory,base,count) ((memory).read_request((base),(count)))
#define SM_READ_WORD(memory,index) ((memory).read())
#define SM_WRITE_BEGIN(memory,base,count) ((memory).write_request((base),(count)))
#define SM_WRITE_WORD(memory,index,value) ((memory).write(value))
#define SM_WRITE_END(memory) ((memory).write_response())
#endif

#if defined(SMOOTH_NATIVE) && defined(_WIN32)
#define SM_EXPORT __declspec(dllexport)
#else
#define SM_EXPORT
#endif
// All coordinate buffers have nv elements; rows has nv+1; edges has nnz.
// Host validates all indices/CSR invariants before DMA. report has 16 uint32s.
extern "C" SM_EXPORT void mesh_smooth(const PointWord* original,
    const uint32_t* rows,const EdgeWord* edges,const uint32_t* frozen,
    const FaceWord* faces,PointMemory current,PointMemory half,
    PointMemory candidate,PointMemory lap,PointMemory next_lap,uint32_t* report,
    uint32_t nv,uint32_t nf,uint32_t nnz,float limit,uint32_t iterations);
