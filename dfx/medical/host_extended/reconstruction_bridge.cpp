#include "shared_session.hpp"
#include "../algorithms/hls/mesh_smooth.hpp"
#include <array>
#include <cmath>
#include <sstream>
#include <sys/resource.h>
using namespace medical;
static void mc(Session& s,const std::filesystem::path& dir,const std::filesystem::path& output,const std::filesystem::path& report,uint32_t test_capacity=0){
 unsigned nx,ny,nz;std::ifstream config(dir/"dimensions.txt");config>>nx>>ny>>nz;
 require(bool(config)&&nx>=2&&ny>=2&&nz>=2&&nx<=512&&ny<=512&&nz<=512,"Invalid MC dimensions");
 auto mask=read<uint8_t>(dir/"mask.u8",size_t(nx)*ny*nz);require(std::all_of(mask.begin(),mask.end(),[](auto v){return v<2;}),"Nonbinary mask");
 auto total=Clock::now();auto input=s.buffer(mask.size());std::memcpy(input.map<void*>(),mask.data(),mask.size());input.sync(XCL_BO_SYNC_BO_TO_DEVICE);
 uint32_t capacity=uint32_t(std::min<size_t>(9*size_t(nx-1)*(ny-1)*(nz-1),32*1024*1024/24));
 if(test_capacity)capacity=std::min(capacity,test_capacity);
 auto out=s.buffer(size_t(capacity)*24);
 // Allocate before switching: the same BOs must survive DFX.
 auto ia=input.address(),oa=out.address();s.select("mc");require(ia==input.address()&&oa==out.address(),"BO moved during switch");
 unsigned passes=0,required=0,written=0,status=0;double compute=0;
 do {
  s.pointer(0x10,input);s.pointer(0x20,out);s.arg(0x30,nx);s.arg(0x38,ny);s.arg(0x40,nz);s.arg(0x48,capacity);s.arg(0x50,0);
  compute+=s.execute(60);++passes;required=s.ip->read_register(0x58);written=s.ip->read_register(0x68);status=s.ip->read_register(0x78);
  require(!(status&~2u),"MC status error");
  if(status==2){require(passes==1&&required>capacity&&written==capacity&&size_t(required)*24<=128*1024*1024,"Invalid MC overflow");capacity=required;out=s.buffer(size_t(capacity)*24);}
 }while(status==2);
 require(required==written,"Incomplete MC");size_t bytes=size_t(written)*24;if(bytes)out.sync(XCL_BO_SYNC_BO_FROM_DEVICE,bytes,0);
 std::ofstream f(output,std::ios::binary);f.write(out.map<const char*>(),bytes);require(bool(f),"MC output failed");
 std::ofstream r(report);r<<"{\"backend\":\"dfx_pl\",\"triangles\":"<<written<<",\"generation_passes\":"<<passes<<",\"compute_seconds\":"<<compute<<",\"partial_seconds\":"<<s.load_seconds<<",\"switch_seconds\":"<<s.switch_seconds<<",\"host_seconds\":"<<seconds(total)<<",\"input_bo\":"<<input.address()<<",\"output_bo\":"<<out.address()<<"}\n";
}
static void smooth(Session& s,const std::filesystem::path& dir,const std::filesystem::path& output,const std::filesystem::path& report){
 unsigned nv,nf,nnz,iterations;float limit;std::ifstream config(dir/"config.txt");config>>nv>>nf>>nnz>>limit>>iterations;
 require(bool(config)&&nv>0&&nv<=1000000&&nf<=2000000&&nnz<=12000000&&std::isfinite(limit)&&limit>0&&iterations>=1&&iterations<=16,"Invalid smoothing configuration");
 auto points=read<SmoothPoint>(dir/"original.bin",nv);auto rows=read<uint32_t>(dir/"rows.bin",nv+1);auto edges=read<SmoothEdge>(dir/"edges.bin",nnz);auto frozen=read<uint32_t>(dir/"frozen.bin",nv);auto faces=read<SmoothFace>(dir/"faces.bin",nf);
 for(auto p:points)require(std::isfinite(p.x)&&std::isfinite(p.y)&&std::isfinite(p.z),"Nonfinite point");
 require(rows.front()==0&&rows.back()==nnz&&std::is_sorted(rows.begin(),rows.end()),"Invalid CSR");
 for(auto e:edges){require(e.index<nv&&std::isfinite(e.weight)&&e.weight>0,"Invalid edge");}
 for(auto f:faces){require(f.a<nv&&f.b<nv&&f.c<nv,"Invalid face");}
 for(auto v:frozen){require(v<=1,"Invalid frozen flag");}
 auto total=Clock::now();std::vector<xrt::bo> buffers;buffers.reserve(11);
 auto input=[&](const void* data,size_t bytes){buffers.push_back(s.buffer(bytes));if(bytes)std::memcpy(buffers.back().map<void*>(),data,bytes);buffers.back().sync(XCL_BO_SYNC_BO_TO_DEVICE);};
 input(points.data(),nv*16);input(rows.data(),rows.size()*4);input(edges.data(),nnz*8);input(frozen.data(),nv*4);input(faces.data(),nf*16);
 for(unsigned j=0;j<5;++j){buffers.push_back(s.buffer(nv*16));}
 buffers.push_back(s.buffer(64));
 std::vector<uint64_t> addresses;for(auto& b:buffers)addresses.push_back(b.address());s.select("smooth");
 for(unsigned j=0;j<11;++j){require(buffers[j].address()==addresses[j],"BO moved during switch");s.pointer(0x10+j*0x10,buffers[j]);}
 uint32_t bits;std::memcpy(&bits,&limit,4);s.arg(0xc0,nv);s.arg(0xc8,nf);s.arg(0xd0,nnz);s.arg(0xd8,bits);s.arg(0xe0,iterations);
 double compute=s.execute(180);buffers[10].sync(XCL_BO_SYNC_BO_FROM_DEVICE);auto result=buffers[10].map<const uint32_t*>();require(result[0]==0,"Smoothing report error");
 buffers[5].sync(XCL_BO_SYNC_BO_FROM_DEVICE);std::ofstream out(output,std::ios::binary);out.write(buffers[5].map<const char*>(),nv*16);require(bool(out),"Smoothing output failed");
 float before,after;std::memcpy(&before,result+2,4);std::memcpy(&after,result+3,4);
 std::ofstream r(report);r<<"{\"backend\":\"dfx_pl\",\"compute_seconds\":"<<compute<<",\"partial_seconds\":"<<s.load_seconds<<",\"switch_seconds\":"<<s.switch_seconds<<",\"host_seconds\":"<<seconds(total)<<",\"accepted_iterations\":"<<result[1]<<",\"attempts\":"<<result[4]<<",\"roughness_before_mm\":"<<before<<",\"roughness_after_mm\":"<<after<<"}\n";
}

extern "C" int medical_reconstruction_job(void* handle,const char* operation,const char* folder,const char* output,const char* report){
 try {auto& s=*static_cast<medical::Handle*>(handle)->session;std::lock_guard<std::recursive_mutex> guard(s.operation_mutex);std::string op(operation);
 if(op=="mc")mc(s,folder,output,report);else if(op=="smooth")smooth(s,folder,output,report);else throw std::runtime_error("Unknown reconstruction job");return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<"\n";return -1;}
}
