// Testbench only: native libm std::fma, outside the HLS simulation compiler.
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
        const char* path=std::getenv("FULL_SMOOTH_REFERENCE_SO");
        if(!path||!path[0]){std::puts("Missing explicitly bound native oracle SO");std::exit(1);}
        // Keep the native libm reference independent of simulator math symbols.
        void* module=::dlopen(path,RTLD_NOW|RTLD_LOCAL|RTLD_DEEPBIND);
        if(!module){std::printf("Independent oracle load failed: %s\n",::dlerror());std::exit(1);}
        reference=reinterpret_cast<Reference>(::dlsym(module,"mesh_smooth"));
        if(!reference){std::puts("Independent oracle symbol missing");std::exit(1);}
    }
    ++oracle_calls_r150;
    reference(original,rows,edges,frozen,faces,current,half,candidate,lap,next,report,nv,nf,nnz,limit,iterations);
}
