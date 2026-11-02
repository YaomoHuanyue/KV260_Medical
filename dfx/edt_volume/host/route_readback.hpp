#pragma once
#include <cstddef>
#include <cstdint>
#include <stdexcept>

struct RouteReadback {
 size_t bytes;
 bool points_known;
 uint64_t points;
};

// Static DMA still drains/writes every word of the frozen 8706-word frame.
// Only the CPU cache synchronization range changes. Successful upload replies
// are one word; valid raw-audit requests state their exact output length.
inline RouteReadback route_readback_plan(const uint64_t* request,unsigned input_words,
                                        unsigned capacity_words,unsigned route_copy){
 RouteReadback plan{size_t(capacity_words)*64,false,0};
 if(!route_copy)return plan;
 if(capacity_words!=8706)throw std::runtime_error("Route readback capacity");
 if(route_copy==1){plan.bytes=64;return plan;}
 if(route_copy==3&&request&&input_words&&request[0]==0x4155444954303031ULL
    &&request[1]<=4096&&uint64_t(input_words)==request[1]+1){
  plan.bytes=size_t(request[1]+1)*64;plan.points_known=true;plan.points=request[1];
 }
 return plan;
}

// Check before extraction: a corrupt/mismatched header must never cause a read
// outside the synchronized prefix, even if the BO has a larger allocation.
inline void validate_route_readback(const RouteReadback& plan,const uint64_t* header){
 if(plan.points_known&&(header[0]||header[1]!=plan.points||header[2]!=0x4155444954303031ULL))
  throw std::runtime_error("Audit output differs from synchronized request range");
}
