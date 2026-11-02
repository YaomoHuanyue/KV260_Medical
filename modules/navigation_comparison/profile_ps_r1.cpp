// Optimized CPU baseline for the supplied 26-neighbor weighted Dijkstra rule.
// Geometry-derived edge lengths are shared inputs, not recalculated or rounded.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <functional>
#include <limits>
#include <queue>
#include <utility>
#include <vector>

extern "C" int profile_ps(uint32_t nodes, uint32_t edges,
    const uint32_t* rows, const uint32_t* neighbors, const double* lengths,
    const double* radii, uint32_t root, uint32_t queries,
    const double* diameters, double margin, double radius_weight, uint32_t threads,
    double* distances, int32_t* parents) {
    if (!nodes || root >= nodes || !queries || queries > 64 || !threads || threads > 4
        || !std::isfinite(margin) || margin < 0 || !std::isfinite(radius_weight) || radius_weight < 0
        || rows[0] != 0 || rows[nodes] != edges) return 1;
    for (uint32_t i=0; i<nodes; ++i) {
        if (!std::isfinite(radii[i]) || radii[i] < 0 || rows[i] > rows[i+1]) return 2;
    }
    for (uint32_t i=0; i<edges; ++i) {
        if (neighbors[i] >= nodes || !std::isfinite(lengths[i]) || lengths[i] <= 0) return 3;
    }
    for (uint32_t i=0; i<queries; ++i) {
        if (!std::isfinite(diameters[i]) || diameters[i] <= 0) return 4;
    }
    #pragma omp parallel for num_threads(threads) schedule(static)
    for (int query=0; query<int(queries); ++query) {
        double* dist=distances+size_t(query)*nodes;
        int32_t* parent=parents+size_t(query)*nodes;
        std::fill(dist,dist+nodes,std::numeric_limits<double>::infinity());
        std::fill(parent,parent+nodes,-1);
        const double scope_radius=std::max(diameters[query]*.5,.1);
        const double required=scope_radius+margin;
        using Entry=std::pair<double,uint32_t>;
        std::priority_queue<Entry,std::vector<Entry>,std::greater<Entry>> heap;
        dist[root]=0.; heap.emplace(0.,root);
        while (!heap.empty()) {
            const Entry entry=heap.top(); heap.pop();
            const double d=entry.first; const uint32_t u=entry.second;
            if (d != dist[u]) continue;
            for (uint32_t j=rows[u]; j<rows[u+1]; ++j) {
                const uint32_t v=neighbors[j];
                const double r=std::max(std::min(radii[u],radii[v]),.2);
                if (r+1e-9 < required) continue;
                const double ratio=scope_radius/r;
                const double excess=std::max(0.,ratio-.65);
                const double penalty=excess*excess;
                const double factor=1.+radius_weight*penalty;
                const double nd=d+lengths[j]*factor;
                if (nd+1e-9 < dist[v]) {
                    dist[v]=nd; parent[v]=int32_t(u); heap.emplace(nd,v);
                }
            }
        }
    }
    return 0;
}
