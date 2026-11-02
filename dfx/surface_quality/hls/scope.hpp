#pragma once
#include <ap_int.h>
#include <ap_axi_sdata.h>
#include <hls_stream.h>
#include <stdint.h>
using ScopeAxis=ap_axiu<512,1,0,0>;
constexpr int SX=384,SY=320,SZ=512;
constexpr int MAX_BLOCKS=10240,SW=MAX_BLOCKS*2;
constexpr int FIELD_WORDS=(MAX_BLOCKS*8+4)/5;
constexpr int DIR_WORDS=512,LEAF_WORDS=2048,MAX_PAGES=128;
constexpr int SCENE_WORDS=1+DIR_WORDS+LEAF_WORDS+SW;
constexpr unsigned SCENE_MAGIC=0x53514733;
constexpr int MAX_WIDTH=640,MAX_HEIGHT=512,LANES=4,SLOTS=64;
constexpr int OUTSIDE_Q5=-128;
void scope_visual(hls::stream<ScopeAxis>& input,hls::stream<ScopeAxis>& output,
                  unsigned operation,unsigned input_words,unsigned output_words,unsigned& status);
