#pragma once
#include <cstdint>

// Input: contiguous uint8 binary volume in Z,Y,X order. Output: triangle soup,
// three uint64 words per triangle. Each word holds XYZ in unsigned Q1:
// bits 0..15 X*2, 16..31 Y*2, 32..47 Z*2; upper 16 bits zero.
// Physical image spacing/origin/direction are applied by the PS.
static const unsigned MC_MAX_DIM = 512;
enum McStatus { MC_OK = 0, MC_BAD_DIMENSIONS = 1, MC_OVERFLOW = 2,
                MC_NON_BINARY = 4, MC_BAD_MODE = 8 };

#if defined(MC_NATIVE) && defined(_WIN32)
#define MC_EXPORT __declspec(dllexport)
#else
#define MC_EXPORT
#endif
extern "C" MC_EXPORT void binary_mc(
    const uint8_t* volume, uint64_t* vertices,
    uint32_t nx, uint32_t ny, uint32_t nz,
    uint32_t capacity_triangles, uint32_t count_only,
    uint32_t& triangles_required, uint32_t& triangles_written, uint32_t& status);
