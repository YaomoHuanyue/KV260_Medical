#pragma once
#include <xrt/xrt_bo.h>
#include "graph_memory.hpp"

namespace smooth_d9 {
struct XrtCoherence {
    void to_device(xrt::bo& buffer,size_t bytes,size_t offset){buffer.sync(XCL_BO_SYNC_BO_TO_DEVICE,bytes,offset);}
    void from_device(xrt::bo& buffer,size_t bytes,size_t offset){buffer.sync(XCL_BO_SYNC_BO_FROM_DEVICE,bytes,offset);}
};
using XrtGraphHeaderMemory=GraphHeaderMemory<xrt::bo,XrtCoherence>;
}
