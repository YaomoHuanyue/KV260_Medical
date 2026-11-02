"""Retain PL fan cycles when exact scalar-zero vertices coincide.

This changes indexing only. Every retained triangle keeps its original ordered
coordinates. No new triangle, spatial offset, hole filling or field edit exists.
Coincident geometric contact remains explicit; no self-intersection guarantee.
"""
import numpy as np


def _fan_cycles(raw_faces, centre, merged, valid):
    face_ids = np.flatnonzero(np.any(raw_faces == centre, axis=1))
    successor = {}
    for fid in face_ids:
        t = raw_faces[fid]
        hit = np.flatnonzero(t == centre)
        if len(hit) != 1:
            raise ValueError('A PL interior fan triangle must contain its centre once')
        t = np.roll(t, -int(hit[0]))
        a, b = map(int, t[1:])
        if a in successor or a == b:
            raise ValueError('PL fan boundary is not a directed simple cycle')
        successor[a] = (b, int(fid))
    if set(successor) != {b for b, _ in successor.values()}:
        raise ValueError('Open original PL interior fan refused')
    remaining, cycles = set(successor), []
    while remaining:
        at = first = min(remaining)
        order = []
        while at in remaining:
            remaining.remove(at)
            to, fid = successor[at]
            order.append((int(merged[at]), int(merged[to]), fid))
            at = to
        if at != first:
            raise ValueError('PL fan boundary intersects another cycle')
        walk, stack_edges = [], []
        for a, b, fid in order:
            if not valid[fid]:
                if a != b:
                    raise ValueError('Collinear noncollapsed PL fan triangle requires separate review')
                continue
            if a == b or a == int(merged[centre]) or b == int(merged[centre]):
                raise ValueError('Unexpected retained degenerate PL fan triangle')
            if not walk:
                walk = [a]
            if walk[-1] != a:
                raise ValueError('Removing scalar-zero fan edges left an open chain')
            if b in walk:
                j = walk.index(b)
                loop = stack_edges[j:]+[fid]
                if len(loop) < 3:
                    raise ValueError('Collapsed PL fan has fewer than three nonzero triangles')
                cycles.append(loop)
                walk, stack_edges = walk[:j+1], stack_edges[:j]
            else:
                stack_edges.append(fid)
                walk.append(b)
        if stack_edges:
            raise ValueError('Scalar-zero fan cycle did not close')
    kept = sorted(int(f) for f in face_ids if valid[f])
    if sorted(f for group in cycles for f in group) != kept:
        raise ValueError('PL fan cycle decomposition did not preserve every triangle')
    return cycles


from .indexing_r17.native import split_vertex_links as _split_vertex_links


def retain_PL_fan_indexing(points, faces, raw_faces, merged, centres, valid):
    before = points[faces].copy()
    p, f = [q.copy() for q in points], faces.copy()
    row = np.full(len(raw_faces), -1, np.int64)
    row[valid] = np.arange(int(valid.sum()))
    fan_splits, copies = 0, 0
    for centre in centres:
        cycles = _fan_cycles(raw_faces, int(centre), merged, valid)
        if len(cycles) <= 1:
            continue
        fan_splits += 1
        hub = int(merged[centre])
        for cycle in cycles[1:]:
            replacement = len(p)
            p.append(points[hub].copy())
            copies += 1
            for original_id in cycle:
                fid = int(row[original_id])
                if np.count_nonzero(f[fid] == hub) != 1:
                    raise ValueError('PL fan provenance disagrees with retained scalar triangle')
                f[fid, f[fid] == hub] = replacement
    p, f, link_splits, link_copies = _split_vertex_links(np.asarray(p), f)
    np.testing.assert_array_equal(p[f], before)
    # A second independent pass must find no remaining disconnected links.
    pp, ff, remaining, added = _split_vertex_links(p, f)
    assert remaining == added == 0
    np.testing.assert_array_equal(pp, p)
    np.testing.assert_array_equal(ff, f)
    return p, f, dict(rule='original_PL_directed_fan_cycles_and_connected_vertex_links',
        split_PL_fans=fan_splits, coincident_fan_centres_added=copies,
        split_disconnected_vertex_links=link_splits, coincident_sheet_vertices_added=link_copies,
        every_retained_ordered_triangle_coordinate_exact=True,
        all_retained_vertex_links_cycles_or_open_fans=True,
        scalar_values_changed=False, triangles_added_or_removed=False,
        geometry_self_contact_removed=False, geometric_self_intersection_certified=False)
