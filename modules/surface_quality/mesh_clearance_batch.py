"""Bounded vector batches for the exact geometric wall-distance baseline.

The accepted reference and its physical distances are unchanged. KD pruning
still proves completeness; batching removes 2,070 small NumPy dispatches.
"""
from time import perf_counter
import numpy as np
from .mesh_clearance import MeshClearance, paired_triangle_distances


class BatchedMeshClearance(MeshClearance):
    def distance(self, points, *, pair_budget=32768):
        if not isinstance(pair_budget, int) or pair_budget <= 0:
            raise ValueError('Positive integer batch budget required')
        p = np.asarray(points, np.float64)
        start = perf_counter()
        groups, upper = self.candidates(p)
        counts = np.array([len(x) for x in groups], np.int64)
        if np.any(counts == 0):
            raise RuntimeError('Triangle pruning lost a valid vertex upper bound')
        best = np.full(len(p), np.inf)
        closest = np.empty_like(p)
        triangle_ids = np.full(len(p), -1, np.int64)
        query_batch = np.empty(pair_budget, np.int64)
        triangle_batch = np.empty(pair_budget, np.int64)
        filled = batches = peak = 0

        def consume(size):
            nonlocal batches, peak
            qi, ti = query_batch[:size], triangle_batch[:size]
            d, q = paired_triangle_distances(p[qi], self.triangles[ti])
            # Query IDs are ordered, including a query split across batches.
            unique, first = np.unique(qi, return_index=True)
            minima = np.minimum.reduceat(d, first)
            lengths = np.diff(np.r_[first, size])
            winner = np.minimum.reduceat(np.where(
                d == np.repeat(minima, lengths), np.arange(size), size), first)
            update = minima < best[unique]
            ids, positions = unique[update], winner[update]
            best[ids] = minima[update]
            closest[ids] = q[positions]
            triangle_ids[ids] = ti[positions]
            batches += 1
            peak = max(peak, size)

        for index, group in enumerate(groups):
            ids = np.asarray(group, np.int64)
            offset = 0
            while offset < len(ids):
                take = min(pair_budget-filled, len(ids)-offset)
                query_batch[filled:filled+take] = index
                triangle_batch[filled:filled+take] = ids[offset:offset+take]
                filled += take
                offset += take
                if filled == pair_budget:
                    consume(filled)
                    filled = 0
        if filled:
            consume(filled)
        if np.any(best > upper+np.maximum(1., upper)*1e-10):
            raise RuntimeError('Actual wall distance exceeded the vertex upper bound')
        stats = dict(backend='PS_exact_point_to_triangle_float64_bounded_batches',
            query_seconds=perf_counter()-start, preparation_seconds=self.preparation_seconds,
            queries=len(p), candidate_pairs=int(counts.sum()), all_triangles=len(self.triangles),
            pair_budget=pair_budget, batches=batches, peak_batch_pairs=peak,
            minimum_candidate_triangles=int(counts.min()) if len(counts) else 0,
            maximum_candidate_triangles=int(counts.max()) if len(counts) else 0,
            maximum_triangle_enclosing_radius_mm=self.maximum_radius,
            measures='unsigned Euclidean distance to triangle union in physical LPS mm',
            containment_certified=False, clinical_safety_certified=False, PS_Marching_Cubes_used=False)
        return best, closest, triangle_ids, stats
