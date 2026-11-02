#pragma once
namespace seed_stream {
inline bool dma_complete(bool reader, bool writer, bool core) noexcept {
    return reader && writer && core;
}
inline bool dma_timeout(bool reader, bool writer, bool core, double elapsed) noexcept {
    // A caller may collect long after completion. Expiry applies only while
    // at least one engine has not been observed drained.
    return !dma_complete(reader, writer, core) && elapsed > 30;
}
}
