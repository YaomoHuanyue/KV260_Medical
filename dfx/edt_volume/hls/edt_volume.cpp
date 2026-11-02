#include "types.hpp"
#ifdef EDT_VOLUME_NATIVE
#include <cmath>
#else
#include <hls_math.h>
#endif

// Power-of-two widths avoid a runtime divider in the address/control path.
// Small volumes use narrower tiles instead of processing 128 padded columns.
static unsigned stripe_shift(unsigned words){
#pragma HLS INLINE
 return words<=2?1:words<=4?2:words<=8?3:4;
}

// Eleven exact binary quotient decisions become a bounded combinational chain;
// HLS may schedule the chain across cycles to meet the 100 MHz clock.
static unsigned first_better(int64_t numerator,uint64_t denominator,unsigned length){
#pragma HLS INLINE
 if(numerator<0)return 0;
 uint64_t shifted=denominator<<10,accumulated=0;unsigned coordinate=0,step=1024;
 for(unsigned bit=0;bit<11;++bit){
#pragma HLS UNROLL
  unsigned candidate=coordinate+step;uint64_t trial=accumulated+shifted;
  if(candidate<length&&trial<=uint64_t(numerator)){coordinate=candidate;accumulated=trial;}
  shifted>>=1;step>>=1;
 }
 return coordinate+1<length?coordinate+1:length;
}

static void line(const uint64_t*f,uint64_t*d,unsigned n,uint32_t weight,bool binary,bool all_zero){
#pragma HLS INLINE off
 if(all_zero){
  for(unsigned q=0;q<n;++q){
#pragma HLS PIPELINE II=1
   d[q]=0;
  }
  return;
 }
 if(binary){
  unsigned run=VOLUME_MAX_LINE+1;
  for(unsigned q=0;q<n;++q){
#pragma HLS PIPELINE II=1
   run=f[q]==0?0:run+1;d[q]=run>VOLUME_MAX_LINE?VOLUME_INF:uint64_t(weight)*run*run;
  }
  run=VOLUME_MAX_LINE+1;
  for(int q=int(n)-1;q>=0;--q){
#pragma HLS PIPELINE II=1
   run=f[q]==0?0:run+1;uint64_t value=run>VOLUME_MAX_LINE?VOLUME_INF:uint64_t(weight)*run*run;
   if(value<d[q])d[q]=value;
  }
  return;
 }
 uint16_t candidates[VOLUME_MAX_LINE],starts[VOLUME_MAX_LINE];
#pragma HLS BIND_STORAGE variable=candidates type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=starts type=ram_2p impl=bram
 int last=-1;
 for(unsigned q=0;q<n;++q){
#pragma HLS LOOP_TRIPCOUNT min=1 max=1024
  if(f[q]==VOLUME_INF)continue;
  unsigned first=0;
  while(last>=0){
#pragma HLS LOOP_TRIPCOUNT min=1 max=1024
   unsigned p=candidates[last];
   int64_t numerator=int64_t(f[q])-int64_t(f[p])+int64_t(weight)*(int64_t(q)*q-int64_t(p)*p);
   uint64_t denominator=2*uint64_t(weight)*(q-p);
   first=first_better(numerator,denominator,n);
   if(first>starts[last])break;--last;
  }
  if(last<0)first=0;
  if(first<n){++last;candidates[last]=q;starts[last]=first;}
 }
 if(last<0){
  for(unsigned q=0;q<n;++q){
#pragma HLS PIPELINE II=1
   d[q]=VOLUME_INF;
  }
  return;
 }
 unsigned k=0;
 for(unsigned q=0;q<n;++q){
#pragma HLS LOOP_TRIPCOUNT min=1 max=1024
  while(k<unsigned(last)&&starts[k+1]<=q)++k;
  int64_t delta=int64_t(q)-candidates[k];d[q]=f[candidates[k]]+uint64_t(weight)*uint64_t(delta*delta);
 }
}

static void lines(const uint64_t input[8][VOLUME_MAX_LINE],uint64_t output[8][VOLUME_MAX_LINE],
 unsigned length,uint32_t weight,bool binary,const bool all_zero[8]){
#pragma HLS INLINE off
#pragma HLS DATAFLOW
 for(unsigned lane=0;lane<8;++lane){
#pragma HLS UNROLL
  line(input[lane],output[lane],length,weight,binary,all_zero[lane]);
 }
}

