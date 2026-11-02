#include "stream_types.hpp"

static void read_words(const W256* input,Stream<W256>& words,unsigned count){
#pragma HLS INLINE off
 for(unsigned i=0;i<(count+3)/4;i++){
#pragma HLS PIPELINE II=1
  words.write(input[i]);
 }
}

static void reader_packets(Stream<W256>& words,Stream<P256>& pixels,unsigned height,unsigned width,unsigned cin,unsigned kernel){
#pragma HLS INLINE off
 unsigned groups=(cin+7)/8,count=height*width*groups;
 if(kernel==1){
  for(unsigned i=0;i<(count+3)/4;i++){
#pragma HLS PIPELINE II=1
   P256 p;p.data=words.read();p.keep=valid_bytes(count-i*4);p.strb=p.keep;
   p.last=(i+1==(count+3)/4);pixels.write(p);
  }
 }else{
  // Spatial windows retain their proven 64-bit ordering. The DDR fetch is wide;
  // each padded spatial beat has only its low eight bytes enabled.
  unsigned index=0;W256 cached{};
  for(unsigned y=0;y<height+2;y++)for(unsigned x=0;x<width+2;x++)for(unsigned g=0;g<groups;g++){
#pragma HLS PIPELINE II=1
   P256 p;p.data=W256{};p.keep=255;p.strb=255;
   if(y>=1&&y<=height&&x>=1&&x<=width){
    if(index%4==0)cached=words.read();
    setword64(p.data,0,word64(cached,index%4));index++;
   }
   p.last=(y==height+1&&x==width+1&&g+1==groups);pixels.write(p);
  }
 }
}

static void reader_pipeline(const W256* input,Stream<P256>& pixels,unsigned height,unsigned width,unsigned cin,unsigned kernel){
#pragma HLS INLINE off
 Stream<W256> words;
#pragma HLS STREAM variable=words depth=64
#pragma HLS DATAFLOW
 read_words(input,words,height*width*((cin+7)/8));
 reader_packets(words,pixels,height,width,cin,kernel);
}

extern "C" void ct_reader(const W256* input,Stream<P256>& pixels,uint32_t height,uint32_t width,uint32_t cin,uint32_t kernel){
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=memory depth=1024 max_read_burst_length=64
#pragma HLS INTERFACE axis port=pixels register_mode=both
#pragma HLS INTERFACE s_axilite port=input bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=height bundle=control offset=0x20
#pragma HLS INTERFACE s_axilite port=width bundle=control offset=0x28
#pragma HLS INTERFACE s_axilite port=cin bundle=control offset=0x30
#pragma HLS INTERFACE s_axilite port=kernel bundle=control offset=0x38
#pragma HLS INTERFACE s_axilite port=return bundle=control
 if(!valid_shape(height,width,cin,1,kernel))return;
 reader_pipeline(input,pixels,height,width,cin,kernel);
}

struct PointPixel {W64 words[8];};

static void point_pixels(Stream<P256>& pixels,Stream<PointPixel>& packed,unsigned count,unsigned groups,uint32_t& status){
#pragma HLS INLINE off
 PointPixel block{};
#pragma HLS ARRAY_PARTITION variable=block.words complete
 unsigned errors=0,total=count*groups;W256 cached{};
 if(groups==1||groups==2||groups==4){
  unsigned offset=0,consumed=0;
  point_wide_small:for(unsigned i=0;i<count;i++){
#pragma HLS PIPELINE II=1
   if(offset==0){
    P256 p=pixels.read();unsigned mask=valid_bytes(total-consumed);
    if(p.keep!=mask||p.strb!=mask||bool(p.last)!=(total-consumed<=4))errors|=2;
    cached=p.data;consumed+=4;
   }
   for(unsigned j=0;j<4;j++){
#pragma HLS UNROLL
    block.words[j]=j<groups?word64(cached,offset+j):W64(0);
   }
   packed.write(block);offset=(offset+groups)%4;
  }
 }else if(groups==8){
  point_wide_large:for(unsigned i=0;i<count*2;i++){
#pragma HLS PIPELINE II=1
   P256 p=pixels.read();
   if(p.keep!=0xffffffffu||p.strb!=0xffffffffu||bool(p.last)!=(i+1==count*2))errors|=2;
   for(unsigned j=0;j<4;j++){
#pragma HLS UNROLL
    block.words[(i%2)*4+j]=word64(p.data,j);
   }
   if(i%2==1)packed.write(block);
  }
 }else{
  // Arbitrary channel counts retain a general, frame-exact fallback.
  unsigned group=0;
  point_wide_tail:for(unsigned i=0;i<total;i++){
#pragma HLS PIPELINE II=1
   if(i%4==0){
    P256 p=pixels.read();unsigned mask=valid_bytes(total-i);
    if(p.keep!=mask||p.strb!=mask||bool(p.last)!=(total-i<=4))errors|=2;
    cached=p.data;
   }
   block.words[group]=word64(cached,i%4);
   if(group+1==groups){packed.write(block);group=0;}else group++;
  }
 }
 status=errors;
}

