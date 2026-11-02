#include <cstdint>
#include <cstring>
#include <algorithm>
#if defined(__aarch64__)
#include <arm_neon.h>
#endif
extern "C" void ct_lut(const uint8_t* src,uint8_t* dst,size_t count,const uint8_t* table){
 size_t i=0;
#if defined(__aarch64__)
 uint8x16x4_t a,b,c,d;
 for(unsigned k=0;k<4;k++){a.val[k]=vld1q_u8(table+k*16);b.val[k]=vld1q_u8(table+64+k*16);c.val[k]=vld1q_u8(table+128+k*16);d.val[k]=vld1q_u8(table+192+k*16);}
 for(;i+16<=count;i+=16){
  auto x=vld1q_u8(src+i);
  auto y=vorrq_u8(vqtbl4q_u8(a,x),vqtbl4q_u8(b,vsubq_u8(x,vdupq_n_u8(64))));
  y=vorrq_u8(y,vqtbl4q_u8(c,vsubq_u8(x,vdupq_n_u8(128))));
  y=vorrq_u8(y,vqtbl4q_u8(d,vsubq_u8(x,vdupq_n_u8(192))));vst1q_u8(dst+i,y);
 }
#endif
 for(;i<count;i++)dst[i]=table[src[i]];
}
extern "C" void ct_relu(const int8_t* src,int8_t* dst,size_t count,int zero){
 size_t i=0;
#if defined(__aarch64__)
 for(;i+16<=count;i+=16)vst1q_s8(dst+i,vmaxq_s8(vld1q_s8(src+i),vdupq_n_s8(int8_t(zero))));
#endif
 for(;i<count;i++)dst[i]=std::max(src[i],int8_t(zero));
}
extern "C" void ct_pool2(const int8_t* src,int8_t* dst,unsigned h,unsigned w,unsigned channels){
 for(unsigned y=0;y<h/2;y++)for(unsigned x=0;x<w/2;x++){
  const int8_t *a=src+(size_t(y*2)*w+x*2)*channels,*b=a+channels,*c=a+size_t(w)*channels,*d=c+channels;
  int8_t* out=dst+(size_t(y)*(w/2)+x)*channels;unsigned i=0;
#if defined(__aarch64__)
  for(;i+16<=channels;i+=16)vst1q_s8(out+i,vmaxq_s8(vmaxq_s8(vld1q_s8(a+i),vld1q_s8(b+i)),vmaxq_s8(vld1q_s8(c+i),vld1q_s8(d+i))));
  for(;i+8<=channels;i+=8)vst1_s8(out+i,vmax_s8(vmax_s8(vld1_s8(a+i),vld1_s8(b+i)),vmax_s8(vld1_s8(c+i),vld1_s8(d+i))));
#endif
  for(;i<channels;i++)out[i]=std::max(std::max(a[i],b[i]),std::max(c[i],d[i]));
 }
}
extern "C" void ct_resize2(const int8_t* src,int8_t* dst,unsigned h,unsigned w,unsigned channels){
 for(unsigned y=0;y<h;y++){
  int8_t* row=dst+size_t(y*2)*w*2*channels;
  for(unsigned x=0;x<w;x++){
   const int8_t* in=src+(size_t(y)*w+x)*channels;int8_t* out=row+size_t(x*2)*channels;
   std::memcpy(out,in,channels);std::memcpy(out+channels,in,channels);
  }
  std::memcpy(row+size_t(w)*2*channels,row,size_t(w)*2*channels);
 }
}
extern "C" void ct_concat2(const int8_t* a,const int8_t* b,int8_t* dst,unsigned pixels,unsigned ca,unsigned cb){
 for(unsigned p=0;p<pixels;p++){
  std::memcpy(dst+size_t(p)*(ca+cb),a+size_t(p)*ca,ca);
  std::memcpy(dst+size_t(p)*(ca+cb)+ca,b+size_t(p)*cb,cb);
 }
}

