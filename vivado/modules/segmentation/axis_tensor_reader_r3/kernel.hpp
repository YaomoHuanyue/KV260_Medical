#pragma once
#include "../../../dfx/medical/algorithms/segmentation/stream_types.hpp"
extern "C" void ct_tensor_reader(const W256* input,Stream<P256>& pixels,
 uint32_t height,uint32_t width,uint32_t cin,uint32_t kernel,
 const W256* skip,const W256* tables,uint32_t mode,uint32_t channels_a,
 uint32_t channels_b,uint32_t factor_a,uint32_t factor_b,uint32_t& status);
