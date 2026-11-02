#include "scope.hpp"

static ap_uint<70> field[2][8][FIELD_WORDS];
static ap_uint<64> directory[2][8][DIR_WORDS],leaf_map[2][8][LEAF_WORDS];
static int nx=0,ny=0,nz=0;
static unsigned mx=0,my=0,mz=0,page_stride_y=0,page_stride_z=0;
static int outside_q=-128;
static unsigned scene_token=0,block_count=0;
static bool loaded=false;
static ap_int<16> normal_matrix[9];

static ap_uint<32> encode_normal(ap_int<25> gx,ap_int<25> gy,ap_int<25> gz){
#pragma HLS INLINE
 ap_uint<32> result=0xff000000;
 for(int row=0;row<3;++row){
#pragma HLS UNROLL
  ap_int<43> v=ap_int<43>(gx*normal_matrix[row*3])+ap_int<43>(gy*normal_matrix[row*3+1])+ap_int<43>(gz*normal_matrix[row*3+2]);
  int c=int(v>>16);c=c<-127?-127:c>127?127:c;
  result.range(row*8+7,row*8)=128+c;
 }
 return result;
}

// Four lanes retain two field copies; paged maps use BRAM.
// Five exact 14-bit signed-Q/target samples share each 70-bit URAM word.
// The input scene keeps its checked 16-bit slots; no separate target atlas.
static void sample(int copy,int xq,int yq,int zq,int& value,unsigned& selected){
#pragma HLS INLINE
 int x=xq>>16,y=yq>>16,z=zq>>16;
 unsigned fx=(unsigned(xq)>>8)&255,fy=(unsigned(yq)>>8)&255,fz=(unsigned(zq)>>8)&255;
 int bx=x>>2,by=y>>2,bz=z>>2;
 unsigned ids[8];int a[8];unsigned b[8];
#pragma HLS ARRAY_PARTITION variable=ids complete
#pragma HLS ARRAY_PARTITION variable=a complete
#pragma HLS ARRAY_PARTITION variable=b complete
 // The eight coarse parity banks cover all bricks touched by eight corners.
 for(int bank=0;bank<8;++bank){
#pragma HLS UNROLL
  int xx=bx+((bx&1)^(bank&1)),yy=by+((by&1)^((bank>>1)&1)),zz=bz+((bz&1)^((bank>>2)&1));
  unsigned id=0;
  if(xx>=0&&unsigned(xx)<mx&&yy>=0&&unsigned(yy)<my&&zz>=0&&unsigned(zz)<mz){
   unsigned address=(unsigned(zz)>>3)*page_stride_z+(unsigned(yy)>>3)*page_stride_y+(unsigned(xx)>>3);
   ap_uint<64> upper=directory[copy][bank][address>>2];unsigned page=(upper>>((address&3)*16))&65535;
   if(page){unsigned local=((unsigned(zz)&7)>>1)*16+((unsigned(yy)&7)>>1)*4+((unsigned(xx)&7)>>1);
    unsigned index=(page-1)*64+local;ap_uint<64> word=leaf_map[copy][bank][index>>2];id=(word>>((index&3)*16))&65535;}
  }
  ids[bank]=id;
 }
 for(int bank=0;bank<8;++bank){
#pragma HLS UNROLL
  int dx=(x&1)^(bank&1),dy=(y&1)^((bank>>1)&1),dz=(z&1)^((bank>>2)&1);
  int xx=x+dx,yy=y+dy,zz=z+dz,v=outside_q;unsigned selected_bit=0;
  unsigned coarse=((unsigned(xx)>>2)&1)+2*((unsigned(yy)>>2)&1)+4*((unsigned(zz)>>2)&1),id=ids[coarse];
  if(xx>=0&&xx<nx&&yy>=0&&yy<ny&&zz>=0&&zz<nz&&id&&id<=block_count){
   unsigned brick=id-1,local=((unsigned(zz)&3)>>1)*4+((unsigned(yy)&3)>>1)*2+((unsigned(xx)&3)>>1);
   ap_uint<17> index=brick*8+local;
   ap_uint<33> reciprocal_product=index*ap_uint<16>(52429);
   ap_uint<14> address=reciprocal_product>>18;
   ap_uint<3> slot=index-ap_uint<17>(address)*ap_uint<3>(5);
   unsigned shift=unsigned(slot)*14;
   ap_uint<70> word=field[copy][bank][address];
   ap_int<13> signed_value=word.range(shift+12,shift);v=int(signed_value);
   selected_bit=word[shift+13];
  }
  a[bank]=v;b[bank]=selected_bit;
 }
 int ax[4];unsigned sx[4];
#pragma HLS ARRAY_PARTITION variable=ax complete
#pragma HLS ARRAY_PARTITION variable=sx complete
 for(int i=0;i<4;++i){
#pragma HLS UNROLL
  int left=(x&1)?a[i*2+1]:a[i*2],right=(x&1)?a[i*2]:a[i*2+1];
  unsigned target_left=(x&1)?b[i*2+1]:b[i*2],target_right=(x&1)?b[i*2]:b[i*2+1];
  ax[i]=left*int(256-fx)+right*int(fx);
  sx[i]=target_left*(256-fx)+target_right*fx;
 }
 int low=(((y&1)?ax[1]:ax[0])*int(256-fy)+((y&1)?ax[0]:ax[1])*int(fy))>>8;
 int high=(((y&1)?ax[3]:ax[2])*int(256-fy)+((y&1)?ax[2]:ax[3])*int(fy))>>8;
 value=(((z&1)?high:low)*int(256-fz)+((z&1)?low:high)*int(fz))>>8;
 unsigned slow=((y&1)?sx[1]:sx[0])*(256-fy)+((y&1)?sx[0]:sx[1])*fy;
 unsigned shigh=((y&1)?sx[3]:sx[2])*(256-fy)+((y&1)?sx[2]:sx[3])*fy;
 selected=(((z&1)?shigh:slow)*(256-fz)+((z&1)?slow:shigh)*fz)>>8;
}