// Load each LUT once per operation, including when concatenating short vectors.
struct Lookup {
 const uint8_t* table;
 int clamp=-128;bool simple=true;
#if defined(__aarch64__)
 uint8x16x4_t a,b,c,d;
#endif
 explicit Lookup(const uint8_t* t):table(t){
  clamp=int8_t(t[128]);
  for(unsigned i=0;i<256;i++)if(int8_t(t[i])!=std::max(int(int8_t(i)),clamp)){simple=false;break;}
#if defined(__aarch64__)
  for(unsigned k=0;k<4;k++){a.val[k]=vld1q_u8(t+k*16);b.val[k]=vld1q_u8(t+64+k*16);c.val[k]=vld1q_u8(t+128+k*16);d.val[k]=vld1q_u8(t+192+k*16);}
#endif
 }
#if defined(__aarch64__)
 uint8x16_t vector(uint8x16_t x)const{
  if(simple)return vreinterpretq_u8_s8(vmaxq_s8(vreinterpretq_s8_u8(x),vdupq_n_s8(int8_t(clamp))));
  auto y=vorrq_u8(vqtbl4q_u8(a,x),vqtbl4q_u8(b,vsubq_u8(x,vdupq_n_u8(64))));
  y=vorrq_u8(y,vqtbl4q_u8(c,vsubq_u8(x,vdupq_n_u8(128))));
  return vorrq_u8(y,vqtbl4q_u8(d,vsubq_u8(x,vdupq_n_u8(192))));
 }
#endif
 void copy(const uint8_t* src,uint8_t* dst,size_t count)const{
  if(simple){
   if(clamp==-128)std::memcpy(dst,src,count);
   else ct_relu(reinterpret_cast<const int8_t*>(src),reinterpret_cast<int8_t*>(dst),count,clamp);
   return;
  }
  size_t i=0;
#if defined(__aarch64__)
  for(;i+16<=count;i+=16){
   auto x=vld1q_u8(src+i);
   auto y=vorrq_u8(vqtbl4q_u8(a,x),vqtbl4q_u8(b,vsubq_u8(x,vdupq_n_u8(64))));
   y=vorrq_u8(y,vqtbl4q_u8(c,vsubq_u8(x,vdupq_n_u8(128))));
   y=vorrq_u8(y,vqtbl4q_u8(d,vsubq_u8(x,vdupq_n_u8(192))));vst1q_u8(dst+i,y);
  }
#endif
  for(;i<count;i++)dst[i]=table[src[i]];
 }
};
extern "C" void ct_pool_transform(const int8_t* src,uint8_t* dst,unsigned h,unsigned w,unsigned channels,const uint8_t* table){
 const Lookup lut(table);
 for(unsigned y=0;y<h/2;y++)for(unsigned x=0;x<w/2;x++){
  const int8_t *a=src+(size_t(y*2)*w+x*2)*channels,*b=a+channels,*c=a+size_t(w)*channels,*d=c+channels;
  uint8_t* out=dst+(size_t(y)*(w/2)+x)*channels;unsigned i=0;
#if defined(__aarch64__)
  for(;i+16<=channels;i+=16){
   const auto maximum=vmaxq_s8(vmaxq_s8(vld1q_s8(a+i),vld1q_s8(b+i)),vmaxq_s8(vld1q_s8(c+i),vld1q_s8(d+i)));
   vst1q_u8(out+i,lut.vector(vreinterpretq_u8_s8(maximum)));
  }
#endif
  for(;i<channels;i++)out[i]=table[uint8_t(std::max(std::max(a[i],b[i]),std::max(c[i],d[i])))];
 }
}
extern "C" void ct_transform(const uint8_t* src,uint8_t* dst,unsigned h,unsigned w,unsigned channels,unsigned factor,const uint8_t* table){
 const Lookup lut(table);
 if(factor==1){lut.copy(src,dst,size_t(h)*w*channels);return;}
 for(unsigned y=0;y<h;y++){
  auto row=dst+size_t(y)*factor*w*factor*channels;
  for(unsigned x=0;x<w;x++){
   auto out=row+size_t(x)*factor*channels;
   lut.copy(src+(size_t(y)*w+x)*channels,out,channels);
   for(unsigned dx=1;dx<factor;dx++)std::memcpy(out+dx*channels,out,channels);
  }
  for(unsigned dy=1;dy<factor;dy++)std::memcpy(row+size_t(dy)*w*factor*channels,row,size_t(w)*factor*channels);
 }
}
extern "C" void ct_join_transform(const uint8_t* a,const uint8_t* b,uint8_t* dst,unsigned h,unsigned w,unsigned ca,unsigned cb,unsigned fa,unsigned fb,const uint8_t* ta,const uint8_t* tb){
 const Lookup la(ta),lb(tb);
 for(unsigned y=0;y<h;y++){
  const auto ar=a+size_t(y/fa)*(w/fa)*ca,br=b+size_t(y/fb)*(w/fb)*cb;
  for(unsigned x=0;x<w;x++){
   auto out=dst+(size_t(y)*w+x)*(ca+cb);
   const unsigned xa=fa==1?x:(fa==2?x/2:x/fa),xb=fb==1?x:(fb==2?x/2:x/fb);
   la.copy(ar+size_t(xa)*ca,out,ca);lb.copy(br+size_t(xb)*cb,out+ca,cb);
  }
 }
}
extern "C" void ct_context(const uint16_t* ct,const uint32_t* indices,const int8_t* table,int8_t* dst,unsigned h,unsigned w,unsigned hp,unsigned wp){
 const size_t plane=size_t(h)*w;
 const uint16_t *a=ct+indices[0]*plane,*b=ct+indices[1]*plane,*c=ct+indices[2]*plane,*d=ct+indices[3]*plane,*e=ct+indices[4]*plane;
 for(unsigned y=0;y<hp;y++)for(unsigned x=0;x<wp;x++){
  size_t i=size_t(std::min(y,h-1))*w+std::min(x,w-1);auto out=dst+(size_t(y)*wp+x)*5;
  out[0]=table[a[i]];out[1]=table[b[i]];out[2]=table[c[i]];out[3]=table[d[i]];out[4]=table[e[i]];
 }
}
extern "C" void ct_hu_lut(const uint16_t* src,int8_t* dst,size_t count,const int8_t* table){
 for(size_t i=0;i<count;i++)dst[i]=table[src[i]];
}
extern "C" void ct_context5(const int8_t* a,const int8_t* b,const int8_t* c,const int8_t* d,const int8_t* e,int8_t* dst,unsigned h,unsigned w,unsigned hp,unsigned wp){
 for(unsigned y=0;y<hp;y++){
  const size_t base=size_t(std::min(y,h-1))*w;unsigned x=0;
#if defined(__aarch64__)
  const auto zeros=vdupq_n_u8(0);
  for(;x+16<=w;x+=16){
   const auto av=vreinterpretq_u8_s8(vld1q_s8(a+base+x)),bv=vreinterpretq_u8_s8(vld1q_s8(b+base+x));
   const auto cv=vreinterpretq_u8_s8(vld1q_s8(c+base+x)),dv=vreinterpretq_u8_s8(vld1q_s8(d+base+x));
   const auto ev=vreinterpretq_u8_s8(vld1q_s8(e+base+x));
   uint16x8x4_t lo,hi;
   lo.val[0]=vreinterpretq_u16_u8(vzip1q_u8(av,bv));hi.val[0]=vreinterpretq_u16_u8(vzip2q_u8(av,bv));
   lo.val[1]=vreinterpretq_u16_u8(vzip1q_u8(cv,dv));hi.val[1]=vreinterpretq_u16_u8(vzip2q_u8(cv,dv));
   lo.val[2]=vreinterpretq_u16_u8(vzip1q_u8(ev,zeros));hi.val[2]=vreinterpretq_u16_u8(vzip2q_u8(ev,zeros));
   lo.val[3]=hi.val[3]=vdupq_n_u16(0);
   vst4q_u16(reinterpret_cast<uint16_t*>(dst+(size_t(y)*wp+x)*8),lo);
   vst4q_u16(reinterpret_cast<uint16_t*>(dst+(size_t(y)*wp+x+8)*8),hi);
  }
#endif
  for(;x<wp;x++){
   const size_t i=base+std::min(x,w-1);auto out=dst+(size_t(y)*wp+x)*8;
   out[0]=a[i];out[1]=b[i];out[2]=c[i];out[3]=d[i];out[4]=e[i];out[5]=out[6]=out[7]=0;
  }
 }
}