static void read_volume(const VolumeWord*mask,const VolumeWord*input,VolumeStream<VolumeWord>&stream,
 unsigned nz,unsigned ny,unsigned nx,unsigned axis){
#pragma HLS INLINE off
 unsigned words=(nx+7)/8,length=axis==2?nx:axis==1?ny:nz;
 if(axis==2){
  unsigned mask_words=(nx+63)/64,rows=nz*ny,groups=(rows+7)/8;
  VolumeWord masks[8][VOLUME_MAX_LINE/64];
#pragma HLS ARRAY_PARTITION variable=masks complete dim=1
#pragma HLS BIND_STORAGE variable=masks type=ram_2p impl=lutram
  for(unsigned group=0;group<groups;++group){
#pragma HLS LOOP_TRIPCOUNT min=1 max=131072
   unsigned valid_rows=rows-group*8<8?rows-group*8:8;
   // Bound the loop before the load: every DDR request is contiguous.
   // The former per-word conditional prevented read burst inference.
   for(unsigned lane=0;lane<valid_rows;++lane)for(unsigned block=0;block<mask_words;++block){
#pragma HLS PIPELINE II=1
    masks[lane][block]=mask[(group*8+lane)*mask_words+block];
   }
   for(unsigned lane=valid_rows;lane<8;++lane)for(unsigned block=0;block<mask_words;++block){
#pragma HLS PIPELINE II=1
    masks[lane][block]=VolumeWord{};
   }
   for(unsigned block=0;block<mask_words;++block){
    unsigned count=nx-block*64<64?nx-block*64:64;
    for(unsigned j=0;j<count;++j){
#pragma HLS PIPELINE II=1
     VolumeWord word{};
     for(unsigned lane=0;lane<8;++lane){
#pragma HLS UNROLL
      cost(word,lane,byte(masks[lane][block],j)!=0);
     }
     stream.write(word);
    }
   }
  }
 }else{
  // Up to 128 columns give contiguous sixteen-word DDR bursts before
  // emitting complete lines. Reordering stays inside the PL URAM tile.
  VolumeWord tile[VOLUME_STRIPE_WORDS*VOLUME_MAX_LINE];
#pragma HLS BIND_STORAGE variable=tile type=ram_2p impl=uram
  unsigned shift=stripe_shift(words),stripe_words=1u<<shift;
  unsigned outer=axis==1?nz:ny,stripes=(words+stripe_words-1)>>shift;
  for(unsigned major=0;major<outer;++major)for(unsigned stripe=0;stripe<stripes;++stripe){
#pragma HLS LOOP_TRIPCOUNT min=1 max=32768
   unsigned base=stripe<<shift;
   unsigned valid_words=words-base<stripe_words?words-base:stripe_words;
   for(unsigned q=0;q<length;++q){
    uint64_t row=axis==1?uint64_t(major)*ny+q:uint64_t(q)*ny+major;
    for(unsigned batch=0;batch<valid_words;++batch){
#pragma HLS PIPELINE II=1
     tile[batch*VOLUME_MAX_LINE+q]=input[row*words+base+batch];
    }
    for(unsigned batch=valid_words;batch<stripe_words;++batch){
#pragma HLS PIPELINE II=1
     tile[batch*VOLUME_MAX_LINE+q]=VolumeWord{};
    }
   }
   for(unsigned batch=0;batch<stripe_words;++batch)for(unsigned q=0;q<length;++q){
#pragma HLS PIPELINE II=1
    stream.write(tile[batch*VOLUME_MAX_LINE+q]);
   }
  }
 }
}

static void compute_volume(VolumeStream<VolumeWord>&input,VolumeStream<VolumeWord>&output,
 unsigned nz,unsigned ny,unsigned nx,unsigned axis,uint32_t weight){
#pragma HLS INLINE off
 uint64_t f[8][VOLUME_MAX_LINE],d[8][VOLUME_MAX_LINE];
#pragma HLS ARRAY_PARTITION variable=f complete dim=1
#pragma HLS ARRAY_PARTITION variable=d complete dim=1
#pragma HLS BIND_STORAGE variable=f type=ram_t2p impl=bram
#pragma HLS BIND_STORAGE variable=d type=ram_2p impl=bram
 bool all_zero[8];
#pragma HLS ARRAY_PARTITION variable=all_zero complete
 unsigned length=axis==2?nx:axis==1?ny:nz,words=(nx+7)/8;
 unsigned shift=stripe_shift(words),stripe_words=1u<<shift;
 unsigned groups=axis==2?(nz*ny+7)/8:((axis==1?nz:ny)*((words+stripe_words-1)>>shift))<<shift;
 for(unsigned group=0;group<groups;++group){
#pragma HLS LOOP_TRIPCOUNT min=1 max=131072
  for(unsigned lane=0;lane<8;++lane){
#pragma HLS UNROLL
   all_zero[lane]=true;
  }
  for(unsigned q=0;q<length;++q){
#pragma HLS PIPELINE II=1
   VolumeWord word=input.read();
   for(unsigned lane=0;lane<8;++lane){
#pragma HLS UNROLL
    uint64_t value=cost(word,lane);f[lane][q]=value;all_zero[lane]=all_zero[lane]&&value==0;
   }
  }
  lines(f,d,length,weight,axis==2,all_zero);
  for(unsigned q=0;q<length;++q){
#pragma HLS PIPELINE II=1
   VolumeWord word{};
   for(unsigned lane=0;lane<8;++lane){
#pragma HLS UNROLL
    cost(word,lane,d[lane][q]);
   }
   output.write(word);
  }
 }
}

