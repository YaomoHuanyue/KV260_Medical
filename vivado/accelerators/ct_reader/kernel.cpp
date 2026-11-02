#include "../../modules/segmentation/axis_tensor_reader_r3/kernel.hpp"
#include "../../modules/segmentation/axis_tensor_reader_r3/legacy_framing.hpp"

// Transform on the reader side: DDR source tensors -> original convolution AXIS.
// Intermediate resize/concat tensors are never materialized in PS memory here.
static W64 source_group(const W256* input,unsigned pixel,unsigned channels,unsigned group){
#pragma HLS INLINE
 unsigned index=pixel*((channels+7)/8)+group;
 return word64(input[index/4],index%4);
}
static unsigned coordinate(unsigned value,unsigned factor){
#pragma HLS INLINE
 return factor==2?value>>1:value;
}

static void transform_words(const W256* input,const W256* skip,Stream<W256>& words,
 const int8_t lut[2][8][256],unsigned h,unsigned w,unsigned ca,unsigned cb,unsigned fa,unsigned fb){
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=lut complete dim=1
#pragma HLS ARRAY_PARTITION variable=lut complete dim=2
 unsigned channels=ca+cb,groups=(channels+7)/8,y=0,x=0,g=0;
 W256 wide{};
 for(unsigned i=0;i<h*w*groups;i++){
#pragma HLS PIPELINE II=1
  unsigned channel=g*8;W64 a=0,b0=0,b1=0;unsigned bgroup=0;
  if(channel<ca)a=source_group(input,coordinate(y,fa)*coordinate(w,fa)+coordinate(x,fa),ca,g);
  if(cb&&channel+8>ca){
   unsigned start=channel>=ca?channel-ca:0;bgroup=start/8;
   unsigned pixel=coordinate(y,fb)*coordinate(w,fb)+coordinate(x,fb);
   b0=source_group(skip,pixel,cb,bgroup);
   unsigned end=channel+8<channels?channel+8:channels;
   if((end-ca-1)/8>bgroup)b1=source_group(skip,pixel,cb,bgroup+1);
  }
  W256 low{};
  for(unsigned j=0;j<8;j++){
#pragma HLS UNROLL
   unsigned c=channel+j;int8_t value=0;
   if(c<ca)value=lut[0][j][uint8_t(byte64(a,j))];
   else if(c<channels){unsigned offset=c-ca-bgroup*8;int8_t raw=offset<8?byte64(b0,offset):byte64(b1,offset-8);value=lut[1][j][uint8_t(raw)];}
   setbyte(low,j,value);
  }
  setword64(wide,i%4,word64(low,0));
  if(i%4==3||i+1==h*w*groups){words.write(wide);wide=W256{};}
  if(g+1==groups){g=0;if(x+1==w){x=0;y++;}else x++;}else g++;
 }
}

static void load_tables(const W256* tables,int8_t lut[2][8][256],unsigned cb){
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=lut complete dim=1
#pragma HLS ARRAY_PARTITION variable=lut complete dim=2
 for(unsigned branch=0;branch<(cb?2u:1u);branch++){
  W256 packed{};
  for(unsigned i=0;i<256;i++){
#pragma HLS PIPELINE II=1
   if(i%32==0)packed=tables[branch*8+i/32];
   int8_t value=byte256(packed,i%32);
   for(unsigned bank=0;bank<8;bank++){
#pragma HLS UNROLL
    lut[branch][bank][i]=value;
   }
  }
 }
}

// Only the admitted 16+16, unit-scale join uses these sequential burst regions.
// Each source W256 contains two consecutive 16-channel pixels.
static void load_join16_a(const W256* input,W256 tile[64],unsigned base,unsigned count){
#pragma HLS INLINE off
 for(unsigned i=0;i<count;i++){
#pragma HLS PIPELINE II=1 style=flp
  tile[i]=input[base+i];
 }
}

static void load_join16_b(const W256* skip,W256 tile[64],unsigned base,unsigned count){
#pragma HLS INLINE off
 for(unsigned i=0;i<count;i++){
#pragma HLS PIPELINE II=1 style=flp
  tile[i]=skip[base+i];
 }
}

static void emit_join16_tile(const W256 tile_a[64],const W256 tile_b[64],
 Stream<W256>& words,const int8_t lut[2][8][256],unsigned pixels){
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=lut complete dim=1
#pragma HLS ARRAY_PARTITION variable=lut complete dim=2
 for(unsigned p=0;p<pixels;p++){
#pragma HLS PIPELINE II=2 style=flp
  const W256 a=tile_a[p/2],b=tile_b[p/2];
  const unsigned offset=(p&1)*16;
  W256 joined{};
  // Two lookups per existing single-port LUT bank, scheduled over II=2.
  for(unsigned c=0;c<16;c++){
#pragma HLS UNROLL
   setbyte(joined,c,lut[0][c&7][uint8_t(byte256(a,offset+c))]);
   setbyte(joined,16+c,lut[1][c&7][uint8_t(byte256(b,offset+c))]);
  }
  words.write(joined);
 }
}

