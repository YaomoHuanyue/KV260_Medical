// Independent PS benchmark. No runtime fallback and no PS Marching Cubes.
// Keep float accumulation/decision order identical to accepted PL smoothing.
#include "../../hls/mesh_smooth.hpp"
#include <cmath>
#include <cstring>
#include <vector>
#include <omp.h>

static SmoothPoint add(SmoothPoint a,SmoothPoint b){return {a.x+b.x,a.y+b.y,a.z+b.z,0};}
static SmoothPoint sub(SmoothPoint a,SmoothPoint b){return {a.x-b.x,a.y-b.y,a.z-b.z,0};}
static SmoothPoint scale(SmoothPoint a,float s){return {a.x*s,a.y*s,a.z*s,0};}
static float dot(SmoothPoint a,SmoothPoint b){return (a.x*b.x+a.y*b.y)+a.z*b.z;}
static SmoothPoint cross(SmoothPoint a,SmoothPoint b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x,0};}
static bool finite(SmoothPoint a){return std::isfinite(a.x)&&std::isfinite(a.y)&&std::isfinite(a.z);}
static float norm(SmoothPoint a){return std::sqrt(dot(a,a));}
static uint32_t bits(float v){uint32_t b;std::memcpy(&b,&v,4);return b;}

static double average(const SmoothPoint* source,const SmoothPoint* original,
    const uint32_t* rows,const SmoothEdge* edges,const uint32_t* frozen,
    SmoothPoint* output,uint32_t nv,bool expand,float coefficient,float limit,
    std::vector<float>& magnitudes,int threads){
#pragma omp parallel for schedule(static) num_threads(threads)
    for(uint32_t i=0;i<nv;++i){
        SmoothPoint mean={0,0,0,0};
        for(uint32_t j=rows[i];j<rows[i+1];++j){
            SmoothPoint p=source[edges[j].index];float w=edges[j].weight;
            mean={std::fma(p.x,w,mean.x),std::fma(p.y,w,mean.y),std::fma(p.z,w,mean.z),0};
        }
        SmoothPoint delta=sub(mean,source[i]);
        if(!expand){output[i]=delta;magnitudes[i]=norm(delta);}
        else{
            SmoothPoint trial=sub(source[i],scale(delta,coefficient));
            SmoothPoint displacement=sub(trial,original[i]);float length=norm(displacement);
            float factor=length>limit?limit/length:1.f;
            output[i]=frozen[i]?original[i]:add(original[i],scale(displacement,factor));
        }
    }
    // Serial, ordered double accumulation preserves strict acceptance decisions.
    double sum=0;if(!expand)for(uint32_t i=0;i<nv;++i)sum+=double(magnitudes[i]);
    return sum/double(nv);
}

static bool orientation(const SmoothPoint* original,const SmoothPoint* trial,
                        const SmoothFace* faces,uint32_t nf,int threads){
    int good=1;
#pragma omp parallel for schedule(static) num_threads(threads) reduction(&:good)
    for(uint32_t i=0;i<nf;++i){
        SmoothFace f=faces[i];
        SmoothPoint n0=cross(sub(original[f.b],original[f.a]),sub(original[f.c],original[f.a]));
        SmoothPoint n1=cross(sub(trial[f.b],trial[f.a]),sub(trial[f.c],trial[f.a]));
        good&=finite(trial[f.a])&&finite(trial[f.b])&&finite(trial[f.c])&&finite(n1)
              &&(!(dot(n0,n0)>1e-24f)||dot(n0,n1)>0);
    }
    return good!=0;
}

extern "C" int diagnostic_smooth_fma_r112(const SmoothPoint* original,const uint32_t* rows,
    const SmoothEdge* edges,const uint32_t* frozen,const SmoothFace* faces,
    SmoothPoint* current,SmoothPoint* half,SmoothPoint* candidate,
    SmoothPoint* lap,SmoothPoint* next_lap,uint32_t* report,
    uint32_t nv,uint32_t nf,uint32_t nnz,float limit,uint32_t iterations,int threads){
    if(!report)return 1;
    for(int i=0;i<16;++i)report[i]=0;
    if(!original||!rows||!edges||!frozen||!faces||!current||!half||!candidate||!lap||!next_lap
       ||!nv||nv>1000000||nf>2000000||nnz>12000000||iterations<1||iterations>16
       ||!std::isfinite(limit)||limit<=0||(threads!=1&&threads!=4))return report[0]=1;
    if(rows[0]!=0||rows[nv]!=nnz)return report[0]=2;
    for(uint32_t i=0;i<nv;++i)if(rows[i]>rows[i+1]||rows[i+1]>nnz||frozen[i]>1||!finite(original[i]))return report[0]=2;
    for(uint32_t i=0;i<nnz;++i)if(edges[i].index>=nv||!std::isfinite(edges[i].weight)||edges[i].weight<=0)return report[0]=2;
    for(uint32_t i=0;i<nf;++i)if(faces[i].a>=nv||faces[i].b>=nv||faces[i].c>=nv)return report[0]=2;
    std::memcpy(current,original,size_t(nv)*sizeof(SmoothPoint));std::vector<float> magnitudes(nv);
    double roughness=average(current,original,rows,edges,frozen,lap,nv,false,0,limit,magnitudes,threads);
    report[2]=bits(float(roughness));unsigned accepted=0,attempts=0;
    for(unsigned iteration=0;iteration<iterations;++iteration){
        bool advanced=false;float step=1.f;
        for(unsigned retry=0;retry<4;++retry,step*=.5f){
            ++attempts;float coefficient=.5f*step;
#pragma omp parallel for schedule(static) num_threads(threads)
            for(uint32_t i=0;i<nv;++i)half[i]=frozen[i]?original[i]:add(current[i],scale(lap[i],coefficient));
            average(half,original,rows,edges,frozen,candidate,nv,true,.53f*step,limit,magnitudes,threads);
            if(!orientation(original,candidate,faces,nf,threads))continue;
            double next=average(candidate,original,rows,edges,frozen,next_lap,nv,false,0,limit,magnitudes,threads);
            if(!std::isfinite(next)||!(next<roughness))continue;
            std::memcpy(current,candidate,size_t(nv)*sizeof(SmoothPoint));std::memcpy(lap,next_lap,size_t(nv)*sizeof(SmoothPoint));
            roughness=next;++accepted;advanced=true;break;
        }
        if(!advanced)break;
    }
    report[1]=accepted;report[3]=bits(float(roughness));report[4]=attempts;return 0;
}
