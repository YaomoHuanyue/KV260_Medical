// Testbench-only independent native std::fma reference, already verified
// against original whole-core FMA gold on Windows and ARM. No DUT helper.
static unsigned oracle_calls_r150=0;
static void accepted_mesh_smooth(const SmoothPoint* original,const uint32_t* rows,
    const SmoothEdge* edges,const uint32_t* frozen,const SmoothFace* faces,
    SmoothPoint* current,SmoothPoint* half,SmoothPoint* candidate,SmoothPoint* lap,
    SmoothPoint* next,uint32_t* report,uint32_t nv,uint32_t nf,uint32_t nnz,float limit,uint32_t iterations){
    typedef void (*Reference)(const SmoothPoint*,const uint32_t*,const SmoothEdge*,
        const uint32_t*,const SmoothFace*,SmoothPoint*,SmoothPoint*,SmoothPoint*,
        SmoothPoint*,SmoothPoint*,uint32_t*,uint32_t,uint32_t,uint32_t,float,uint32_t);
    static Reference reference=nullptr;
    if(!reference){
        const char* path=std::getenv("FULL_SMOOTH_REFERENCE_DLL");
        if(!path||!path[0]){std::puts("Missing explicitly bound independent oracle DLL");std::exit(1);}
        HMODULE module=::LoadLibraryExA(path,nullptr,LOAD_WITH_ALTERED_SEARCH_PATH);
        if(!module){std::printf("Independent oracle load failed %lu\n",::GetLastError());std::exit(1);}
        reference=reinterpret_cast<Reference>(::GetProcAddress(module,"mesh_smooth"));
        if(!reference){std::puts("Independent oracle symbol missing");std::exit(1);}
    }
    ++oracle_calls_r150;
    reference(original,rows,edges,frozen,faces,current,half,candidate,lap,next,report,nv,nf,nnz,limit,iterations);
}
