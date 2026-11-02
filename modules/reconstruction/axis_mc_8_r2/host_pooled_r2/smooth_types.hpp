#pragma once
#include <cstdint>
struct SmoothPoint { float x,y,z,pad; };
struct SmoothEdge { uint32_t index; float weight; };
struct SmoothFace { uint32_t a,b,c,pad; };
#if defined(SMOOTH_NATIVE) && defined(_WIN32)
#define SM_EXPORT __declspec(dllexport)
#else
#define SM_EXPORT
#endif
// All coordinate buffers have nv elements; rows has nv+1; edges has nnz.
// Host validates all indices/CSR invariants before DMA. report has 16 uint32s.
extern "C" SM_EXPORT void mesh_smooth(const SmoothPoint* original,
    const uint32_t* rows,const SmoothEdge* edges,const uint32_t* frozen,
    const SmoothFace* faces,SmoothPoint* current,SmoothPoint* half,
    SmoothPoint* candidate,SmoothPoint* lap,SmoothPoint* next_lap,uint32_t* report,
    uint32_t nv,uint32_t nf,uint32_t nnz,float limit,uint32_t iterations);
