#pragma once
#include <QMatrix4x4>
#include <QVector4D>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>

namespace medical_tiles {
constexpr unsigned edge=16;
struct Box {uint16_t x0,y0,x1,y1;};
struct Active {
 unsigned columns,rows;
 std::vector<unsigned> integral;
 Active(const std::vector<uint32_t>&pixels,unsigned width,unsigned height):
  columns((width+edge-1)/edge),rows((height+edge-1)/edge),integral((columns+1)*(rows+1),0){
  for(unsigned y=0;y<height;++y)for(unsigned x=0;x<width;++x)
   if(pixels[y*width+x])integral[(y/edge+1)*(columns+1)+x/edge+1]=1;
  for(unsigned y=1;y<=rows;++y)for(unsigned x=1;x<=columns;++x)
   integral[y*(columns+1)+x]+=integral[(y-1)*(columns+1)+x]+integral[y*(columns+1)+x-1]-integral[(y-1)*(columns+1)+x-1];
 }
 bool intersects(const Box&b)const{
  if(b.x0>=b.x1||b.y0>=b.y1)return false;
  auto s=columns+1;
  return integral[b.y1*s+b.x1]+integral[b.y0*s+b.x0]!=integral[b.y0*s+b.x1]+integral[b.y1*s+b.x0];
 }
};
// Conservative one-pixel halo includes fixed-point rasterization boundaries.
// Triangles behind/at the camera use the whole viewport to avoid false culls.
inline Box bounds(const float*vertices,const QMatrix4x4&mvp,unsigned width,unsigned height){
 float x0=1e30f,y0=1e30f,x1=-1e30f,y1=-1e30f;
 unsigned columns=(width+edge-1)/edge,rows=(height+edge-1)/edge;
 for(unsigned k=0;k<3;++k){auto p=vertices+k*6;auto c=mvp*QVector4D(p[0],p[1],p[2],1);
  if(!std::isfinite(c.w())||c.w()<=0)return {0,0,uint16_t(columns),uint16_t(rows)};
  float x=(c.x()/c.w()+1)*width*.5f,y=(c.y()/c.w()+1)*height*.5f;
  x0=std::min(x0,x);x1=std::max(x1,x);y0=std::min(y0,y);y1=std::max(y1,y);
 }
 auto clip=[](int a,unsigned limit){return uint16_t(std::max(0,std::min(a,int(limit))));};
 return {clip(int(std::floor((x0-1)/edge)),columns),clip(int(std::floor((y0-1)/edge)),rows),
         clip(int(std::floor((x1+1)/edge))+1,columns),clip(int(std::floor((y1+1)/edge))+1,rows)};
}
}
