#pragma once
#include <ap_int.h>
#include <hls_stream.h>
using CompositeWord=ap_uint<128>;
constexpr unsigned COMPOSITE_PIXELS=640*512,COMPOSITE_TILE_WORDS=128;
void depth_composite(const CompositeWord*input,CompositeWord*output,unsigned pixels,unsigned stride_words,
                      unsigned background,unsigned&status,unsigned active_layers=0);
