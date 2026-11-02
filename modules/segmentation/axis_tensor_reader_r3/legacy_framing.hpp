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

