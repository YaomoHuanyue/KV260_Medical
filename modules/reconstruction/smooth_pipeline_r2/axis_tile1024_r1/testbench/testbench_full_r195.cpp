// Reuse every numerical fixture without changing the accepted source.
// Strengthen the invalid-scalar post-check to cover all sixteen report words.
#define main immutable_full_fixture_main
#include "testbench_all_banks_r150.cpp"
#undef main


// Finite medical input can overflow its accumulated mean. Later finite terms
// must not turn an infinite accumulator into NaN. All vertices are frozen so
// every stored candidate remains finite; the complete roughness/decision and
// five raw work banks are compared against independent std::fma.
static int run_finite_overflow_case(){
    const unsigned nv=2;
    std::vector<SmoothPoint> original={{3.0e38f,0,1,0},{-3.0e38f,0,1,0}},ref(nv),rh(nv),rc(nv),rl(nv),rn(nv);
    std::vector<uint32_t> rows(65537),fixed(65537);rows[1]=3;rows[2]=6;fixed[0]=fixed[1]=1;
    std::vector<SmoothEdge> edges={{0,2.f},{1,2.f},{0,2.f},{1,2.f},{0,2.f},{1,2.f}};
    std::vector<PointWord> wire(65537),out(65537),half(65537),candidate(65537),lap(65537),next(65537);
    std::vector<EdgeWord> graph(131072);std::vector<FaceWord> face(8192);
    for(unsigned i=0;i<nv;++i)wire[i]=pack(original[i]);
    for(unsigned i=0;i<edges.size();++i)graph[i]=pack(edges[i]);
    uint32_t report[16],expected[16];SmoothFace dummy={0,0,0,0};
    accepted::accepted_mesh_smooth(original.data(),rows.data(),edges.data(),fixed.data(),&dummy,ref.data(),rh.data(),rc.data(),rl.data(),rn.data(),expected,nv,0,6,.31f,1);
    fixture_smooth(wire.data(),rows.data(),graph.data(),fixed.data(),face.data(),out.data(),half.data(),candidate.data(),lap.data(),next.data(),report,nv,0,6,.31f,1,expected);
    for(unsigned i=0;i<16;++i)std::printf("OVERFLOW REPORT word=%u actual=%08x expected=%08x\n",i,report[i],expected[i]);
    if(std::memcmp(report,expected,sizeof(report))||report[1]!=0||report[4]!=4||report[2]!=0x7f800000u||report[3]!=0x7f800000u)return 7;
    const std::vector<PointWord>* banks[5]={&out,&half,&candidate,&lap,&next};
    const std::vector<SmoothPoint>* refs[5]={&ref,&rh,&rc,&rl,&rn};
    if(compare_banks(banks,refs,nv))return 8;
    std::puts("PASS finite overflow accumulation all five banks and sixteen reports exact");return 0;
}

int main(){
    if(run_finite_overflow_case()||run_circular_case()||run_case(67,0)||run_case(129,1)||run_case(1031,1)||run_case(33,2))return 1;
    std::vector<PointWord> p(65537),a(65537),b(65537),c(65537),d(65537),e(65537);
    std::vector<uint32_t> rows(65537),fixed(65537);uint32_t r[16]={0x403ffdf0u,0x00000000u,0x40024d43u,0x00000001u,0x400512a0u,0x00000001u,0x4002c982u,0x00000001u,0x40740750u,0x00000000u,0x00000100u,0x00000000u,0x40740780u,0x00000000u,0x00000030u,0x00000000u};
    std::vector<EdgeWord> edge(131072);std::vector<FaceWord> face(8192);
    fixture_smooth(p.data(),rows.data(),edge.data(),fixed.data(),face.data(),a.data(),b.data(),c.data(),d.data(),e.data(),r,0,0,0,.3f,1,nullptr);
    if(r[0]!=1)return 3;
    for(unsigned i=1;i<16;++i)if(r[i]!=0)return 3;
    std::puts("PASS invalid nv=0 report exact");
#ifdef _WIN32
    if(accepted::oracle_calls_r150!=6)return 9;
    std::puts("PASS six independent native oracle invocations plus explicit invalid case");
#endif
    std::puts("ALL FULL INTEGER FMA SEVEN STRICT CASES PASSED");return 0;
}
