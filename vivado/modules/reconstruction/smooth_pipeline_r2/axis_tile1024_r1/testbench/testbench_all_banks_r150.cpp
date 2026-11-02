#ifdef SMOOTH_NATIVE
#define TEST_NATIVE
#endif
#include "fixture_axis.hpp"
#include <cstdlib>
#ifdef _WIN32
#include <windows.h>
#endif
#include <cmath>
#include <queue>
#include <vector>
#include <cstring>
#include <cstdio>
#ifndef SMOOTH_NATIVE
#define SMOOTH_NATIVE
#endif
#define mesh_smooth accepted_mesh_smooth
namespace accepted {
#ifdef _WIN32
#include "oracle_bridge_r150.inc"
#else
#include "oracle_reference.inc"
#endif
}
#undef mesh_smooth
#undef SMOOTH_NATIVE

static PointWord pack(SmoothPoint p){
#ifdef TEST_NATIVE
    return p;
#else
    union{float f;uint32_t u;}a,b,c,d;a.f=p.x;b.f=p.y;c.f=p.z;d.f=p.pad;
    PointWord w;w.range(31,0)=a.u;w.range(63,32)=b.u;w.range(95,64)=c.u;w.range(127,96)=d.u;return w;
#endif
}
static SmoothPoint unpack(PointWord w){
#ifdef TEST_NATIVE
    return w;
#else
    union{float f;uint32_t u;}a,b,c,d;a.u=w.range(31,0);b.u=w.range(63,32);c.u=w.range(95,64);d.u=w.range(127,96);
    return {a.f,b.f,c.f,d.f};
#endif
}
static EdgeWord pack(SmoothEdge e){
#ifdef TEST_NATIVE
    return e;
#else
    union{float f;uint32_t u;}a;a.f=e.weight;EdgeWord w;w.range(31,0)=e.index;w.range(63,32)=a.u;return w;
#endif
}
static FaceWord pack(SmoothFace f){
#ifdef TEST_NATIVE
    return f;
#else
    FaceWord w;w.range(31,0)=f.a;w.range(63,32)=f.b;w.range(95,64)=f.c;w.range(127,96)=f.pad;return w;
#endif
}

static int compare_banks(const std::vector<PointWord>* banks[5],
    const std::vector<SmoothPoint>* refs[5],unsigned nv){
    for(unsigned bank=0;bank<5;++bank){
        for(unsigned i=0;i<nv;++i){
            SmoothPoint actual=unpack((*banks[bank])[i]);
            if(std::memcmp(&actual,&(*refs[bank])[i],sizeof(actual))){
                std::printf("FULL BANK mismatch bank=%u vertex=%u nv=%u\n",bank,i,nv);return 1;
            }
        }
        for(unsigned i=nv;i<banks[bank]->size();++i){
            SmoothPoint actual=unpack((*banks[bank])[i]);SmoothPoint zero={0,0,0,0};
            if(std::memcmp(&actual,&zero,sizeof(actual))){
                std::printf("TAIL WRITE bank=%u vertex=%u nv=%u\n",bank,i,nv);return 1;
            }
        }
    }
    return 0;
}

static int run_case(unsigned nv,unsigned kind){
    std::vector<SmoothPoint> original(nv),current(nv),ref(nv),rh(nv),rc(nv),rl(nv),rn(nv);
    // Co-simulation captures the full declared AXI depth for each argument.
    std::vector<uint32_t> rows(65537),frozen(65537);std::vector<SmoothEdge> edges;std::vector<SmoothFace> faces;
    for(unsigned i=0;i<nv;++i){
        original[i]={float(i%13)*.7f,float((i/13)%13)*1.1f,float(i/169)*.4f+.05f*std::sin(float(i)),0};
        frozen[i]=(i%17==0);rows[i]=edges.size();
        unsigned degree=kind==1 && i%11==0?0:(kind==2?257:2+(i%7));
        for(unsigned k=0;k<degree;++k)edges.push_back({(i+k+1)%nv,1.f/float(degree)});
    }
    rows[nv]=edges.size();
    if(kind==0){for(unsigned i=0;i+14<nv;i+=13)faces.push_back({i,i+1,i+13,0});}
    std::vector<PointWord> wire(65537),out(65537),half(65537),candidate(65537),lap(65537),next(65537);
    std::vector<EdgeWord> graph(131072);std::vector<FaceWord> triangle(8192);
    for(unsigned i=0;i<nv;++i)wire[i]=pack(original[i]);
    for(unsigned i=0;i<edges.size();++i)graph[i]=pack(edges[i]);
    for(unsigned i=0;i<faces.size();++i)triangle[i]=pack(faces[i]);
    uint32_t report[16]={0},expected[16]={0};float limit=.31f;unsigned iterations=3;
    accepted::accepted_mesh_smooth(original.data(),rows.data(),edges.data(),frozen.data(),faces.data(),ref.data(),rh.data(),rc.data(),rl.data(),rn.data(),expected,nv,faces.size(),edges.size(),limit,iterations);
    fixture_smooth(wire.data(),rows.data(),graph.data(),frozen.data(),triangle.data(),out.data(),half.data(),candidate.data(),lap.data(),next.data(),report,nv,faces.size(),edges.size(),limit,iterations,expected);
    const std::vector<PointWord>* actual_banks[5]={&out,&half,&candidate,&lap,&next};
    const std::vector<SmoothPoint>* reference_banks[5]={&ref,&rh,&rc,&rl,&rn};
    if(compare_banks(actual_banks,reference_banks,nv))return 6;
    for(unsigned i=0;i<nv;++i)current[i]=unpack(out[i]);
    if(std::memcmp(report,expected,sizeof(report)) || std::memcmp(current.data(),ref.data(),nv*sizeof(SmoothPoint))){std::printf("Exact packed coordinate/decision mismatch nv=%u kind=%u\n",nv,kind);return 1;}
    for(unsigned i=0;i<nv;++i){
        float x=current[i].x-original[i].x,y=current[i].y-original[i].y,z=current[i].z-original[i].z;
        if(std::sqrt((x*x+y*y)+z*z)>limit+2e-5f || (frozen[i] && std::memcmp(&current[i],&original[i],sizeof(SmoothPoint))))return 2;
    }
    std::printf("PASS packed nv=%u edges=%zu faces=%zu kind=%u accepted=%u attempts=%u exact\n",nv,edges.size(),faces.size(),kind,report[1],report[4]);return 0;
}