static void point_macs(const W256 cache[8][144],Stream<PointPixel>& pixels,Stream<P256>& sums,unsigned count,unsigned cin,unsigned cout){
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=cache complete dim=1
 const unsigned ig=(cin+3)/4,groups32=(cin+31)/32,og=(cout+7)/8,steps=og*groups32;
 PointPixel pixel{};
#pragma HLS ARRAY_PARTITION variable=pixel.words complete
 int32_t acc[8]={};
#pragma HLS ARRAY_PARTITION variable=acc complete
 unsigned step=0,g=0,o=0;
 // One pipeline spans the complete image. AXIS backpressure controls the rate.
 for(unsigned i=0;i<count*steps;i++){
#pragma HLS PIPELINE II=1
  if(step==0)pixel=pixels.read();
  W256 weights8[8];
#pragma HLS ARRAY_PARTITION variable=weights8 complete
  for(unsigned bank=0;bank<8;bank++){
#pragma HLS UNROLL
   weights8[bank]=(g*8+bank<ig)?cache[bank][step]:W256{};
  }
  P256 p;p.keep=0xffffffffu;p.strb=0xffffffffu;p.last=(i+1==count*steps);
  for(unsigned oc=0;oc<8;oc++){
#pragma HLS UNROLL
   int32_t partial[8]={};
#pragma HLS ARRAY_PARTITION variable=partial complete
   for(unsigned j=0;j<32;j++){
#pragma HLS UNROLL
    unsigned c=g*32+j;
    int8_t a=c<cin?byte64(pixel.words[c/8],c%8):int8_t(0);
    int8_t b=byte256(weights8[j/4],oc*4+j%4);
    int16_t product=a*b;
#pragma HLS BIND_OP variable=product op=mul impl=dsp
    partial[j/4]+=product;
   }
   int32_t dot=((partial[0]+partial[1])+(partial[2]+partial[3]))+((partial[4]+partial[5])+(partial[6]+partial[7]));
   int32_t value=(g==0?int32_t(0):acc[oc])+dot;acc[oc]=value;
   setlane(p.data,oc,o*8+oc<cout?value:int32_t(0));
  }
  if(g+1==groups32)sums.write(p);
  if(step+1==steps){step=0;g=0;o=0;}
  else {step++;if(g+1==groups32){g=0;o++;}else g++;}
 }
}

static void point_pipeline(const W256 cache[8][144],Stream<P256>& pixels,Stream<P256>& sums,unsigned count,unsigned cin,unsigned cout,uint32_t& status){
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=cache complete dim=1
 Stream<PointPixel> packed;
#pragma HLS STREAM variable=packed depth=16
#pragma HLS DATAFLOW
 point_pixels(pixels,packed,count,(cin+7)/8,status);
 point_macs(cache,packed,sums,count,cin,cout);
}


struct SpatialWindow {W64 words[9][8];};
struct SpatialWindowHalf {W64 words[9][4];};
struct SpatialOutput {W256 halves[2][2];};

