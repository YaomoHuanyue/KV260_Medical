#include "hu_axis.hpp"

static uint8_t memory_byte(const HuMemoryWord& word, unsigned byte) {
#pragma HLS inline
#ifdef HU_AXIS_NATIVE
    return word[byte];
#else
    return word.range(8 * byte + 7, 8 * byte);
#endif
}

static uint8_t stream_byte(const HuAxisWord& word, unsigned byte) {
#pragma HLS inline
#ifdef HU_AXIS_NATIVE
    return word.data[byte];
#else
    return word.data.range(8 * byte + 7, 8 * byte);
#endif
}

static void put_quantized(HuQuantizedWord& word, unsigned lane, uint8_t value) {
#pragma HLS inline
#ifdef HU_AXIS_NATIVE
    word[lane] = value;
#else
    word.range(8 * lane + 7, 8 * lane) = value;
#endif
}

static void pack_half(HuAxisWord& word, const HuQuantizedWord& values, unsigned half) {
#pragma HLS inline
#ifdef HU_AXIS_NATIVE
    for (unsigned lane = 0; lane < 32; ++lane) {
        word.data[half * 32 + lane] = values[lane];
        if (!half) word.data[32 + lane] = 0;
    }
#else
    if (half) word.data.range(511, 256) = values;
    else {
        word.data = 0;
        word.data.range(255, 0) = values;
    }
#endif
}

static void report(HuMemoryWord* memory, uint32_t error, uint32_t voxels,
                   uint32_t input_words, uint32_t output_words) {
#pragma HLS inline off
    const uint32_t values[8] = {hu_axis::MAGIC, 1, error, voxels,
                               input_words, output_words, voxels, 0};
    report_words: for (unsigned i = 0; i < 2; ++i) {
#pragma HLS pipeline II=1
        HuMemoryWord word{};
        report_bytes: for (unsigned b = 0; b < 16; ++b) {
#pragma HLS unroll
            const uint8_t value = uint8_t(values[i * 4 + b / 4] >> (8 * (b % 4)));
#ifdef HU_AXIS_NATIVE
            word[b] = value;
#else
            word.range(8 * b + 7, 8 * b) = value;
#endif
        }
        memory[hu_axis::LUT_WORDS + i] = word;
    }
}

extern "C" void ct_hu_axis(HuAxisStream& input, HuAxisStream& output,
                            HuMemoryWord* configuration, uint32_t voxels) {
#pragma HLS interface axis port=input register_mode=both
#pragma HLS interface axis port=output register_mode=both
#pragma HLS interface m_axi port=configuration offset=slave bundle=memory depth=90 max_read_burst_length=16 max_write_burst_length=2 num_read_outstanding=1 num_write_outstanding=1
#pragma HLS interface s_axilite port=configuration bundle=control offset=0x10
#pragma HLS interface s_axilite port=voxels bundle=control offset=0x1c
#pragma HLS interface s_axilite port=return bundle=control
    if (voxels > hu_axis::MAX_VOXELS) {
        report(configuration, hu_axis::COUNT, voxels, 0, 0);
        return;
    }
    const uint32_t words = voxels / 32 + (voxels % 32 != 0);
    const uint32_t out_words = voxels / 64 + (voxels % 64 != 0);
    if (!voxels) {
        report(configuration, 0, 0, 0, 0);
        return;
    }
    // Small model configuration only. Bulk CT values never use AXI-MM here.
    uint8_t lut[32][hu_axis::LUT_BYTES];
#pragma HLS array_partition variable=lut complete dim=1
#pragma HLS bind_storage variable=lut type=ram_1p impl=bram
    HuMemoryWord packed{};
    load_lut: for (unsigned i = 0; i < hu_axis::LUT_BYTES; ++i) {
#pragma HLS pipeline II=1
        if (i % 16 == 0) packed = configuration[i / 16];
        const uint8_t value = memory_byte(packed, i % 16);
        load_lanes: for (unsigned lane = 0; lane < 32; ++lane) {
#pragma HLS unroll
            lut[lane][i] = value;
        }
    }
    uint32_t errors = 0;
    HuAxisWord result{};
#ifndef HU_AXIS_NATIVE
    result.data = 0;
#endif
    convert_words: for (uint32_t i = 0; i < words; ++i) {
#pragma HLS pipeline II=1
        const HuAxisWord source = input.read();
        if (uint64_t(source.keep) != ~uint64_t(0)) errors |= hu_axis::KEEP;
        if (uint64_t(source.strb) != ~uint64_t(0)) errors |= hu_axis::STRB;
        if (bool(source.user) != (i == 0)) errors |= hu_axis::USER;
        if (bool(source.last) != (i + 1 == words)) errors |= hu_axis::LAST;
        const unsigned half = i & 1;
        HuQuantizedWord quantized{};
        convert_groups: for (unsigned group = 0; group < 1; ++group) {
#pragma HLS unroll
            convert_lanes: for (unsigned lane = 0; lane < 32; ++lane) {
#pragma HLS unroll
                const unsigned sample = group * 32 + lane;
                const uint32_t position = i * 32 + sample;
                const uint16_t bits = uint16_t(stream_byte(source, sample * 2)) |
                                      (uint16_t(stream_byte(source, sample * 2 + 1)) << 8);
                // Explicit sign extension is identical in native C++ and RTL.
                const int hu = bits < 32768 ? int(bits) : int(bits) - 65536;
                const unsigned index = hu <= -1000 ? 0 : hu >= 400 ? 1400 : unsigned(hu + 1000);
                const uint8_t value = position < voxels ? lut[lane][index] : uint8_t(0);
                put_quantized(quantized, sample, value);
            }
        }
        pack_half(result, quantized, half);
        if (half || i + 1 == words) {
            // The installed static DMA ABI transfers complete 64-byte words.
            // Logical tails are zero padded, not claimed to be tissue voxels.
            result.keep = ~uint64_t(0); result.strb = ~uint64_t(0);
            result.user = i < 2; result.last = i + 1 == words;
            output.write(result);
            result = HuAxisWord{};
#ifndef HU_AXIS_NATIVE
            result.data = 0;
#endif
        }
    }
    report(configuration, errors, voxels, words, out_words);
}
