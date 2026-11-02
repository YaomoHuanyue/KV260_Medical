#include "composite.hpp"
#include "algorithm.hpp"
static void read_planes(const CompositeWord*input,hls::stream<CompositeWord>&stream,unsigned words,unsigned stride,unsigned layers){
#pragma HLS INLINE off
 for(unsigned base=0;base<words;base+=COMPOSITE_TILE_WORDS){
#pragma HLS LOOP_TRIPCOUNT min=1 max=640
  unsigned count=words-base<COMPOSITE_TILE_WORDS?words-base:COMPOSITE_TILE_WORDS;
  for(unsigned plane=0;plane<2*layers;++plane){
   for(unsigned j=0;j<count;++j){
#pragma HLS LOOP_TRIPCOUNT min=4 max=128
#pragma HLS PIPELINE II=1
    stream.write(input[plane*stride+base+j]);
   }
  }
 }
}
static void sort_blend(hls::stream<CompositeWord>&input,hls::stream<CompositeWord>&output,unsigned words,unsigned background,unsigned layers){
#pragma HLS INLINE off
 CompositeWord tile[7][COMPOSITE_TILE_WORDS];
#pragma HLS ARRAY_PARTITION variable=tile complete dim=1
#pragma HLS BIND_STORAGE variable=tile type=ram_2p impl=bram
 for(unsigned base=0;base<words;base+=COMPOSITE_TILE_WORDS){
#pragma HLS LOOP_TRIPCOUNT min=1 max=640
  unsigned count=words-base<COMPOSITE_TILE_WORDS?words-base:COMPOSITE_TILE_WORDS;
  for(unsigned plane=0;plane<2*layers-1;++plane){
   for(unsigned j=0;j<count;++j){
#pragma HLS LOOP_TRIPCOUNT min=4 max=128
#pragma HLS PIPELINE II=1
    tile[plane][j]=input.read();
   }
  }
  for(unsigned j=0;j<count;++j){
#pragma HLS LOOP_TRIPCOUNT min=4 max=128
#pragma HLS PIPELINE II=1
   CompositeWord last=input.read(),result=0;
   for(unsigned pixel=0;pixel<4;++pixel){
#pragma HLS UNROLL
    uint32_t color[4],depth[4];
#pragma HLS ARRAY_PARTITION variable=color complete
#pragma HLS ARRAY_PARTITION variable=depth complete
    for(unsigned layer=0;layer<4;++layer){
#pragma HLS UNROLL
     // Inactive slots are absent, not fetched or allowed to read old tile RAM.
     color[layer]=layer<layers?uint32_t(tile[layer*2][j].range(pixel*32+31,pixel*32)):0;
     depth[layer]=layer<layers?uint32_t((layer==3||layer+1==layers?last:tile[layer*2+1][j]).range(pixel*32+31,pixel*32)):0;
    }
    result.range(pixel*32+31,pixel*32)=depthcompose::pixel(color,depth,background);
   }
   output.write(result);
  }
 }
}
static void write_pixels(hls::stream<CompositeWord>&input,CompositeWord*output,unsigned words){
#pragma HLS INLINE off
 for(unsigned j=0;j<words;++j){
#pragma HLS LOOP_TRIPCOUNT min=4 max=81920
#pragma HLS PIPELINE II=1
  output[j]=input.read();
 }
}
static void render(const CompositeWord*input,CompositeWord*output,unsigned words,unsigned stride,unsigned background,unsigned layers){
#pragma HLS INLINE off
#pragma HLS DATAFLOW
 hls::stream<CompositeWord> planes("planes"),pixels("pixels");
#pragma HLS STREAM variable=planes depth=256
#pragma HLS STREAM variable=pixels depth=256
 read_planes(input,planes,words,stride,layers);sort_blend(planes,pixels,words,background,layers);write_pixels(pixels,output,words);
}
void depth_composite(const CompositeWord*input,CompositeWord*output,unsigned pixels,unsigned stride_words,
                      unsigned background,unsigned&status,unsigned active_layers){
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=memory depth=655360 max_read_burst_length=64 num_read_outstanding=16 max_widen_bitwidth=128
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=memory depth=81920 max_write_burst_length=64 num_write_outstanding=16 max_widen_bitwidth=128
#pragma HLS INTERFACE s_axilite port=input bundle=control
#pragma HLS INTERFACE s_axilite port=output bundle=control
#pragma HLS INTERFACE s_axilite port=pixels bundle=control
#pragma HLS INTERFACE s_axilite port=stride_words bundle=control
#pragma HLS INTERFACE s_axilite port=background bundle=control
#pragma HLS INTERFACE s_axilite port=status bundle=control
#pragma HLS INTERFACE s_axilite port=active_layers bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
 status=0;
 if(!pixels||pixels>COMPOSITE_PIXELS||pixels%16||stride_words<pixels/4||stride_words>COMPOSITE_PIXELS/4||active_layers>4){status=2;return;}
 // A reset/legacy caller retains the previous complete four-layer behavior.
 unsigned layers=active_layers?active_layers:4;
 render(input,output,pixels/4,stride_words,background,layers);
}