static void spatial_windows(Stream<P256>& pixels,Stream<SpatialWindowHalf>& low0,Stream<SpatialWindowHalf>& high0,Stream<SpatialWindowHalf>& low1,Stream<SpatialWindowHalf>& high1,unsigned height,unsigned width,unsigned cin,uint32_t& status){
#pragma HLS INLINE off
 W64 line0[4096],line1[4096];
#pragma HLS BIND_STORAGE variable=line0 type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=line1 type=ram_2p impl=bram
 W64 win[3][3][8]={};
#pragma HLS ARRAY_PARTITION variable=win complete
 unsigned cg=(cin+7)/8,ph=height+2,pw=width+2,errors=0,pixel=0,pixel_lane=0;
 SpatialWindowHalf lo[2]={},hi[2]={};
#pragma HLS ARRAY_PARTITION variable=lo complete
#pragma HLS ARRAY_PARTITION variable=hi complete
 unsigned y=0,x=0,g=0;
 spatial_window_input:for(unsigned index=0;index<ph*pw*cg;index++){
#pragma HLS PIPELINE II=1
   P256 packet=pixels.read();P64 p;p.data=word64(packet.data,0);p.keep=packet.keep;p.strb=packet.strb;p.last=packet.last;
   if(packet.keep!=255||packet.strb!=255||bool(p.last)!=(y==ph-1&&x==pw-1&&g==cg-1))errors|=2;
   W64 old0=0,old1=0;
   if(x>=1&&x<width+1){
    unsigned pos=(x-1)*8+g;
    if(y>=2)old0=line0[pos];
    if(y>=1)old1=line1[pos];
    line0[pos]=old1;line1[pos]=p.data;
   }
   for(unsigned r=0;r<3;r++){
#pragma HLS UNROLL
    win[r][0][g]=win[r][1][g];win[r][1][g]=win[r][2][g];
   }
   win[0][2][g]=old0;win[1][2][g]=old1;win[2][2][g]=p.data;
  if(g+1==cg && y>=2&&x>=2){
   for(unsigned n=0;n<36;n++){
#pragma HLS UNROLL
    lo[pixel_lane].words[n/4][n%4]=win[n/12][(n/4)%3][n%4];
    hi[pixel_lane].words[n/4][n%4]=win[n/12][(n/4)%3][n%4+4];
   }
   if(pixel_lane==1 || pixel+1==height*width){low0.write(lo[0]);high0.write(hi[0]);low1.write(lo[1]);high1.write(hi[1]);}
   pixel_lane=(pixel_lane==1)?0:pixel_lane+1;
   pixel++;
  }
  if(g+1==cg){g=0;if(x+1==pw){x=0;y++;}else x++;}else g++;
 }
 status=errors;
}

// Separate arithmetic pipelines keep each HLS scheduling problem bounded.
template<unsigned Lane>
static void spatial_dot(const int8_t input[16],const int8_t weights[16][16],int32_t dot[16]){
#pragma HLS INLINE off
#pragma HLS PIPELINE II=1
#pragma HLS ARRAY_PARTITION variable=input complete
#pragma HLS ARRAY_PARTITION variable=weights complete dim=0
#pragma HLS ARRAY_PARTITION variable=dot complete
 for(unsigned oc=0;oc<16;oc++){
#pragma HLS UNROLL
  int32_t partial[4]={};
#pragma HLS ARRAY_PARTITION variable=partial complete
  for(unsigned j=0;j<16;j++){
#pragma HLS UNROLL
   int16_t product=input[j]*weights[oc][j];
#pragma HLS BIND_OP variable=product op=mul impl=dsp
   partial[j/4]+=product;
  }
  dot[oc]=(partial[0]+partial[1])+(partial[2]+partial[3]);
 }
}

