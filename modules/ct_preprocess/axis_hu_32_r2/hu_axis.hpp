#pragma once
#include <cstdint>

namespace hu_axis {
constexpr unsigned LUT_BYTES = 1401; // HU -1000 through +400, inclusive.
constexpr unsigned LUT_WORDS = 88;
constexpr unsigned MEMORY_WORDS = 90; // LUT padding, then two report words.
constexpr uint32_t MAX_VOXELS = 1u << 28;
constexpr uint32_t MAGIC = 0x31554851u; // QHU1, little endian.
enum Error : uint32_t { KEEP = 1, STRB = 2, USER = 4, LAST = 8, COUNT = 16 };
}

#ifdef HU_AXIS_NATIVE
#include <array>
struct HuAxisWord {
    std::array<uint8_t, 64> data{};
    uint64_t keep = 0, strb = 0;
    bool user = false, last = false;
};
using HuMemoryWord = std::array<uint8_t, 16>;
using HuQuantizedWord = std::array<uint8_t, 32>;
// Callbacks model the same sequential stream without storing a whole frame.
struct HuAxisStream {
    void* context = nullptr;
    HuAxisWord (*reader)(void*) = nullptr;
    void (*writer)(void*, const HuAxisWord&) = nullptr;
    HuAxisWord read() { return reader(context); }
    void write(const HuAxisWord& value) { writer(context, value); }
};
#else
#include <ap_int.h>
#include <ap_axi_sdata.h>
#include <hls_stream.h>
using HuAxisWord = ap_axiu<512, 1, 0, 0>;
using HuMemoryWord = ap_uint<128>;
using HuQuantizedWord = ap_uint<256>;
using HuAxisStream = hls::stream<HuAxisWord>;
#endif

extern "C" void ct_hu_axis(HuAxisStream& input, HuAxisStream& output,
                            HuMemoryWord* configuration, uint32_t voxels);