static int run_circular_case(){
    const unsigned nv=33001;
    std::vector<SmoothPoint> original(nv),ref(nv),rh(nv),rc(nv),rl(nv),rn(nv);
    std::vector<uint32_t> rows(65537),frozen(65537);
    std::vector<SmoothEdge> edges;
    for(unsigned i=0;i<nv;++i){
        original[i]={float(i%137)*.07f,float((i/137)%113)*.11f,float(i/15481)*.4f+.05f*std::sin(float(i)),0};
        frozen[i]=(i%97==0);rows[i]=edges.size();
        edges.push_back({(i+31)%nv,.5f});
        // Alternating range motion exercises reuse in both directions; the
        // last groups cross the physical index-modulo-32768 boundary.
        unsigned neighbor=(i/1024)&1 ? (i+nv-4096)%nv : (i+2048)%nv;
        edges.push_back({neighbor,.5f});
    }
    rows[nv]=edges.size();
    std::vector<PointWord> wire(65537),out(65537),half(65537),candidate(65537),lap(65537),next(65537);
    std::vector<EdgeWord> graph(131072);std::vector<FaceWord> faces(8192);
    for(unsigned i=0;i<nv;++i)wire[i]=pack(original[i]);
    for(unsigned i=0;i<edges.size();++i)graph[i]=pack(edges[i]);
    uint32_t report[16]={0},expected[16]={0};SmoothFace dummy={0,0,0,0};
    accepted::accepted_mesh_smooth(original.data(),rows.data(),edges.data(),frozen.data(),&dummy,ref.data(),rh.data(),rc.data(),rl.data(),rn.data(),expected,nv,0,edges.size(),.31f,1);
    fixture_smooth(wire.data(),rows.data(),graph.data(),frozen.data(),faces.data(),out.data(),half.data(),candidate.data(),lap.data(),next.data(),report,nv,0,edges.size(),.31f,1,expected);
    if(std::memcmp(report,expected,sizeof(report)))return 4;
    const std::vector<PointWord>* actual_banks[5]={&out,&half,&candidate,&lap,&next};
    const std::vector<SmoothPoint>* reference_banks[5]={&ref,&rh,&rc,&rl,&rn};
    if(compare_banks(actual_banks,reference_banks,nv))return 6;
    for(unsigned i=0;i<nv;++i){SmoothPoint actual=unpack(out[i]);if(std::memcmp(&actual,&ref[i],sizeof(actual)))return 5;}
    std::printf("PASS circular nv=%u edges=%zu exact coordinate/report\n",nv,edges.size());return 0;
}

int main(){
    if(run_circular_case()||run_case(67,0)||run_case(129,1)||run_case(1031,1)||run_case(33,2))return 1;
    std::vector<PointWord> p(65537),a(65537),b(65537),c(65537),d(65537),e(65537);
    std::vector<uint32_t> rows(65537),fixed(65537);uint32_t r[16];std::vector<EdgeWord> edge(131072);std::vector<FaceWord> face(8192);
    fixture_smooth(p.data(),rows.data(),edge.data(),fixed.data(),face.data(),a.data(),b.data(),c.data(),d.data(),e.data(),r,0,0,0,.3f,1,nullptr);
    if(r[0]!=1)return 3;
    std::puts("ALL C2 R3 STRICT PACKED CASES PASSED");return 0;
}
