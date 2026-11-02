#pragma once
#include <cstdint>

namespace mc_axis {
constexpr uint32_t MAX_DIM = 512;
constexpr uint32_t MAX_INPUT_WORDS = (MAX_DIM * MAX_DIM * MAX_DIM) / 64;
constexpr uint32_t MAX_TRIANGLES = 9 * (MAX_DIM-1) * (MAX_DIM-1) * (MAX_DIM-1);
constexpr uint32_t MAGIC = 0x3141434d; // MCA1, little endian.
enum Error : uint32_t {
    BAD_DIMENSIONS=1, OVERFLOW=2, NON_BINARY=4, BAD_MODE=8,
    COUNT_MISMATCH=16, KEEP=32, STRB=64, USER=128, LAST=256,
    FRAME_LENGTH=512, INPUT_LIMIT=1024, EXPECTED_LIMIT=2048
};
}

#ifdef MC_AXIS_NATIVE
#include <array>
struct McAxisWord {
    std::array<uint8_t,64> data{};
    uint64_t keep=0, strb=0;
    bool user=false, last=false;
};
// Callbacks let the native model consume a whole volume without an AXIS copy.
struct McAxisStream {
    void* context=nullptr;
    McAxisWord (*reader)(void*)=nullptr;
    void (*writer)(void*,const McAxisWord&)=nullptr;
    McAxisWord read() { return reader(context); }
    void write(const McAxisWord& v) { writer(context,v); }
};
#else
#include <ap_int.h>
#include <ap_axi_sdata.h>
#include <hls_stream.h>
using McAxisWord=ap_axiu<512,1,0,0>;
using McAxisStream=hls::stream<McAxisWord>;
#endif

// Count pass: one footer beat. Produce pass: ceil(3*min(capacity,expected)/8)
// vertex beats followed by one footer. Full KEEP/STRB, zero logical tail.
// Invalid scalar configurations drain min(input_words,MAX_INPUT_WORDS) beats
// and return just one footer. The host must validate scalars before DMA.
extern "C" void binary_mc_axis(McAxisStream& input, McAxisStream& output,
    uint32_t nx,uint32_t ny,uint32_t nz,uint32_t capacity_triangles,
    uint32_t count_only,uint32_t expected_triangles,uint32_t input_words);