static uint32_t physical_distance(uint64_t squared){
#pragma HLS INLINE
 if(squared==VOLUME_INF)return 0x7f800000;
 float value=float(squared)*(1.f/1048576.f);
#ifdef EDT_VOLUME_NATIVE
 value=std::sqrt(value);
#else
 value=hls::sqrtf(value);
#endif
 uint32_t bits;std::memcpy(&bits,&value,4);return bits;
}

static void write_volume(VolumeStream<VolumeWord>&stream,VolumeWord*output,VolumeWord*distance,
 unsigned nz,unsigned ny,unsigned nx,unsigned axis,unsigned&status){
#pragma HLS INLINE off
 VolumeWord tile[VOLUME_STRIPE_WORDS*VOLUME_MAX_LINE];
#pragma HLS BIND_STORAGE variable=tile type=ram_2p impl=uram
 unsigned words=(nx+7)/8,length=axis==2?nx:axis==1?ny:nz;
 bool any_finite=false;
 if(axis==2){
  unsigned rows=nz*ny,groups=(rows+7)/8;
  VolumeWord row[VOLUME_MAX_LINE/8];
#pragma HLS BIND_STORAGE variable=row type=ram_2p impl=bram
  for(unsigned group=0;group<groups;++group){
#pragma HLS LOOP_TRIPCOUNT min=1 max=131072
   unsigned valid_rows=rows-group*8<8?rows-group*8:8;
   for(unsigned q=0;q<nx;++q){
#pragma HLS PIPELINE II=1
    tile[q]=stream.read();
   }
   for(unsigned lane=0;lane<valid_rows;++lane){
    for(unsigned xword=0;xword<words;++xword){
     VolumeWord word{};
     for(unsigned j=0;j<8;++j){
#pragma HLS PIPELINE II=1
      unsigned q=xword*8+j;cost(word,j,q<nx?cost(tile[q],lane):0);
     }
     row[xword]=word;
    }
    for(unsigned j=0;j<words;++j){
#pragma HLS PIPELINE II=1
     output[(group*8+lane)*words+j]=row[j];
    }
   }
  }
 }else{
  unsigned shift=stripe_shift(words),stripe_words=1u<<shift;
  unsigned outer=axis==1?nz:ny,stripes=(words+stripe_words-1)>>shift,float_words=(nx+15)/16;
  for(unsigned major=0;major<outer;++major)for(unsigned stripe=0;stripe<stripes;++stripe){
#pragma HLS LOOP_TRIPCOUNT min=1 max=32768
   unsigned base=stripe<<shift;
   unsigned valid_words=words-base<stripe_words?words-base:stripe_words;
   for(unsigned batch=0;batch<stripe_words;++batch)for(unsigned q=0;q<length;++q){
#pragma HLS PIPELINE II=1
    tile[batch*VOLUME_MAX_LINE+q]=stream.read();
   }
   for(unsigned q=0;q<length;++q){
    uint64_t row_index=axis==1?uint64_t(major)*ny+q:uint64_t(q)*ny+major;
    // Consecutive costs and floats use distinct unconditional burst loops.
    // Mixing two writes and per-word bounds checks forced scalar AXI traffic.
    for(unsigned batch=0;batch<valid_words;++batch){
#pragma HLS PIPELINE II=1
     output[row_index*words+base+batch]=tile[batch*VOLUME_MAX_LINE+q];
    }
    if(axis==0){
     VolumeWord float_row[VOLUME_STRIPE_WORDS/2];
#pragma HLS ARRAY_PARTITION variable=float_row complete
     unsigned float_base=base/2;
     unsigned valid_floats=float_words-float_base<stripe_words/2?float_words-float_base:stripe_words/2;
     for(unsigned fw=0;fw<valid_floats;++fw){
#pragma HLS PIPELINE II=1
      VolumeWord first=tile[(fw*2)*VOLUME_MAX_LINE+q],second=tile[(fw*2+1)*VOLUME_MAX_LINE+q],floats{};
      for(unsigned lane=0;lane<16;++lane){
#pragma HLS UNROLL
       unsigned x=(base+fw*2)*8+lane;uint64_t value=lane<8?cost(first,lane):cost(second,lane-8);
       if(x<nx&&value!=VOLUME_INF)any_finite=true;
       bits32(floats,lane,x<nx?physical_distance(value):0);
      }
      float_row[fw]=floats;
     }
     for(unsigned fw=0;fw<valid_floats;++fw){
#pragma HLS PIPELINE II=1
      distance[row_index*float_words+float_base+fw]=float_row[fw];
     }
    }
   }
  }
 }
 status=axis==0&&!any_finite?2:0;
}

