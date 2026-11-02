#include "types.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <vector>

static void set_byte(VolumeWord&word,unsigned index,unsigned value){
#ifdef EDT_VOLUME_NATIVE
 unsigned lane=index/8,shift=(index%8)*8;
 word.lane[lane]=(word.lane[lane]&~(uint64_t(255)<<shift))|(uint64_t(value)<<shift);
#else
 word.range(index*8+7,index*8)=value;
#endif
}
static uint32_t get32(const VolumeWord&word,unsigned index){return uint32_t(cost(word,index/2)>>((index%2)*32));}

static bool run(unsigned nz,unsigned ny,unsigned nx,unsigned pattern,uint32_t wz,uint32_t wy,uint32_t wx){
 unsigned mw=(nx+63)/64,cw=(nx+7)/8,fw=(nx+15)/16,rows=nz*ny;
 std::vector<VolumeWord> mask(std::max(rows*mw,VOLUME_SIM_WORDS)+1),a(std::max(rows*cw,VOLUME_SIM_WORDS)+1),b(a.size()),field(std::max(rows*fw,VOLUME_SIM_WORDS)+1);
 for(auto&word:mask)for(unsigned lane=0;lane<8;++lane)cost(word,lane,~uint64_t(0));
 for(auto*volume:{&a,&b,&field})for(auto&word:*volume)for(unsigned lane=0;lane<8;++lane)cost(word,lane,0xa5b6c7d8e9fa1023ull);
 std::vector<unsigned char> binary(uint64_t(rows)*nx);std::vector<unsigned> background;
 for(unsigned z=0;z<nz;++z)for(unsigned y=0;y<ny;++y)for(unsigned x=0;x<nx;++x){
  unsigned id=(z*ny+y)*nx+x;
  bool foreground=pattern==0?false:pattern==1?true:pattern==2?(id*131+z*17+y*11)%7<4:true;
  if(pattern==3&&z==nz/2&&y==ny/2&&x==nx/2)foreground=false;
  binary[id]=foreground;if(!foreground)background.push_back(id);
  set_byte(mask[(z*ny+y)*mw+x/64],x%64,foreground?255:0);
 }
 unsigned status=99;edt_volume(mask.data(),a.data(),b.data(),field.data(),nz,ny,nx,wz,wy,wx,status);
 if(status!=(background.empty()?2u:0u)){std::cerr<<"status mismatch\n";return false;}
 for(unsigned z=0;z<nz;++z)for(unsigned y=0;y<ny;++y)for(unsigned x=0;x<nx;++x){
  uint64_t expected=VOLUME_INF;unsigned id=(z*ny+y)*nx+x;
  if(!binary[id])expected=0;
  else for(unsigned point:background){
   int64_t pz=point/(nx*ny),py=(point/nx)%ny,px=point%nx,dz=int64_t(z)-pz,dy=int64_t(y)-py,dx=int64_t(x)-px;
   expected=std::min(expected,uint64_t(wz)*uint64_t(dz*dz)+uint64_t(wy)*uint64_t(dy*dy)+uint64_t(wx)*uint64_t(dx*dx));
  }
  if(cost(a[(z*ny+y)*cw+x/8],x%8)!=expected){std::cerr<<"squared mismatch "<<nz<<","<<ny<<","<<nx<<" @ "<<id<<"\n";return false;}
  uint32_t bits=get32(field[(z*ny+y)*fw+x/16],x%16);float actual;std::memcpy(&actual,&bits,4);
  if(expected==VOLUME_INF){if(!std::isinf(actual))return false;}
  else{double ref=std::sqrt(double(expected)/1048576.);if(std::abs(actual-ref)>2e-6*std::max(1.,ref)){std::cerr<<"float mismatch\n";return false;}}
 }
 for(unsigned row=0;row<rows;++row){
  for(unsigned x=nx;x<cw*8;++x)if(cost(a[row*cw+x/8],x%8)!=0)return false;
  for(unsigned x=nx;x<fw*16;++x)if(get32(field[row*fw+x/16],x%16)!=0)return false;
 }
 for(auto*volume:{&a,&b,&field}){
  unsigned payload=volume==&field?rows*fw:rows*cw;
  for(unsigned i=payload;i<volume->size();++i)for(unsigned lane=0;lane<8;++lane)
   if(cost((*volume)[i],lane)!=0xa5b6c7d8e9fa1023ull){std::cerr<<"write guard corrupted\n";return false;}
 }
 return true;
}

int main(){
 unsigned shapes[][3]={{1,1,1},{1,7,5},{3,5,7},{2,3,17},{3,2,33},{2,3,65},
  {2,2,129},{2,3,127},{3,2,128},{2,3,255},{3,2,256},{2,3,257},
  {1,1,1024},{1,1024,1},{1024,1,1}};
 unsigned cases=0;
 for(auto&shape:shapes)for(unsigned pattern=0;pattern<4;++pattern){
  if(!run(shape[0],shape[1],shape[2],pattern,6553600,608400,1587321))return 1;++cases;
 }
 std::vector<VolumeWord> mask(VOLUME_SIM_WORDS),a(VOLUME_SIM_WORDS),b(VOLUME_SIM_WORDS),out(VOLUME_SIM_WORDS);
 for(auto*volume:{&mask,&a,&b,&out})for(auto&word:*volume)for(unsigned lane=0;lane<8;++lane)cost(word,lane,0x12345678);
 unsigned status=0;
 edt_volume(mask.data(),a.data(),b.data(),out.data(),0,1,1,1,1,1,status);
 if(status!=1)return 1;
 edt_volume(mask.data(),a.data(),b.data(),out.data(),1024,1024,1024,1,1,1,status);
 if(status!=1)return 1;
 edt_volume(mask.data(),a.data(),b.data(),out.data(),1,1,1,0,1,1,status);
 if(status!=1)return 1;
 for(auto*volume:{&mask,&a,&b,&out})for(auto&word:*volume)for(unsigned lane=0;lane<8;++lane)if(cost(word,lane)!=0x12345678)return 1;
 std::cout<<"PASS "<<cases<<" exact brute-force volumes, float distance, padding, guards, and three invalid jobs\n";
 return 0;
}