static void trace(hls::stream<ap_uint<64>>& pixels,const int p[16]){
#pragma HLS INLINE off
 const unsigned width=p[0],height=p[1],steps=p[2];
 int x[LANES][SLOTS],y[LANES][SLOTS],z[LANES][SLOTS];
 int dx[LANES][SLOTS],dy[LANES][SLOTS],dz[LANES][SLOTS];
 bool inside[LANES][SLOTS],done[LANES][SLOTS],reached[LANES][SLOTS],refining[LANES][SLOTS];
 ap_uint<3> refinement_count[LANES][SLOTS];ap_uint<7> low_fraction[LANES][SLOTS],high_fraction[LANES][SLOTS];
 ap_uint<16> depth_base[LANES][SLOTS];bool found[LANES][SLOTS];
 ap_uint<3> normal_count[LANES][SLOTS];
 ap_int<25> positive[LANES][SLOTS],gx[LANES][SLOTS],gy[LANES][SLOTS];
 ap_uint<32> normals[LANES][SLOTS];
 // Trace nearby 16x16 pixels together to reduce long-ray batch waiting.
 // A 16-row stripe restores raster order before the streaming contour stage.
 ap_uint<64> stripe[16*MAX_WIDTH];
#pragma HLS BIND_STORAGE variable=stripe type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=x complete
#pragma HLS ARRAY_PARTITION variable=y complete
#pragma HLS ARRAY_PARTITION variable=z complete
#pragma HLS ARRAY_PARTITION variable=dx complete
#pragma HLS ARRAY_PARTITION variable=dy complete
#pragma HLS ARRAY_PARTITION variable=dz complete
#pragma HLS ARRAY_PARTITION variable=inside complete
#pragma HLS ARRAY_PARTITION variable=done complete dim=0
#pragma HLS ARRAY_PARTITION variable=reached complete
#pragma HLS ARRAY_PARTITION variable=refining complete
#pragma HLS ARRAY_PARTITION variable=refinement_count complete
#pragma HLS ARRAY_PARTITION variable=low_fraction complete
#pragma HLS ARRAY_PARTITION variable=high_fraction complete
#pragma HLS ARRAY_PARTITION variable=depth_base complete
#pragma HLS ARRAY_PARTITION variable=found complete
#pragma HLS ARRAY_PARTITION variable=normal_count complete
#pragma HLS ARRAY_PARTITION variable=positive complete
#pragma HLS ARRAY_PARTITION variable=gx complete
#pragma HLS ARRAY_PARTITION variable=gy complete
#pragma HLS ARRAY_PARTITION variable=normals complete
#pragma HLS BIND_STORAGE variable=x type=ram_2p impl=lutram
#pragma HLS BIND_STORAGE variable=y type=ram_2p impl=lutram
#pragma HLS BIND_STORAGE variable=z type=ram_2p impl=lutram
#pragma HLS BIND_STORAGE variable=dx type=ram_2p impl=lutram
#pragma HLS BIND_STORAGE variable=dy type=ram_2p impl=lutram
#pragma HLS BIND_STORAGE variable=dz type=ram_2p impl=lutram
#pragma HLS BIND_STORAGE variable=depth_base type=ram_2p impl=lutram
#pragma HLS BIND_STORAGE variable=normal_count type=ram_2p impl=lutram
#pragma HLS BIND_STORAGE variable=positive type=ram_2p impl=lutram
#pragma HLS BIND_STORAGE variable=gx type=ram_2p impl=lutram
#pragma HLS BIND_STORAGE variable=gy type=ram_2p impl=lutram
#pragma HLS BIND_STORAGE variable=normals type=ram_2p impl=lutram
#pragma HLS BIND_STORAGE variable=refinement_count type=ram_2p impl=lutram
#pragma HLS BIND_STORAGE variable=low_fraction type=ram_2p impl=lutram
#pragma HLS BIND_STORAGE variable=high_fraction type=ram_2p impl=lutram
 for(unsigned band=0;band<height;band+=16){
  for(unsigned column=0;column<width;column+=16){
  for(int slot=0;slot<SLOTS;++slot){
#pragma HLS PIPELINE II=1
   for(int lane=0;lane<LANES;++lane){
#pragma HLS UNROLL
    unsigned i=slot*LANES+lane,px=column+(i&15),py=band+(i>>4);
    x[lane][slot]=p[4];y[lane][slot]=p[5];z[lane][slot]=p[6];
    dx[lane][slot]=p[7]+int(px)*p[10]+int(py)*p[13];
    dy[lane][slot]=p[8]+int(px)*p[11]+int(py)*p[14];
    dz[lane][slot]=p[9]+int(px)*p[12]+int(py)*p[15];
    done[lane][slot]=py>=height;inside[lane][slot]=false;reached[lane][slot]=false;
    depth_base[lane][slot]=0;found[lane][slot]=false;refining[lane][slot]=false;
    normal_count[lane][slot]=0;normals[lane][slot]=0;positive[lane][slot]=0;gx[lane][slot]=0;gy[lane][slot]=0;
    refinement_count[lane][slot]=0;low_fraction[lane][slot]=0;high_fraction[lane][slot]=64;
   }
  }
  bool any=true;
  // A ray keeps the same physical sampler for marching and its six refinements.
  // Rays which finish refining stop while the other rays continue marching.
  for(unsigned wave=0;wave<=steps+12&&any;++wave){
#pragma HLS LOOP_TRIPCOUNT min=2 max=1036 avg=60
   ray_slots: for(int slot=0;slot<SLOTS;++slot){
#pragma HLS PIPELINE II=1
    for(int lane=0;lane<LANES;++lane){
#pragma HLS UNROLL
     if(!done[lane][slot]){
      unsigned old_high=high_fraction[lane][slot];
      unsigned middle=(unsigned(low_fraction[lane][slot])+old_high)>>1;
      bool refine=refining[lane][slot];unsigned gradient=normal_count[lane][slot];
      int offset=(gradient&1)?65536:-65536;
      int qx=x[lane][slot]+(refine?((dx[lane][slot]*int(middle))>>6):gradient==1||gradient==2?offset:0);
      int qy=y[lane][slot]+(refine?((dy[lane][slot]*int(middle))>>6):gradient==3||gradient==4?offset:0);
      int qz=z[lane][slot]+(refine?((dz[lane][slot]*int(middle))>>6):gradient==5||gradient==6?offset:0);
      int value;unsigned target;sample(lane/2,qx,qy,qz,value,target);bool state=value>0;
      if(gradient){
       if(gradient&1)positive[lane][slot]=value;
       else if(gradient==2)gx[lane][slot]=positive[lane][slot]-value;
       else if(gradient==4)gy[lane][slot]=positive[lane][slot]-value;
       else{normals[lane][slot]=encode_normal(gx[lane][slot],gy[lane][slot],positive[lane][slot]-value);done[lane][slot]=true;}
       normal_count[lane][slot]=gradient+1;
      }else if(refine){
       bool same_side=state==inside[lane][slot];
       if(same_side)low_fraction[lane][slot]=middle;else high_fraction[lane][slot]=middle;
       unsigned crossing_fraction=same_side?old_high:middle;
       if(refinement_count[lane][slot]==5){
        refining[lane][slot]=false;normal_count[lane][slot]=1;
        x[lane][slot]+=(dx[lane][slot]*int(crossing_fraction))>>6;
        y[lane][slot]+=(dy[lane][slot]*int(crossing_fraction))>>6;
        z[lane][slot]+=(dz[lane][slot]*int(crossing_fraction))>>6;
       }else refinement_count[lane][slot]++;
      }else{
       if(wave==0)inside[lane][slot]=state;
       bool hit=wave>0&&state!=inside[lane][slot];
       if(hit){
        depth_base[lane][slot]=(wave-1)*64;found[lane][slot]=true;refining[lane][slot]=true;
        x[lane][slot]-=dx[lane][slot];y[lane][slot]-=dy[lane][slot];z[lane][slot]-=dz[lane][slot];
       }else{
        if(inside[lane][slot]&&target>42598)reached[lane][slot]=true;
        x[lane][slot]+=dx[lane][slot];y[lane][slot]+=dy[lane][slot];z[lane][slot]+=dz[lane][slot];
        if(wave>=steps)done[lane][slot]=true;
       }
      }
     }
    }
   }
   // Reduce once after the wave. Accumulating across lane updates inside the
   // pipelined slot loop creates a carried OR dependence and raises II to 4.
   any=false;
   for(int slot=0;slot<SLOTS;++slot){
#pragma HLS UNROLL
    for(int lane=0;lane<LANES;++lane){
#pragma HLS UNROLL
     any=any||!done[lane][slot];
    }
   }
  }
  for(int i=0;i<LANES*SLOTS;++i){
#pragma HLS PIPELINE II=1
    int slot=i/LANES,lane=i%LANES;
    if(band+unsigned(i>>4)<height){
     int fraction=high_fraction[lane][slot];
     ap_uint<64> v=found[lane][slot]?ap_uint<16>(depth_base[lane][slot]+fraction):ap_uint<16>(65535);
     v.range(63,32)=normals[lane][slot];v[16]=reached[lane][slot]&&inside[lane][slot];stripe[(i>>4)*MAX_WIDTH+column+(i&15)]=v;
    }
  }
  }
  for(unsigned row=0;row<16&&band+row<height;++row){
   for(unsigned column=0;column<width;++column){
#pragma HLS PIPELINE II=1
    pixels.write(stripe[row*MAX_WIDTH+column]);
   }
  }
 }
}

