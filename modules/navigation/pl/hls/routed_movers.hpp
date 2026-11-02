#pragma once
#include "types.hpp"
extern "C" void nav_reader_split(const Word* input,Stream<Packet>& edt,Stream<Packet>& route,uint32_t count,uint32_t select);
extern "C" void nav_writer_merge(Stream<Packet>& edt,Stream<Packet>& route,Word* output,uint32_t capacity,uint32_t& status,uint32_t& written,uint32_t select);