static void pass(const VolumeWord*mask,const VolumeWord*input,VolumeWord*output,VolumeWord*distance,
 unsigned nz,unsigned ny,unsigned nx,unsigned axis,uint32_t weight,unsigned&status){
#pragma HLS INLINE off
#pragma HLS DATAFLOW
 VolumeStream<VolumeWord> ingress,egress;
#pragma HLS STREAM variable=ingress depth=128
#pragma HLS STREAM variable=egress depth=128
#pragma HLS BIND_STORAGE variable=ingress type=fifo impl=bram
#pragma HLS BIND_STORAGE variable=egress type=fifo impl=bram
 read_volume(mask,input,ingress,nz,ny,nx,axis);
 compute_volume(ingress,egress,nz,ny,nx,axis,weight);
 write_volume(egress,output,distance,nz,ny,nx,axis,status);
}

extern "C" void edt_volume(const VolumeWord*mask,VolumeWord*work_a,VolumeWord*work_b,VolumeWord*distance,
 unsigned nz,unsigned ny,unsigned nx,uint32_t wz,uint32_t wy,uint32_t wx,unsigned&status){
#pragma HLS INTERFACE m_axi port=mask offset=slave bundle=memory depth=2048 max_read_burst_length=16 num_read_outstanding=8
#pragma HLS INTERFACE m_axi port=work_a offset=slave bundle=memory depth=2048 max_read_burst_length=16 max_write_burst_length=16 num_read_outstanding=8 num_write_outstanding=8
#pragma HLS INTERFACE m_axi port=work_b offset=slave bundle=memory depth=2048 max_read_burst_length=16 max_write_burst_length=16 num_read_outstanding=8 num_write_outstanding=8
#pragma HLS INTERFACE m_axi port=distance offset=slave bundle=memory depth=2048 max_write_burst_length=16 num_write_outstanding=8
#pragma HLS INTERFACE s_axilite port=mask bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=work_a bundle=control offset=0x1c
#pragma HLS INTERFACE s_axilite port=work_b bundle=control offset=0x28
#pragma HLS INTERFACE s_axilite port=distance bundle=control offset=0x34
#pragma HLS INTERFACE s_axilite port=nz bundle=control offset=0x40
#pragma HLS INTERFACE s_axilite port=ny bundle=control offset=0x48
#pragma HLS INTERFACE s_axilite port=nx bundle=control offset=0x50
#pragma HLS INTERFACE s_axilite port=wz bundle=control offset=0x58
#pragma HLS INTERFACE s_axilite port=wy bundle=control offset=0x60
#pragma HLS INTERFACE s_axilite port=wx bundle=control offset=0x68
#pragma HLS INTERFACE s_axilite port=status bundle=control offset=0x70
#pragma HLS INTERFACE s_axilite port=return bundle=control
 if(!nz||!ny||!nx||nz>1024||ny>1024||nx>1024||uint64_t(nz)*ny*nx>80000000||!wz||!wy||!wx){status=1;return;}
 unsigned phase_status=0;
 pass(mask,work_b,work_a,distance,nz,ny,nx,2,wx,phase_status);
 pass(mask,work_a,work_b,distance,nz,ny,nx,1,wy,phase_status);
 pass(mask,work_b,work_a,distance,nz,ny,nx,0,wz,phase_status);
 status=phase_status;
}