// Screen-edge replication avoids drawing a false anatomical rim at the viewport.
static void outline(hls::stream<ap_uint<64>>& input,hls::stream<ap_uint<64>>& output,unsigned width,unsigned height){
#pragma HLS INLINE off
 ap_uint<64> rows[6][MAX_WIDTH],window[7][7];
#pragma HLS ARRAY_PARTITION variable=rows complete dim=1
#pragma HLS BIND_STORAGE variable=rows type=ram_2p impl=bram
#pragma HLS ARRAY_PARTITION variable=window complete
 for(unsigned r=0;r<height+3;++r){
  for(unsigned c=0;c<width+3;++c){
#pragma HLS PIPELINE II=1
   ap_uint<64> column[7];
#pragma HLS ARRAY_PARTITION variable=column complete
   if(c<width){
    ap_uint<64> v=r<height?input.read():rows[5][c];
    for(int j=0;j<6;++j){
#pragma HLS UNROLL
     column[j]=r==0?v:rows[j][c];
    }
    column[6]=v;
    for(int j=0;j<6;++j){
#pragma HLS UNROLL
     rows[j][c]=column[j+1];
    }
   }else{
    for(int j=0;j<7;++j){
#pragma HLS UNROLL
     column[j]=window[j][6];
    }
   }
   for(int j=0;j<7;++j){
#pragma HLS UNROLL
    for(int k=0;k<6;++k){
#pragma HLS UNROLL
     window[j][k]=c==0?column[j]:window[j][k+1];
    }
    window[j][6]=column[j];
   }
   if(r>=3&&c>=3){
    unsigned sum=0;bool lo=true,hi=false,outer=false;
    for(int j=0;j<7;++j){
#pragma HLS UNROLL
     for(int k=0;k<7;++k){
#pragma HLS UNROLL
      bool b=window[j][k][16];outer|=b;
      if(j>=1&&j<=5&&k>=1&&k<=5){lo&=b;hi|=b;}
      if(j>=2&&j<=4&&k>=2&&k<=4)sum+=unsigned(b)*(j==3?2:1)*(k==3?2:1);
     }
    }
    ap_uint<64> center=window[3][3],v=center&65535;
    // Smooth lighting only. Depth and target visibility remain bit-identical.
    ap_uint<13> normal_sum[3];ap_uint<5> weights=0;
#pragma HLS ARRAY_PARTITION variable=normal_sum complete
    for(int channel=0;channel<3;++channel){
#pragma HLS UNROLL
     normal_sum[channel]=0;
    }
    if(center.range(15,0)!=65535){
     for(int j=2;j<=4;++j){
#pragma HLS UNROLL
      for(int k=2;k<=4;++k){
#pragma HLS UNROLL
       ap_uint<64> n=window[j][k];int difference=int(n.range(15,0))-int(center.range(15,0));
       bool valid=n.range(63,56)==255&&difference>=-128&&difference<=128;
       unsigned weight=valid?(j==3?2:1)*(k==3?2:1):0;weights+=weight;
       for(int channel=0;channel<3;++channel){
#pragma HLS UNROLL
        normal_sum[channel]+=unsigned(n.range(39+channel*8,32+channel*8))*weight;
       }
      }
     }
     for(int channel=0;channel<3;++channel){
#pragma HLS UNROLL
      v.range(39+channel*8,32+channel*8)=(normal_sum[channel]+weights/2)/weights;
     }
     v.range(63,56)=255;
    }
    v.range(23,16)=(sum*255+8)/16;
    v.range(31,24)=hi&&!lo?255:outer&&!hi?128:0;output.write(v);
   }
  }
 }
}
static void pack(hls::stream<ap_uint<64>>& pixels,hls::stream<ScopeAxis>& output,unsigned count){
 for(unsigned i=0;i<count/8;++i){
  ScopeAxis word;word.data=0;word.keep=-1;word.strb=-1;word.user=0;word.last=i+1==count/8;
  for(int j=0;j<8;++j){
#pragma HLS PIPELINE II=1
   word.data.range(j*64+63,j*64)=pixels.read();
  }
  output.write(word);
 }
}
static void render(hls::stream<ScopeAxis>& output,const int p[16]){
#pragma HLS DATAFLOW
 hls::stream<ap_uint<64>> raw("raw"),edges("edges");
#pragma HLS STREAM variable=raw depth=256
#pragma HLS STREAM variable=edges depth=256
 trace(raw,p);outline(raw,edges,p[0],p[1]);pack(edges,output,unsigned(p[0])*p[1]);
}
void scope_visual(hls::stream<ScopeAxis>& input,hls::stream<ScopeAxis>& output,unsigned operation,unsigned input_words,unsigned output_words,unsigned& status){
#pragma HLS INTERFACE axis port=input
#pragma HLS INTERFACE axis port=output
#pragma HLS INTERFACE s_axilite port=operation bundle=control
#pragma HLS INTERFACE s_axilite port=input_words bundle=control
#pragma HLS INTERFACE s_axilite port=output_words bundle=control
#pragma HLS INTERFACE s_axilite port=status bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
#pragma HLS ARRAY_PARTITION variable=normal_matrix complete
#pragma HLS ARRAY_PARTITION variable=field complete dim=1
#pragma HLS ARRAY_PARTITION variable=field complete dim=2
#pragma HLS BIND_STORAGE variable=field type=ram_t2p impl=uram latency=3
#pragma HLS ARRAY_PARTITION variable=directory complete dim=1
#pragma HLS ARRAY_PARTITION variable=directory complete dim=2
#pragma HLS BIND_STORAGE variable=directory type=ram_t2p impl=bram
#pragma HLS ARRAY_PARTITION variable=leaf_map complete dim=1
#pragma HLS ARRAY_PARTITION variable=leaf_map complete dim=2
#pragma HLS BIND_STORAGE variable=leaf_map type=ram_t2p impl=bram
 status=0;bool framing_error=false,map_error=false;int p[16];
#pragma HLS ARRAY_PARTITION variable=p complete
 ap_uint<112> remainder[8];
#pragma HLS ARRAY_PARTITION variable=remainder complete
 for(unsigned bank=0;bank<8;++bank){
#pragma HLS UNROLL
  remainder[bank]=0;
 }
 unsigned field_fill=0,field_address=0;
 if(!input_words||!output_words)return;
 for(unsigned i=0;i<input_words;++i){
#pragma HLS PIPELINE II=1
  ScopeAxis word=input.read();
  if(bool(word.last)!=(i+1==input_words)||bool(word.user)!=(i==0)||word.keep!=ap_uint<64>(-1)||word.strb!=ap_uint<64>(-1))framing_error=true;
  if(i==0){for(int j=0;j<16;++j){
#pragma HLS UNROLL
   p[j]=int(word.data.range(j*32+31,j*32));
  }}else if(operation==0&&i<SCENE_WORDS){
   if(i<=DIR_WORDS+LEAF_WORDS){
    for(int copy=0;copy<2;++copy){
#pragma HLS UNROLL
     for(int bank=0;bank<8;++bank){
#pragma HLS UNROLL
      ap_uint<64> value=word.data.range(bank*64+63,bank*64);
      if(i<=DIR_WORDS){directory[copy][bank][i-1]=value;
       for(int j=0;j<4;++j){
#pragma HLS UNROLL
        if(copy==0&&unsigned(value.range(j*16+15,j*16))>unsigned(p[15]&255))map_error=true;
       }
       if(copy==0&&bank&&value!=word.data.range(63,0))map_error=true;
      }else {leaf_map[copy][bank][i-1-DIR_WORDS]=value;
       for(int j=0;j<4;++j){
#pragma HLS UNROLL
        if(copy==0&&unsigned(value.range(j*16+15,j*16))>unsigned(p[5]))map_error=true;
       }
      }
     }
    }
   }else {
    bool emit=field_fill+56>=70;
    for(int bank=0;bank<8;++bank){
#pragma HLS UNROLL
     ap_uint<64> value=word.data.range(bank*64+63,bank*64);ap_uint<56> compact=0;
     for(int j=0;j<4;++j){
#pragma HLS UNROLL
      ap_uint<16> sample=value.range(j*16+15,j*16);ap_int<13> q=sample.range(12,0);
      if(sample.range(15,14)!=0||(sample[13]&&q<=0)||q<-(4<<((p[15]>>8)&7)))map_error=true;
      compact.range(j*14+13,j*14)=sample.range(13,0);
     }
     ap_uint<112> combined=remainder[bank]|(ap_uint<112>(compact)<<field_fill);
     if(emit){
      field[0][bank][field_address]=combined.range(69,0);
      field[1][bank][field_address]=combined.range(69,0);
      remainder[bank]=combined>>70;
     }else remainder[bank]=combined;
    }
    if(emit){++field_address;field_fill=field_fill+56-70;}else field_fill+=56;
   }
  }
 }
 status=framing_error?1:map_error?5:0;
 if(operation==0){
  loaded=false;
  if(input_words!=SCENE_WORDS||output_words!=1||p[0]<2||p[0]>SX||p[1]<2||p[1]>SY||p[2]<2||p[2]>SZ||unsigned(p[4])!=SCENE_MAGIC||p[5]<0||p[5]>MAX_BLOCKS||(p[15]&255)>MAX_PAGES||unsigned(p[15])>>16||(((p[15]>>8)&255)!=5&&((p[15]>>8)&255)!=6))status=2;
  if(!status){
   nx=p[0];ny=p[1];nz=p[2];mx=(nx+3)/4;my=(ny+3)/4;mz=(nz+3)/4;
   page_stride_y=(nx+31)/32;page_stride_z=page_stride_y*((ny+31)/32);outside_q=-(4<<((p[15]>>8)&255));
      for(int j=0;j<9;++j){
#pragma HLS UNROLL
    if(p[6+j]<-32767||p[6+j]>32767)status=6;
    normal_matrix[j]=p[6+j];
   }
   scene_token=p[3];block_count=p[5];loaded=!status;
  }
 }else if(operation==1){
  if(!loaded||input_words!=1||p[0]<16||p[0]>MAX_WIDTH||p[0]%16||p[1]<4||p[1]>MAX_HEIGHT||p[2]<1||p[2]>1023||output_words!=1+unsigned(p[0]*p[1])/8)status=3;
 }else status=4;
 ScopeAxis ack;ack.data=0;ack.data.range(31,0)=status;ack.data.range(63,32)=p[3];ack.data.range(95,64)=scene_token;
 ack.keep=-1;ack.strb=-1;ack.user=1;ack.last=output_words==1;output.write(ack);
 if(!status&&operation==1)render(output,p);
 else for(unsigned i=1;i<output_words;++i){
#pragma HLS PIPELINE II=1
  ack.data=0;ack.user=0;ack.last=i+1==output_words;output.write(ack);
 }
}