static void spatial_macs(const W256 cache[8][144],Stream<SpatialWindowHalf>& low0,Stream<SpatialWindowHalf>& high0,Stream<SpatialWindowHalf>& low1,Stream<SpatialWindowHalf>& high1,Stream<SpatialOutput>& results,unsigned count,unsigned cin,unsigned cout){
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=cache complete dim=1
 const unsigned ig=(cin+3)/4,groups32=(cin+31)/32,groups16=(cin+15)/16,og16=(cout+15)/16,steps=og16*9*groups16;
 SpatialWindow window[2]={};
#pragma HLS ARRAY_PARTITION variable=window complete
 int32_t acc[2][16]={};
#pragma HLS ARRAY_PARTITION variable=acc complete
 unsigned step=0,g=0,k=0,o=0;
 // Two adjacent raster pixels share each weight read. One continuous pipeline
 // computes both windows; the output stage restores the original pixel order.
 spatial_compute:for(unsigned i=0;i<((count+1)/2)*steps;i++){
#pragma HLS PIPELINE II=1
  if(step==0){
   SpatialWindowHalf lo[2]={low0.read(),low1.read()},hi[2]={high0.read(),high1.read()};
   for(unsigned px=0;px<2;px++)for(unsigned n=0;n<72;n++){
#pragma HLS UNROLL
    window[px].words[n/8][n%8]=(n%8<4)?lo[px].words[n/8][n%4]:hi[px].words[n/8][n%4];
   }
  }
  W256 weights[2][8];
#pragma HLS ARRAY_PARTITION variable=weights complete
  for(unsigned half=0;half<2;half++)for(unsigned bank=0;bank<8;bank++){
#pragma HLS UNROLL
   unsigned row=((o*2+half)*9+k)*groups32+g/2;
   weights[half][bank]=(o*16+half*8<cout && (g/2)*8+bank<ig)?cache[bank][row]:W256{};
  }
  int8_t inputs[2][16],coefficients[16][16];int32_t dots[2][16];
#pragma HLS ARRAY_PARTITION variable=inputs complete dim=0
#pragma HLS ARRAY_PARTITION variable=coefficients complete dim=0
#pragma HLS ARRAY_PARTITION variable=dots complete dim=0
  for(unsigned j=0;j<16;j++){
#pragma HLS UNROLL
   unsigned c=g*16+j;
   for(unsigned px=0;px<2;px++){
#pragma HLS UNROLL
    inputs[px][j]=c<cin?byte64(window[px].words[k][c/8],c%8):int8_t(0);
   }
   for(unsigned oc=0;oc<16;oc++){
#pragma HLS UNROLL
    coefficients[oc][j]=byte256(weights[oc/8][(g%2)*4+j/4],(oc%8)*4+j%4);
   }
  }
  spatial_dot<0>(inputs[0],coefficients,dots[0]);
  spatial_dot<1>(inputs[1],coefficients,dots[1]);
  SpatialOutput result;
  for(unsigned px=0;px<2;px++)for(unsigned oc=0;oc<16;oc++){
#pragma HLS UNROLL
   int32_t value=(k==0&&g==0?int32_t(0):acc[px][oc])+dots[px][oc];acc[px][oc]=value;
   setlane(result.halves[px][oc/8],oc%8,o*16+oc<cout?value:int32_t(0));
  }
  if(k==8&&g+1==groups16)results.write(result);
  if(step+1==steps){step=0;g=0;k=0;o=0;}
  else {step++;if(g+1<groups16)g++;else{g=0;if(k<8)k++;else{k=0;o++;}}}
 }
}

static void spatial_output(Stream<SpatialOutput>& results,Stream<P256>& sums,unsigned count,unsigned cout){
#pragma HLS INLINE off
 unsigned og=(cout+7)/8,group=0,px=0;SpatialOutput result{};
 W256 pending[1][8];
#pragma HLS ARRAY_PARTITION variable=pending complete dim=0
 spatial_serialize:for(unsigned i=0;i<count*og;i++){
#pragma HLS PIPELINE II=1
  W256 value;
  if(px==0){
   if(group%2==0){
    result=results.read();
    for(unsigned j=0;j<1;j++){
#pragma HLS UNROLL
     pending[j][group]=result.halves[j+1][0];
     if(group+1<og)pending[j][group+1]=result.halves[j+1][1];
    }
   }
   value=result.halves[0][group%2];
  }else value=pending[px-1][group];
  P256 p;p.data=value;p.keep=0xffffffffu;p.strb=0xffffffffu;p.last=(i+1==count*og);sums.write(p);
  if(group+1==og){group=0;px=(px==1)?0:px+1;}else group++;
 }
}

static void spatial_pipeline(const W256 cache[8][144],Stream<P256>& pixels,Stream<P256>& sums,unsigned height,unsigned width,unsigned cin,unsigned cout,unsigned count,uint32_t& status){
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=cache complete dim=1
 Stream<SpatialWindowHalf> low0,high0,low1,high1;Stream<SpatialOutput> results;
#pragma HLS STREAM variable=low0 depth=2
#pragma HLS STREAM variable=low1 depth=2
#pragma HLS STREAM variable=high0 depth=2
#pragma HLS STREAM variable=high1 depth=2
#pragma HLS STREAM variable=results depth=4
#pragma HLS DATAFLOW
 spatial_windows(pixels,low0,high0,low1,high1,height,width,cin,status);
 spatial_macs(cache,low0,high0,low1,high1,results,count,cin,cout);
 spatial_output(results,sums,count,cout);
}

