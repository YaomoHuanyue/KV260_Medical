#pragma once
#include "types.hpp"
constexpr unsigned ROUTE_NODES=4096,ROUTE_POINTS=4096,ROUTE_TILES=65536,ROUTE_BRICKS=4096;
constexpr unsigned ROUTE_OUTPUT_WORDS=2+(ROUTE_NODES+7)/8+ROUTE_POINTS*2;
constexpr unsigned ROUTE_TARGET_LANES=1;
constexpr uint64_t ROUTE_SCENE_MAGIC=0x4e41565343454e31ULL;
constexpr uint64_t ROUTE_QUERY_MAGIC=0x4e41565155455231ULL;
extern "C" void nav_route(Stream<Packet>& input,Stream<Packet>& output,
    uint32_t operation,uint32_t input_count,uint32_t output_count,uint32_t& status);
