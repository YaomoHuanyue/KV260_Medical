#pragma once
#include <cstdint>

// Called only after both missing parts of [lo,hi] have been loaded. Coordinates
// are immutable during an average pass or an orientation check. Retain the
// contiguous union, clipped so modulo-window writes cannot alias a retained
// index. A disjoint request starts a new interval; its gap was never loaded.
static inline void retain_cache_window(uint32_t lo, uint32_t hi, uint32_t window,
                                      bool& valid, uint32_t& cache_lo,
                                      uint32_t& cache_hi) {
#pragma HLS inline
    if (valid && lo <= cache_hi && hi >= cache_lo) {
        const uint32_t union_lo = lo < cache_lo ? lo : cache_lo;
        const uint32_t union_hi = hi > cache_hi ? hi : cache_hi;
        const uint32_t floor = hi >= window - 1 ? hi - (window - 1) : 0;
        cache_lo = union_lo > floor ? union_lo : floor;
        const uint32_t ceiling = cache_lo + window - 1;
        cache_hi = union_hi < ceiling ? union_hi : ceiling;
    } else {
        cache_lo = lo;
        cache_hi = hi;
    }
    valid = true;
}
