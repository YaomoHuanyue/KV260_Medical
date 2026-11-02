#include "hls/types.hpp"
#include "hls/route.hpp"
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif
extern "C" EXPORT int nav_native_run(const uint64_t* input,uint64_t* output,unsigned length,unsigned groups,unsigned weight,unsigned mode){
    if(!length||length>NAV_MAX_LINE||groups>NAV_MAX_GROUPS||!weight||mode>1)return 1;
    try{
        Stream<Packet> a,b;uint32_t status=0,write_status=0;
        nav_reader(reinterpret_cast<const Word*>(input),a,length*groups);
        nav_edt(a,b,length,groups,weight,mode,status);
        nav_writer(b,reinterpret_cast<Word*>(output),length*groups,write_status);
        return status|write_status;
    }catch(...){return 3;}
}
extern "C" EXPORT int nav_native_route(const uint64_t* input,uint64_t* output,unsigned input_count,unsigned output_count,unsigned operation){
    try{
        Stream<Packet> a,b;uint32_t status=0,writer=0,written=0;
        nav_reader(reinterpret_cast<const Word*>(input),a,input_count);
        nav_route(a,b,operation,input_count,output_count,status);
        nav_route_writer(b,reinterpret_cast<Word*>(output),output_count,writer,written);
        return status|writer;
    }catch(...){return 255;}
}
