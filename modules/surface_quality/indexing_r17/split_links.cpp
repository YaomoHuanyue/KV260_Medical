// Index existing PL triangles only: no case table, triangulation or geometry edit.
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <limits>
#include <new>
#include <stdexcept>
#include <utility>
#include <vector>

#ifdef _WIN32
#define EXPORT extern "C" __declspec(dllexport)
#else
#define EXPORT extern "C"
#endif

using U = uint64_t;
static U root(std::vector<U>& parent, U at) {
    while (parent[at] != at) {
        parent[at] = parent[parent[at]];
        at = parent[at];
    }
    return at;
}

EXPORT int split_vertex_links_r17(const double* points, U nv,
        const U* faces, U nf, double* out_points, U capacity,
        U* out_faces, U* stats, char* error, U error_capacity) {
    auto message = [&](const char* text) {
        if (error && error_capacity) {
            const auto n = std::min<U>(std::strlen(text), error_capacity - 1);
            std::memcpy(error, text, n); error[n] = 0;
        }
    };
    try {
        if (!points || !faces || !out_points || !out_faces || !stats ||
            !nv || !nf || capacity < nv ||
            nf > std::numeric_limits<size_t>::max() / (3 * sizeof(U)) ||
            capacity > std::numeric_limits<size_t>::max() / (3 * sizeof(double)))
            throw std::invalid_argument("Invalid native vertex-link buffer dimensions");
        std::vector<U> offsets(nv + 1, 0);
        for (U i = 0; i < nf * 3; ++i) {
            if (faces[i] >= nv) throw std::invalid_argument("Face index outside vertex array");
            ++offsets[faces[i] + 1];
        }
        for (U v = 0; v < nv; ++v) offsets[v + 1] += offsets[v];
        std::vector<U> cursor(offsets), ids(nf * 3);
        // This is the stable flattened-face order used by the Python oracle.
        for (U i = 0; i < nf * 3; ++i) ids[cursor[faces[i]]++] = i / 3;
        std::memcpy(out_faces, faces, nf * 3 * sizeof(U));
        std::memcpy(out_points, points, nv * 3 * sizeof(double));
        U used = nv, splits = 0, copies = 0;
        std::vector<std::pair<U,U>> edges;
        std::vector<U> parent, group_of, root_group, ends, replacement;
        const U absent = std::numeric_limits<U>::max();
        for (U vertex = 0; vertex < nv; ++vertex) {
            const U lo = offsets[vertex], degree = offsets[vertex + 1] - lo;
            if (!degree) continue;
            edges.clear(); edges.reserve(degree * 2);
            parent.resize(degree);
            for (U local = 0; local < degree; ++local) {
                U other[3], count = 0;
                const U fid = ids[lo + local];
                for (U j = 0; j < 3; ++j) {
                    const U n = out_faces[3 * fid + j];
                    if (n != vertex) other[count++] = n;
                }
                if (count != 2 || other[0] == other[1])
                    throw std::invalid_argument("Degenerate indexed triangle in vertex-link review");
                edges.emplace_back(other[0], local);
                edges.emplace_back(other[1], local);
                parent[local] = local;
            }
            std::sort(edges.begin(), edges.end());
            for (size_t at = 0; at < edges.size();) {
                size_t end = at + 1;
                while (end < edges.size() && edges[end].first == edges[at].first) ++end;
                if (end - at > 2)
                    throw std::invalid_argument("Vertex link still branches across a nonmanifold edge");
                if (end - at == 2) {
                    U a = root(parent, edges[at].second), b = root(parent, edges[at + 1].second);
                    parent[b] = a;
                }
                at = end;
            }
            root_group.assign(degree, absent); group_of.resize(degree);
            U groups = 0;
            // Components ordered by first local face, regardless of union root.
            for (U local = 0; local < degree; ++local) {
                const U r = root(parent, local);
                if (root_group[r] == absent) root_group[r] = groups++;
                group_of[local] = root_group[r];
            }
            ends.assign(groups, 0);
            for (size_t at = 0; at < edges.size();) {
                size_t end = at + 1;
                while (end < edges.size() && edges[end].first == edges[at].first) ++end;
                if (end - at == 1) ++ends[group_of[edges[at].second]];
                at = end;
            }
            for (U count : ends)
                if (count != 0 && count != 2)
                    throw std::invalid_argument("Vertex-link component is neither a cycle nor an open fan");
            if (groups > 1) {
                ++splits; replacement.assign(groups, vertex);
                for (U g = 1; g < groups; ++g) {
                    if (used >= capacity) throw std::invalid_argument("Native vertex-link output capacity exceeded");
                    replacement[g] = used++;
                    std::memcpy(out_points + replacement[g] * 3, points + vertex * 3, 3 * sizeof(double));
                    ++copies;
                }
                for (U local = 0; local < degree; ++local) {
                    const U g = group_of[local];
                    if (!g) continue;
                    const U fid = ids[lo + local];
                    for (U j = 0; j < 3; ++j)
                        if (out_faces[fid * 3 + j] == vertex) out_faces[fid * 3 + j] = replacement[g];
                }
            }
        }
        stats[0] = used; stats[1] = splits; stats[2] = copies;
        message(""); return 0;
    } catch (const std::invalid_argument& e) {
        message(e.what()); return 1;
    } catch (const std::exception& e) {
        message(e.what()); return 2;
    } catch (...) {
        message("Unknown native vertex-link error"); return 2;
    }
}
