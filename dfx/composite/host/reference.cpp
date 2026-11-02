#include "../hls/algorithm.hpp"
#ifdef _OPENMP
#include <omp.h>
#endif
extern "C" int composite_reference(const uint32_t*input,uint32_t*output,unsigned pixels,unsigned stride,
                                    uint32_t background,unsigned threads){
 if(!input||!output||!pixels||pixels>640*512||pixels%16||stride<pixels||stride>640*512||!threads||threads>4)return 2;
#ifndef _OPENMP
 if(threads!=1)return 2;
#endif
#ifdef _OPENMP
#pragma omp parallel for num_threads(threads) schedule(static)
#endif
 for(unsigned i=0;i<pixels;++i){
  uint32_t color[4],depth[4];
  for(unsigned layer=0;layer<4;++layer){color[layer]=input[(layer*2)*stride+i];depth[layer]=input[(layer*2+1)*stride+i];}
  output[i]=depthcompose::pixel(color,depth,background);
 }
 return 0;
}
extern "C" unsigned composite_blend(unsigned source,unsigned destination,unsigned alpha){
 return depthcompose::blend(uint8_t(source),uint8_t(destination),uint8_t(alpha));
}
// The comparison also skips inactive PS layers; a four-layer software baseline
// would overstate the benefit of the active-layer hardware path.
extern "C" int composite_reference_layers(const uint32_t*input,uint32_t*output,unsigned pixels,unsigned stride,
                                          uint32_t background,unsigned threads,unsigned active){
 if(!input||!output||!pixels||pixels>640*512||pixels%16||stride<pixels||stride>640*512||!threads||threads>4||active<1||active>4)return 2;
#ifndef _OPENMP
 if(threads!=1)return 2;
#endif
#ifdef _OPENMP
#pragma omp parallel for num_threads(threads) schedule(static)
#endif
 for(unsigned i=0;i<pixels;++i){
  unsigned order[4];uint32_t colors[4],depths[4];
  for(unsigned j=0;j<active;++j){colors[j]=input[j*2*stride+i];depths[j]=input[(j*2+1)*stride+i];order[j]=j;}
  // Stable ascending depth then layer index, followed by far-to-near blending.
  for(unsigned j=1;j<active;++j){unsigned k=j,v=order[j];uint64_t key=(uint64_t(depths[v]&0xffffff)<<2)|v;
   while(k&&(((uint64_t(depths[order[k-1]]&0xffffff)<<2)|order[k-1])>key)){order[k]=order[k-1];--k;}order[k]=v;
  }
  uint32_t result=background|0xff000000;
  for(unsigned j=active;j;--j){unsigned k=order[j-1],alpha=(depths[k]>>24)?colors[k]>>24:0;uint32_t next=0xff000000;
   for(unsigned channel=0;channel<3;++channel){unsigned shift=channel*8;next|=(((colors[k]>>shift&255)*alpha+(result>>shift&255)*(255-alpha)+127)/255)<<shift;}result=next;
  }
  output[i]=result;
 }
 return 0;
}