extern "C" void ct_conv(const W256* weights,Stream<P256>& pixels,Stream<P256>& sums,uint32_t height,uint32_t width,uint32_t cin,uint32_t cout,uint32_t kernel,uint32_t& status){
#pragma HLS INTERFACE m_axi port=weights offset=slave bundle=memory depth=1152 max_read_burst_length=64
#pragma HLS INTERFACE axis port=pixels register_mode=both
#pragma HLS INTERFACE axis port=sums register_mode=both
#pragma HLS INTERFACE s_axilite port=weights bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=height bundle=control offset=0x20
#pragma HLS INTERFACE s_axilite port=width bundle=control offset=0x28
#pragma HLS INTERFACE s_axilite port=cin bundle=control offset=0x30
#pragma HLS INTERFACE s_axilite port=cout bundle=control offset=0x38
#pragma HLS INTERFACE s_axilite port=kernel bundle=control offset=0x40
#pragma HLS INTERFACE s_axilite port=status bundle=control offset=0x48
#pragma HLS INTERFACE s_axilite port=return bundle=control
 status=0;if(!valid_shape(height,width,cin,cout,kernel)){status=1;return;}
 // Eight dual-port banks feed 8x32 pointwise or two-pixel 16x16 spatial MACs.
 // DDR weight format stays unchanged: 8 outputs x 4 inputs per 256-bit word.
 W256 cache[8][144];
#pragma HLS ARRAY_PARTITION variable=cache complete dim=1
#pragma HLS BIND_STORAGE variable=cache type=ram_2p impl=bram
 unsigned ig=(cin+3)/4,og=(cout+7)/8,cg=(cin+7)/8,groups32=(cin+31)/32;
 unsigned steps=og*kernel*kernel*groups32;
 // Keep DDR accesses strictly sequential so HLS can issue AXI bursts.
 unsigned inputWord=0,rowBase=0;
 for(unsigned word=0;word<og*kernel*kernel*ig;word++){
#pragma HLS PIPELINE II=1
  cache[inputWord%8][rowBase+inputWord/8]=weights[word];
  if(inputWord+1==ig){inputWord=0;rowBase+=groups32;}else inputWord++;
 }
 if(kernel==1){point_pipeline(cache,pixels,sums,height*width,cin,cout,status);return;}
 spatial_pipeline(cache,pixels,sums,height,width,cin,cout,height*width,status);
}

static float word_float(uint32_t bits){
#pragma HLS INLINE
 union {uint32_t u;float f;} value;value.u=bits;return value.f;
}

static int8_t round_even_int8(float value,int32_t zero){
#pragma HLS INLINE
 union {uint32_t u;float f;} raw;raw.f=value;
 int exponent=int((raw.u>>23)&255)-127;
 int rounded=0;
 if(exponent>=9)return (raw.u>>31)?int8_t(-128):int8_t(127);
 if(exponent>=-1){
  unsigned shift=unsigned(23-exponent),significand=(raw.u&0x7fffff)|0x800000;
  unsigned base=significand>>shift,remainder=significand&((1u<<shift)-1),half=1u<<(shift-1);
  base+=(remainder>half || (remainder==half&&(base&1)));
  rounded=(raw.u>>31)?-int(base):int(base);
 }
 rounded+=zero;
 return int8_t(rounded<-128?-128:(rounded>127?127:rounded));
}

static void raw_sums(Stream<P256>& sums,Stream<W256>& words,unsigned count,uint32_t& status){
#pragma HLS INLINE off
 unsigned errors=0;
 for(unsigned i=0;i<count;i++){
#pragma HLS PIPELINE II=1
  P256 p=sums.read();if(p.keep!=0xffffffffu||p.strb!=0xffffffffu||bool(p.last)!=(i+1==count))errors|=1;
  words.write(p.data);
 }
 status=errors;
}

