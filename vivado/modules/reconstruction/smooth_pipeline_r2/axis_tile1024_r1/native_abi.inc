#ifdef SMOOTH_NATIVE
#include <cstring>
#include <stdexcept>
struct NativeGraphContext {
    const EdgeWord* edges;uint32_t nv,nnz,requests=0,cursor=0,words=0,finals=0,errors=0;
    bool armed=false;
};
static thread_local uint64_t native_graph_stats[8]={};
static smooth_graph_axis::Word native_graph_read(void* pointer){
    NativeGraphContext& c=*static_cast<NativeGraphContext*>(pointer);
    const uint32_t words=(c.nnz+7)/8;
    if(!c.armed||c.cursor>=words)throw std::runtime_error("unrequested graph transfer");
    smooth_graph_axis::Word word{};
    for(unsigned lane=0;lane<8;++lane){
        const uint32_t index=c.cursor*8+lane;
        if(index<c.nnz)std::memcpy(&word.data[lane],c.edges+index,8);
    }
    word.keep=word.strb=~uint64_t(0);word.user=c.cursor==0;word.last=c.cursor+1==words;
    ++c.cursor;++c.words;return word;
}
static void native_graph_write(void* pointer,const smooth_graph_axis::Word& word){
    NativeGraphContext& c=*static_cast<NativeGraphContext*>(pointer);
    uint32_t f[16];std::memcpy(f,word.data,64);
    if(word.keep!=~uint64_t(0)||word.strb!=~uint64_t(0)||word.user!=1||word.last!=1||
       f[0]!=0x31474d53u||f[1]!=1||f[3]!=c.requests||f[4]!=c.nv||f[5]!=c.nnz||
       f[6]!=(c.nnz+7)/8||f[10]!=c.words||f[11]||f[12]||f[13]||f[14]||f[15])
        throw std::runtime_error("graph header mismatch");
    const uint64_t address=uint64_t(f[8])|(uint64_t(f[9])<<32);
    if(address!=reinterpret_cast<uintptr_t>(c.edges))throw std::runtime_error("graph owner mismatch");
    if(c.armed&&c.cursor!=(c.nnz+7)/8)throw std::runtime_error("undrained previous graph");
    if(f[2]==1){
        if(!c.nnz||c.finals)throw std::runtime_error("invalid graph request");
        ++c.requests;c.cursor=0;c.armed=true;
    }else if(f[2]==2){++c.finals;c.errors=f[7];}
    else throw std::runtime_error("invalid graph header kind");
}
extern "C" SM_EXPORT uint64_t mesh_axis_stat(uint32_t field){return field<8?native_graph_stats[field]:0;}
// Test-only original pointer ABI. Production hardware consumes the actual
// AXIS input; this adapter's packing callbacks are excluded from synthesis.
extern "C" SM_EXPORT void mesh_smooth(const PointWord* original,
    const uint32_t* rows,const EdgeWord* edges,const uint32_t* frozen,
    const FaceWord* faces,PointMemory current,PointMemory half,PointMemory candidate,
    PointMemory lap,PointMemory next_lap,uint32_t* report,uint32_t nv,uint32_t nf,
    uint32_t nnz,float limit,uint32_t iterations){
    NativeGraphContext context{edges,nv,nnz};GraphInput input{&context,native_graph_read};
    GraphOutput output{&context,native_graph_write};
    for(unsigned i=0;i<8;++i)native_graph_stats[i]=0;
    try{
        mesh_smooth_axis(input,output,original,rows,reinterpret_cast<uintptr_t>(edges),frozen,faces,
            current,half,candidate,lap,next_lap,report,nv,nf,nnz,limit,iterations);
        if(context.finals!=1)throw std::runtime_error("missing final graph frame");
        native_graph_stats[0]=context.errors;native_graph_stats[1]=context.requests;
        native_graph_stats[2]=context.words;native_graph_stats[3]=context.finals;
    }catch(...){report[0]=0x41584953u;native_graph_stats[0]=0x80000000u;}
}
#endif
