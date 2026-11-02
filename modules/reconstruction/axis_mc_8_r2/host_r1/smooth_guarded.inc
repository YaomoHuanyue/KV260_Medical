// Original smoothing ABI/validation, with cacheable BOs and all 22 DMA guards.
static void smooth_job_impl(Session& s,const std::filesystem::path& dir,
    const std::filesystem::path& output,const std::filesystem::path& report) {
    unsigned nv,nf,nnz,iterations;float limit;
    std::ifstream config(dir/"config.txt");config>>nv>>nf>>nnz>>limit>>iterations;
    require(bool(config)&&nv>0&&nv<=1000000&&nf<=2000000&&nnz<=12000000&&
        std::isfinite(limit)&&limit>0&&iterations>=1&&iterations<=16,"Invalid smoothing configuration");
    auto points=read<SmoothPoint>(dir/"original.bin",nv);
    auto rows=read<uint32_t>(dir/"rows.bin",nv+1);
    auto edges=read<SmoothEdge>(dir/"edges.bin",nnz);
    auto frozen=read<uint32_t>(dir/"frozen.bin",nv);
    auto faces=read<SmoothFace>(dir/"faces.bin",nf);
    for(auto p:points)require(std::isfinite(p.x)&&std::isfinite(p.y)&&std::isfinite(p.z),"Nonfinite point");
    require(rows.front()==0&&rows.back()==nnz&&std::is_sorted(rows.begin(),rows.end()),"Invalid CSR");
    for(auto e:edges)require(e.index<nv&&std::isfinite(e.weight)&&e.weight>0,"Invalid edge");
    for(auto f:faces)require(f.a<nv&&f.b<nv&&f.c<nv,"Invalid face");
    for(auto v:frozen)require(v<=1,"Invalid frozen flag");
    const auto begin=Clock::now();
    const std::array<size_t,11> sizes={size_t(nv)*16,rows.size()*4,size_t(nnz)*8,size_t(nv)*4,
        size_t(nf)*16,size_t(nv)*16,size_t(nv)*16,size_t(nv)*16,size_t(nv)*16,size_t(nv)*16,64};
    const std::array<const void*,5> source={points.data(),rows.data(),edges.data(),frozen.data(),faces.data()};
    std::vector<xrt::bo> buffers;buffers.reserve(11);
    std::array<unsigned char*,11> mapped{};std::array<uint64_t,11> addresses{};
    for(unsigned j=0;j<11;++j) {
        buffers.push_back(s.buffer(sizes[j]+2*GUARD,xrt::bo::flags::cacheable));
        mapped[j]=buffers[j].map<unsigned char*>();addresses[j]=buffers[j].address()+GUARD;
        require(addresses[j]%64==0,"Smoothing BO alignment");
        std::memset(mapped[j],0xa7,GUARD);std::memset(mapped[j]+GUARD+sizes[j],0xa7,GUARD);
        if(j<5) {
            if(sizes[j])std::memcpy(mapped[j]+GUARD,source[j],sizes[j]);
            buffers[j].sync(XCL_BO_SYNC_BO_TO_DEVICE,sizes[j]+2*GUARD,0);
        }else {
            buffers[j].sync(XCL_BO_SYNC_BO_TO_DEVICE,GUARD,0);
            buffers[j].sync(XCL_BO_SYNC_BO_TO_DEVICE,GUARD,GUARD+sizes[j]);
        }
    }
    s.select("smooth");
    for(unsigned j=0;j<11;++j) {
        require(buffers[j].address()+GUARD==addresses[j],"Smoothing BO moved during DFX");
        s.arg(0x10+j*16,uint32_t(addresses[j]));s.arg(0x14+j*16,uint32_t(addresses[j]>>32));
    }
    uint32_t bits;std::memcpy(&bits,&limit,4);
    s.arg(0xc0,nv);s.arg(0xc8,nf);s.arg(0xd0,nnz);s.arg(0xd8,bits);s.arg(0xe0,iterations);
    const double compute=s.execute(180);
    std::array<unsigned char,2*GUARD> snapshot{};
    for(unsigned j=0;j<11;++j) {
        buffers[j].sync(XCL_BO_SYNC_BO_FROM_DEVICE,GUARD,0);
        buffers[j].sync(XCL_BO_SYNC_BO_FROM_DEVICE,GUARD,GUARD+sizes[j]);
        std::memcpy(snapshot.data(),mapped[j],GUARD);
        std::memcpy(snapshot.data()+GUARD,mapped[j]+GUARD+sizes[j],GUARD);
        require(std::all_of(snapshot.begin(),snapshot.end(),[](unsigned char v){return v==0xa7;}),"Smoothing DMA guard damaged");
    }
    buffers[10].sync(XCL_BO_SYNC_BO_FROM_DEVICE,sizes[10],GUARD);
    std::array<uint32_t,16> result{};std::memcpy(result.data(),mapped[10]+GUARD,64);
    require(result[0]==0,"Smoothing report error");
    buffers[5].sync(XCL_BO_SYNC_BO_FROM_DEVICE,sizes[5],GUARD);
    std::ofstream file(output,std::ios::binary);file.write(reinterpret_cast<const char*>(mapped[5]+GUARD),sizes[5]);
    file.close();require(bool(file),"Smoothing output failed");
    float before,after;std::memcpy(&before,result.data()+2,4);std::memcpy(&after,result.data()+3,4);
    std::ofstream metadata(report);
    metadata<<"{\"backend\":\"dfx_pl\",\"kernel\":\"FMA2\",\"compute_seconds\":"<<compute
        <<",\"partial_seconds\":"<<s.load_seconds<<",\"switch_seconds\":"<<s.switch_seconds
        <<",\"host_seconds\":"<<seconds(begin)<<",\"accepted_iterations\":"<<result[1]
        <<",\"attempts\":"<<result[4]<<",\"roughness_before_mm\":"<<before
        <<",\"roughness_after_mm\":"<<after<<",\"DMA_red_zones_checked\":22,\"report_words\":[";
    for(unsigned i=0;i<16;++i){if(i)metadata<<',';metadata<<result[i];}
    metadata<<"]}\n";metadata.close();require(bool(metadata),"Smoothing metadata failed");
}
