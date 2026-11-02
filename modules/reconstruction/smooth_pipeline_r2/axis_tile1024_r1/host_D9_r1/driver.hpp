#pragma once
#include "protocol.hpp"
#include <chrono>
#include <exception>

namespace smooth_d9 {
struct Poll {
    bool reader_done=false,reader_idle=false,writer_done=false,writer_idle=false;
    bool core_done=false,core_idle=false;
};
// Port owns no lifetime here: the caller keeps every input/output BO and its
// exclusive PL lock until return. retain_active MUST NOT return/free buffers.
// This driver does not load firmware, isolate a live RM, or reset any DMA.
template<class Port>
Result execute(Port& port,Config config,double timeout_seconds=180) {
    Protocol protocol(config);
    require(timeout_seconds>0&&timeout_seconds<=3600,"D9 invalid completion deadline");
    port.preflight(config);
    bool active=false;
    try {
        active=true;
        port.arm_header();             // Receive REQUEST before starting core.
        port.start_core();             // Exactly once for the complete job.
        bool writer_armed=true,writer_done=false,reader_pending=false;
        bool reader_done=false,core_done=false,final=false;
        const auto begin=std::chrono::steady_clock::now();
        for(;;) {
            const Poll status=port.poll();
            // HLS ap_done is clear-on-read. Never require the three pulses to
            // occur in the same poll or lose an early completion.
            writer_done|=status.writer_done;reader_done|=status.reader_done;
            core_done|=status.core_done;
            if(reader_pending&&reader_done&&status.reader_idle)reader_pending=false;
            if(writer_armed&&writer_done&&status.writer_idle&&!reader_pending) {
                const auto header=port.read_header();
                const uint32_t kind=protocol.accept(header);
                writer_armed=false;
                if(kind==1) {
                    require(!core_done,"D9 core ended before its graph request was served");
                    // Re-arm the one-header receiver before giving the core
                    // input: even a tiny graph may finish before the next poll.
                    port.arm_header();writer_armed=true;writer_done=false;
                    port.send_graph(config.graph_address,config.beats());
                    reader_pending=true;reader_done=false;
                }else final=true;
            }
            if(final&&!writer_armed&&!reader_pending&&core_done&&status.core_idle&&
               status.reader_idle&&status.writer_idle) {
                const Result result=protocol.result();
                // The algorithm and both DMAs are now drained. A subsequent
                // sentinel/count failure can be reported without pinning BOs.
                active=false;
                port.finish(result.requests+1);
                return result;
            }
            const double elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();
            require(elapsed<timeout_seconds,"D9 core/DMA completion deadline exceeded");
            port.idle();
        }
    }catch(const std::exception& error) {
        if(active)port.retain_active(error.what());
        throw;
    }catch(...) {
        if(active)port.retain_active("Unknown D9 exception with an active transaction");
        throw;
    }
}
}
