// CPU comparison baseline. This file has no XRT, device or mesh generation.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <omp.h>

struct V { double x,y,z; };
static V add(V a,V b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
static V sub(V a,V b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
static V mul(V a,double s){return {a.x*s,a.y*s,a.z*s};}
static double dot(V a,V b){return (a.x*b.x+a.y*b.y)+a.z*b.z;}
static V cross(V a,V b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
static V load(const double* a){return {a[0],a[1],a[2]};}

static double triangle(V p,const double* t,V& nearest){
 V a=load(t),b=load(t+3),c=load(t+6);V starts[3]={a,b,c},ends[3]={b,c,a};
 double best=std::numeric_limits<double>::infinity();
 for(int j=0;j<3;++j){
  V edge=sub(ends[j],starts[j]);double den=dot(edge,edge);
  double factor=den>0?std::min(1.,std::max(0.,dot(sub(p,starts[j]),edge)/den)):0.;
  V q=add(starts[j],mul(edge,factor)),d=sub(p,q);double value=dot(d,d);
  if(value<best){best=value;nearest=q;}
 }
 V ab=sub(b,a),ac=sub(c,a),normal=cross(ab,ac),pa=sub(p,a);double den=dot(normal,normal);
 if(den>0){
  double v=dot(cross(pa,ac),normal)/den,w=dot(cross(ab,pa),normal)/den;
  if(v>=0&&w>=0&&v+w<=1){V q=add(add(a,mul(ab,v)),mul(ac,w)),d=sub(p,q);double value=dot(d,d);
   if(value<best){best=value;nearest=q;}
  }
 }
 return std::sqrt(best);
}

extern "C" uint64_t mesh_distance_abi(){return 0x4d455348434c0001ULL;}

extern "C" int mesh_distance_native(const double* p,const double* triangles,
 const uint64_t* offsets,const uint64_t* indices,unsigned n,unsigned nt,
 uint64_t pairs,unsigned threads,double* distance,double* closest,uint64_t* ids){
 if(!p||!triangles||!offsets||!indices||!distance||!closest||!ids||!n||n>4096||
    !nt||nt>1000000||!pairs||pairs>100000000||threads<1||threads>4)return 1;
 if(offsets[0]!=0||offsets[n]!=pairs)return 2;
 for(unsigned i=0;i<n;++i)if(offsets[i]>=offsets[i+1]||offsets[i+1]>pairs)return 2;
 for(uint64_t i=0;i<pairs;++i)if(indices[i]>=nt)return 3;
 for(unsigned i=0;i<n*3;++i)if(!std::isfinite(p[i]))return 4;
 for(uint64_t i=0;i<uint64_t(nt)*9;++i)if(!std::isfinite(triangles[i]))return 4;
 #pragma omp parallel for num_threads(threads) schedule(static)
 for(unsigned i=0;i<n;++i){
  V point=load(p+3*i),bestPoint{};double best=std::numeric_limits<double>::infinity();uint64_t winner=0;
  for(uint64_t j=offsets[i];j<offsets[i+1];++j){V q;uint64_t index=indices[j];double d=triangle(point,triangles+9*index,q);
   if(d<best){best=d;bestPoint=q;winner=index;}
  }
  distance[i]=best;closest[3*i]=bestPoint.x;closest[3*i+1]=bestPoint.y;closest[3*i+2]=bestPoint.z;ids[i]=winner;
 }
 return 0;
}