static void quantized_sums(Stream<P256>& sums,Stream<W64>& words,const W256* parameters,unsigned count,unsigned channels,uint32_t scale_bits,int32_t zero,bool activation_lut,uint32_t& status){
#pragma HLS INLINE off
 int32_t bias[64];float scale[64];
#pragma HLS ARRAY_PARTITION variable=bias cyclic factor=8
#pragma HLS ARRAY_PARTITION variable=scale cyclic factor=8
 unsigned groups=(channels+7)/8;
 int8_t table[8][256];
#pragma HLS ARRAY_PARTITION variable=table complete dim=1
#pragma HLS BIND_STORAGE variable=table type=ram_1p impl=lutram
 // One read port per output lane. The shared 256-byte table follows bias/scale.
 if(activation_lut)for(unsigned block=0;block<8;block++){
  W256 data=parameters[groups*2+block];
  for(unsigned byte=0;byte<32;byte++){
#pragma HLS PIPELINE II=1
   for(unsigned j=0;j<8;j++){
#pragma HLS UNROLL
    table[j][block*32+byte]=byte256(data,byte);
   }
  }
 }
 for(unsigned i=0;i<groups*2;i++){
#pragma HLS PIPELINE II=1
  W256 p=parameters[i];
  for(unsigned j=0;j<4;j++){
#pragma HLS UNROLL
   bias[i*4+j]=lane(p,j*2);scale[i*4+j]=word_float(uint32_t(lane(p,j*2+1)));
  }
 }
 float output_scale=word_float(scale_bits);unsigned errors=0,group=0;
 for(unsigned i=0;i<count;i++){
#pragma HLS PIPELINE II=1
  P256 p=sums.read();if(p.keep!=0xffffffffu||p.strb!=0xffffffffu||bool(p.last)!=(i+1==count))errors|=1;
  W64 word=0;
  for(unsigned j=0;j<8;j++){
#pragma HLS UNROLL
   unsigned c=group*8+j;
   int32_t acc=int32_t(uint32_t(lane(p.data,j))+uint32_t(bias[c]));
   float converted=float(acc);
   float product=converted*scale[c];
   float normalized=product/output_scale;
   int8_t q=round_even_int8(normalized,zero);
   if(activation_lut)q=table[j][uint8_t(q)];
   word|=W64(uint8_t(q))<<(8*j);
  }
  words.write(word);group=(group+1==groups)?0:group+1;
 }
 status=errors;
}

static void pack_quantized(Stream<W64>& input,Stream<W256>& output,unsigned count){
#pragma HLS INLINE off
 for(unsigned i=0;i<(count+3)/4;i++){
  W256 p{};
  for(unsigned j=0;j<4;j++){
#pragma HLS PIPELINE II=1
   W64 q=0;if(i*4+j<count)q=input.read();
   setlane(p,j*2,int32_t(uint32_t(q)));setlane(p,j*2+1,int32_t(uint32_t(q>>32)));
  }
  output.write(p);
 }
}

static void write_words(Stream<W256>& words,W256* output,unsigned count){
#pragma HLS INLINE off
 for(unsigned i=0;i<count;i++){
#pragma HLS PIPELINE II=1
  output[i]=words.read();
 }
}

static void raw_write_pipeline(Stream<P256>& sums,W256* output,unsigned count,uint32_t& status){
#pragma HLS INLINE off
 Stream<W256> words;
#pragma HLS STREAM variable=words depth=64
#pragma HLS DATAFLOW
 raw_sums(sums,words,count,status);write_words(words,output,count);
}

static void quant_write_pipeline(Stream<P256>& sums,W256* output,const W256* parameters,unsigned count,unsigned channels,uint32_t scale_bits,int32_t zero,bool activation_lut,uint32_t& status){
#pragma HLS INLINE off
 Stream<W64> quantized;Stream<W256> packed;
#pragma HLS STREAM variable=quantized depth=64
#pragma HLS STREAM variable=packed depth=64
 unsigned output_words=(count+3)/4;
#pragma HLS DATAFLOW
 quantized_sums(sums,quantized,parameters,count,channels,scale_bits,zero,activation_lut,status);
 pack_quantized(quantized,packed,count);write_words(packed,output,output_words);
}

extern "C" void ct_writer(Stream<P256>& sums,W256* output,uint32_t count,uint32_t& status,const W256* parameters,uint32_t mode,uint32_t channels,uint32_t output_scale_bits,uint32_t output_zero){
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=memory depth=1024 max_write_burst_length=64
#pragma HLS INTERFACE m_axi port=parameters offset=slave bundle=memory depth=24 max_read_burst_length=16
#pragma HLS INTERFACE axis port=sums register_mode=both
#pragma HLS INTERFACE s_axilite port=output bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=count bundle=control offset=0x20
#pragma HLS INTERFACE s_axilite port=status bundle=control offset=0x28
#pragma HLS INTERFACE s_axilite port=parameters bundle=control offset=0x30
#pragma HLS INTERFACE s_axilite port=mode bundle=control offset=0x40
#pragma HLS INTERFACE s_axilite port=channels bundle=control offset=0x48
#pragma HLS INTERFACE s_axilite port=output_scale_bits bundle=control offset=0x50
#pragma HLS INTERFACE s_axilite port=output_zero bundle=control offset=0x58
#pragma HLS INTERFACE s_axilite port=return bundle=control
 if(mode==0)raw_write_pipeline(sums,output,count,status);
 else if((mode==1||mode==2)&&channels>=1&&channels<=64)quant_write_pipeline(sums,output,parameters,count,channels,output_scale_bits,int32_t(output_zero),mode==2,status);
 else status=2;
}