static void transform_join16_words(const W256* input,const W256* skip,
 Stream<W256>& words,const int8_t lut[2][8][256],unsigned pixels){
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=lut complete dim=1
#pragma HLS ARRAY_PARTITION variable=lut complete dim=2
 W256 tile_a[64],tile_b[64];
#pragma HLS BIND_STORAGE variable=tile_a type=ram_1p impl=lutram
#pragma HLS BIND_STORAGE variable=tile_b type=ram_1p impl=lutram
 for(unsigned first=0;first<pixels;first+=128){
  const unsigned remaining=pixels-first;
  const unsigned tile_pixels=remaining<128?remaining:128;
  const unsigned tile_words=(tile_pixels+1)/2;
  // One memory owner: no concurrent tasks on the shared m_axi bundle.
  load_join16_a(input,tile_a,first/2,tile_words);
  load_join16_b(skip,tile_b,first/2,tile_words);
  // An odd final pixel ignores the poisoned/padded upper half of its word.
  emit_join16_tile(tile_a,tile_b,words,lut,tile_pixels);
 }
}

static void transform_words_selected(const W256* input,const W256* skip,Stream<W256>& words,
 const int8_t lut[2][8][256],unsigned h,unsigned w,unsigned ca,unsigned cb,unsigned fa,unsigned fb){
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=lut complete dim=1
#pragma HLS ARRAY_PARTITION variable=lut complete dim=2
 if(ca==16&&cb==16&&fa==1&&fb==1)
  transform_join16_words(input,skip,words,lut,h*w);
 else
  transform_words(input,skip,words,lut,h,w,ca,cb,fa,fb);
}

static void transformed_stream(const W256* input,const W256* skip,const int8_t lut[2][8][256],
 Stream<P256>& pixels,unsigned h,unsigned w,unsigned ca,unsigned cb,unsigned fa,unsigned fb,unsigned kernel){
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=lut complete dim=1
#pragma HLS ARRAY_PARTITION variable=lut complete dim=2
 Stream<W256> words;
#pragma HLS STREAM variable=words depth=64
#pragma HLS DATAFLOW
 transform_words_selected(input,skip,words,lut,h,w,ca,cb,fa,fb);
 reader_packets(words,pixels,h,w,ca+cb,kernel);
}

static void transformed_pipeline(const W256* input,const W256* skip,const W256* tables,
 Stream<P256>& pixels,unsigned h,unsigned w,unsigned ca,unsigned cb,unsigned fa,unsigned fb,unsigned kernel){
#pragma HLS INLINE off
 int8_t lut[2][8][256];
#pragma HLS ARRAY_PARTITION variable=lut complete dim=1
#pragma HLS ARRAY_PARTITION variable=lut complete dim=2
#pragma HLS BIND_STORAGE variable=lut type=ram_1p impl=lutram
 load_tables(tables,lut,cb);
 transformed_stream(input,skip,lut,pixels,h,w,ca,cb,fa,fb,kernel);
}

extern "C" void ct_tensor_reader(const W256* input,Stream<P256>& pixels,
 uint32_t height,uint32_t width,uint32_t cin,uint32_t kernel,
 const W256* skip,const W256* tables,uint32_t mode,uint32_t channels_a,
 uint32_t channels_b,uint32_t factor_a,uint32_t factor_b,uint32_t& status){
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=memory depth=1024 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=skip offset=slave bundle=memory depth=1024 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=tables offset=slave bundle=memory depth=16 max_read_burst_length=64
#pragma HLS INTERFACE axis port=pixels register_mode=both
#pragma HLS INTERFACE s_axilite port=input bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=height bundle=control offset=0x20
#pragma HLS INTERFACE s_axilite port=width bundle=control offset=0x28
#pragma HLS INTERFACE s_axilite port=cin bundle=control offset=0x30
#pragma HLS INTERFACE s_axilite port=kernel bundle=control offset=0x38
#pragma HLS INTERFACE s_axilite port=skip bundle=control offset=0x40
#pragma HLS INTERFACE s_axilite port=tables bundle=control offset=0x50
#pragma HLS INTERFACE s_axilite port=mode bundle=control offset=0x60
#pragma HLS INTERFACE s_axilite port=channels_a bundle=control offset=0x68
#pragma HLS INTERFACE s_axilite port=channels_b bundle=control offset=0x70
#pragma HLS INTERFACE s_axilite port=factor_a bundle=control offset=0x78
#pragma HLS INTERFACE s_axilite port=factor_b bundle=control offset=0x80
#pragma HLS INTERFACE s_axilite port=status bundle=control offset=0x88
#pragma HLS INTERFACE s_axilite port=return bundle=control
 status=0;
 if(!valid_shape(height,width,cin,1,kernel)||mode>2){status=1;return;}
 if(mode==0){reader_pipeline(input,pixels,height,width,cin,kernel);return;}
 if(channels_a<1||channels_a>64||channels_b>64||channels_a+channels_b!=cin||
    (mode==1&&channels_b!=0)||(mode==2&&channels_b==0)||
    (factor_a!=1&&factor_a!=2)||(factor_b!=1&&factor_b!=2)||
    height%factor_a||width%factor_a||(channels_b&&(height%factor_b||width%factor_b))){status=1;return;}
 transformed_pipeline(input,skip,tables,pixels,height,width,channels_a,channels_b,factor_a,factor_b,kernel);
}
