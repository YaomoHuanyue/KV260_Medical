// Same FMA2 ABI/math. Reuse cacheable BOs and read source files into them.
// Every logical buffer retains both complete4096-byte red zones on every call.
template<class T>
static void read_smooth_input(const std::filesystem::path& file,T* target,size_t count) {
    std::ifstream source(file,std::ios::binary|std::ios::ate);
    require(bool(source)&&source.tellg()==std::streamoff(count*sizeof(T)),"Input size mismatch: "+file.string());
    source.seekg(0);
    if(count)source.read(reinterpret_cast<char*>(target),count*sizeof(T));
    require(bool(source),"Input read failed");
}

static void smooth_job_impl(Session& s,SmoothWorkspace& pool,
    const std::filesystem::path& dir,const std::filesystem::path& output,
    const std::filesystem::path& report,double heap_release_seconds) {
    const auto begin=Clock::now();
    unsigned nv,nf,nnz,iterations;float limit;
    std::ifstream config(dir/"config.txt");config>>nv>>nf>>nnz>>limit>>iterations;
    require(bool(config)&&nv>0&&nv<=1000000&&nf<=2000000&&nnz<=12000000&&
        std::isfinite(limit)&&limit>0&&iterations>=1&&iterations<=16,"Invalid smoothing configuration");
    const std::array<size_t,11> sizes={size_t(nv)*16,size_t(nv+1)*4,size_t(nnz)*8,size_t(nv)*4,
        size_t(nf)*16,size_t(nv)*16,size_t(nv)*16,size_t(nv)*16,size_t(nv)*16,size_t(nv)*16,64};
    const std::array<const char*,5> names={"original.bin","rows.bin","edges.bin","frozen.bin","faces.bin"};
    for(unsigned j=0;j<5;++j)
        require(std::filesystem::is_regular_file(dir/names[j])&&std::filesystem::file_size(dir/names[j])==sizes[j],
            "Input size mismatch: "+(dir/names[j]).string());
    const double config_seconds=seconds(begin);
    const unsigned old_allocations=pool.allocations,old_reuses=pool.reuses;
    const auto allocation_start=Clock::now();
    std::array<unsigned char*,11> mapped{};std::array<uint64_t,11> addresses{};
    for(unsigned j=0;j<11;++j) {
        const size_t requested=sizes[j]+2*GUARD;
        if(!pool.buffers[j]||pool.capacities[j]<requested) {
            pool.buffers[j].reset();pool.capacities[j]=0;
            pool.buffers[j]=std::make_unique<xrt::bo>(s.buffer(requested,xrt::bo::flags::cacheable));
            pool.capacities[j]=requested;++pool.allocations;
        }else ++pool.reuses;
        mapped[j]=pool.buffers[j]->map<unsigned char*>();addresses[j]=pool.buffers[j]->address()+GUARD;
        require(addresses[j]%64==0,"Smoothing BO alignment");
        std::memset(mapped[j],0xa7,GUARD);std::memset(mapped[j]+GUARD+sizes[j],0xa7,GUARD);
    }
    const double allocation_seconds=seconds(allocation_start);
    const auto read_start=Clock::now();
    read_smooth_input(dir/names[0],reinterpret_cast<SmoothPoint*>(mapped[0]+GUARD),nv);
    read_smooth_input(dir/names[1],reinterpret_cast<uint32_t*>(mapped[1]+GUARD),size_t(nv)+1);
    read_smooth_input(dir/names[2],reinterpret_cast<SmoothEdge*>(mapped[2]+GUARD),nnz);
    read_smooth_input(dir/names[3],reinterpret_cast<uint32_t*>(mapped[3]+GUARD),nv);
    read_smooth_input(dir/names[4],reinterpret_cast<SmoothFace*>(mapped[4]+GUARD),nf);
    const double read_seconds=seconds(read_start);
    const auto validation_start=Clock::now();
    const auto* points=reinterpret_cast<const SmoothPoint*>(mapped[0]+GUARD);
    const auto* rows=reinterpret_cast<const uint32_t*>(mapped[1]+GUARD);
    const auto* edges=reinterpret_cast<const SmoothEdge*>(mapped[2]+GUARD);
    const auto* frozen=reinterpret_cast<const uint32_t*>(mapped[3]+GUARD);
    const auto* faces=reinterpret_cast<const SmoothFace*>(mapped[4]+GUARD);
    for(size_t i=0;i<nv;++i)require(std::isfinite(points[i].x)&&std::isfinite(points[i].y)&&std::isfinite(points[i].z),"Nonfinite point");
    require(rows[0]==0&&rows[nv]==nnz&&std::is_sorted(rows,rows+size_t(nv)+1),"Invalid CSR");
    for(size_t i=0;i<nnz;++i)require(edges[i].index<nv&&std::isfinite(edges[i].weight)&&edges[i].weight>0,"Invalid edge");
    for(size_t i=0;i<nf;++i)require(faces[i].a<nv&&faces[i].b<nv&&faces[i].c<nv,"Invalid face");
    for(size_t i=0;i<nv;++i)require(frozen[i]<=1,"Invalid frozen flag");
    const double validation_seconds=seconds(validation_start);
    const auto input_sync_start=Clock::now();
    for(unsigned j=0;j<11;++j) {
        if(j<5)pool.buffers[j]->sync(XCL_BO_SYNC_BO_TO_DEVICE,sizes[j]+2*GUARD,0);
        else {
            pool.buffers[j]->sync(XCL_BO_SYNC_BO_TO_DEVICE,GUARD,0);
            pool.buffers[j]->sync(XCL_BO_SYNC_BO_TO_DEVICE,GUARD,GUARD+sizes[j]);
        }
    }
    const double input_sync_seconds=seconds(input_sync_start);
    const auto select_start=Clock::now();s.select("smooth");const double selection_seconds=seconds(select_start);
    const auto control_start=Clock::now();
    for(unsigned j=0;j<11;++j) {
        require(pool.buffers[j]->address()+GUARD==addresses[j],"Smoothing BO moved during DFX");
        s.arg(0x10+j*16,uint32_t(addresses[j]));s.arg(0x14+j*16,uint32_t(addresses[j]>>32));
    }
    uint32_t bits;std::memcpy(&bits,&limit,4);
    s.arg(0xc0,nv);s.arg(0xc8,nf);s.arg(0xd0,nnz);s.arg(0xd8,bits);s.arg(0xe0,iterations);
    const double control_seconds=seconds(control_start);
    const double compute=s.execute(180);
    const auto guards_start=Clock::now();std::array<unsigned char,2*GUARD> snapshot{};
    for(unsigned j=0;j<11;++j) {
        pool.buffers[j]->sync(XCL_BO_SYNC_BO_FROM_DEVICE,GUARD,0);
        pool.buffers[j]->sync(XCL_BO_SYNC_BO_FROM_DEVICE,GUARD,GUARD+sizes[j]);
        std::memcpy(snapshot.data(),mapped[j],GUARD);std::memcpy(snapshot.data()+GUARD,mapped[j]+GUARD+sizes[j],GUARD);
        require(std::all_of(snapshot.begin(),snapshot.end(),[](unsigned char v){return v==0xa7;}),"Smoothing DMA guard damaged");
    }
    const double guard_seconds=seconds(guards_start);
    const auto output_sync_start=Clock::now();
    pool.buffers[10]->sync(XCL_BO_SYNC_BO_FROM_DEVICE,sizes[10],GUARD);
    std::array<uint32_t,16> result{};std::memcpy(result.data(),mapped[10]+GUARD,64);
    require(result[0]==0,"Smoothing report error");
    pool.buffers[5]->sync(XCL_BO_SYNC_BO_FROM_DEVICE,sizes[5],GUARD);
    const double output_sync_seconds=seconds(output_sync_start);
    const auto write_start=Clock::now();std::ofstream file(output,std::ios::binary);
    file.write(reinterpret_cast<const char*>(mapped[5]+GUARD),sizes[5]);file.close();require(bool(file),"Smoothing output failed");
    const double write_seconds=seconds(write_start);
    float before,after;std::memcpy(&before,result.data()+2,4);std::memcpy(&after,result.data()+3,4);
    std::ofstream metadata(report);
    metadata<<"{\"backend\":\"dfx_pl\",\"kernel\":\"FMA2\",\"compute_seconds\":"<<compute
        <<",\"partial_seconds\":"<<s.load_seconds<<",\"switch_seconds\":"<<s.switch_seconds
        <<",\"host_seconds\":"<<seconds(begin)+heap_release_seconds<<",\"accepted_iterations\":"<<result[1]
        <<",\"attempts\":"<<result[4]<<",\"roughness_before_mm\":"<<before<<",\"roughness_after_mm\":"<<after
        <<",\"DMA_red_zones_checked\":22,\"pool_allocations_this_call\":"<<pool.allocations-old_allocations
        <<",\"pool_reused_buffers_this_call\":"<<pool.reuses-old_reuses<<",\"pool_capacity_bytes\":"<<pool.reserved_bytes()
        <<",\"intermediate_input_vector_bytes\":0,\"host_scope_includes_input_read_validation_and_heap_release\":true"
        <<",\"phase_seconds\":{\"heap_release\":"<<heap_release_seconds<<",\"configuration\":"<<config_seconds
        <<",\"allocation_and_canaries\":"<<allocation_seconds<<",\"direct_input_read\":"<<read_seconds
        <<",\"input_validation\":"<<validation_seconds<<",\"input_sync\":"<<input_sync_seconds
        <<",\"DFX_selection\":"<<selection_seconds<<",\"control\":"<<control_seconds<<",\"execution\":"<<compute
        <<",\"all22_guard_checks\":"<<guard_seconds<<",\"output_sync\":"<<output_sync_seconds<<",\"output_write\":"<<write_seconds
        <<"},\"report_words\":[";
    for(unsigned i=0;i<16;++i){if(i)metadata<<',';metadata<<result[i];}
    metadata<<"]}\n";metadata.close();require(bool(metadata),"Smoothing metadata failed");
}
