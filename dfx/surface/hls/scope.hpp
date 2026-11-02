#pragma once
#include <ap_int.h>
#include <ap_axi_sdata.h>
#include <hls_stream.h>
#include <stdint.h>
using ScopeAxis=ap_axiu<512,1,0,0>;
constexpr int SX=256,SY=192,SZ=128;
constexpr int MAX_BLOCKS=4096,SW=MAX_BLOCKS*2;
constexpr int MAP_WORDS=3072,LABEL_WORDS=MAX_BLOCKS/8;
constexpr int SCENE_WORDS=1+MAP_WORDS+SW+LABEL_WORDS;
constexpr unsigned SCENE_MAGIC=0x53554632;
constexpr int MAX_WIDTH=640,MAX_HEIGHT=512,LANES=4,SLOTS=64;
constexpr int OUTSIDE_Q5=-128;
void scope_visual(hls::stream<ScopeAxis>& input,hls::stream<ScopeAxis>& output,
                  unsigned operation,unsigned input_words,unsigned output_words,unsigned& status);
