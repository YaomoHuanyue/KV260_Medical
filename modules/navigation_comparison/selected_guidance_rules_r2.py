"""Route-selected junction cues in physical LPS coordinates, independent of renderer."""
import numpy as np
from navigation.centerline import branch_tree
from navigation.aperture import aperture,visible_samples
from navigation.lumen import lumen_owners,selected_lumen
from scipy.spatial import cKDTree
import hashlib


def guidance_route_id(route):
    digest=hashlib.sha256()
    for key,dtype in [('points_lps_mm','<f8'),('arc_mm','<f8'),('centerline_point_ids','<i8')]:
        digest.update(np.asarray(route.get(key,[]),dtype=dtype).tobytes())
    return digest.hexdigest()


def branch_guidance(centerline, route):
    """Mark only exits actually traversed by the retained, clearance-checked route.

    A forest junction can occupy several adjacent skeleton vertices. Group those
    local decisions and place the cue inside the final selected exit, before the
    next junction. Never infer a left/right anatomical label from array axes.
    """
    c = centerline
    points = np.asarray(route.get("points_lps_mm", []), dtype=float).reshape(-1, 3)
    arc = np.asarray(route.get("arc_mm", []), dtype=float)
    ids = np.asarray(route.get("centerline_point_ids", []), dtype=int)
    result = dict(schema="kv260.navigation.guidance.v3", revision=1,route_id=guidance_route_id(route),events=[],
                  coordinates="LPS/mm", policy="retained_route_selected_exit_only")
    if len(points) < 2 or len(ids) < 2:
        return result
    if len(arc) != len(points) or not np.all(np.isfinite(points)) or np.any(np.diff(arc) <= 0):
        raise ValueError("Guidance requires a finite route with strictly increasing arc")
    degree = np.diff(c.adjacency().indptr)
    tolerance = min(c.geometry.spacing_xyz) * .3 + 1e-6
    candidates = []
    cursor = 0
    for k, point_id in enumerate(ids[:-1]):
        if degree[point_id] < 3:
            continue
        # Match both the junction and its chosen next vertex. The planner can
        # truncate its dense curve while retaining the original graph ID list.
        delta = np.linalg.norm(points[cursor:] - c.points_lps_mm[point_id], axis=1)
        j = cursor + int(np.argmin(delta))
        # The bound original Gaussian path may move within 0.28 of local
        # lumen radius. Include half the original 0.8 mm resampling interval.
        # Branch identity comes from its exact checked parent chain, never a
        # global nearest-branch guess. PL has already checked the retained curve.
        junction_tolerance=max(tolerance,.28*max(float(c.radii_mm[point_id]),.8)+.4)
        if delta[j-cursor] > junction_tolerance or j == len(points)-1:
            continue
        outgoing = np.linalg.norm(points[j:] - c.points_lps_mm[ids[k+1]], axis=1)
        outgoing_tolerance=max(tolerance,.28*max(float(c.radii_mm[ids[k+1]]),.8)+.4)
        if outgoing.min() > outgoing_tolerance:
            continue
        outgoing_index=j+int(np.argmin(outgoing))
        if outgoing_index<=j or not c.inside(points[[j,outgoing_index]]).all():
            continue
        cursor = j
        candidates.append(dict(k=k, index=j, arc=float(arc[j])))
    if not candidates:
        return result
    groups = []
    cluster_mm = max(1., min(c.geometry.spacing_xyz)*2)
    for candidate in candidates:
        if groups and candidate["arc"] - groups[-1][0]["arc"] <= cluster_mm:
            groups[-1].append(candidate)
        else:
            groups.append([candidate])
    tree = branch_tree(c)
    branches={b['id']:b for b in tree['branches']}
    point_tree=cKDTree(c.points_lps_mm)
    voxels,owners=lumen_owners(c,point_tree)
    edge_branch = {}
    for b in tree["branches"]:
        for a, z in zip(b["point_ids"][:-1], b["point_ids"][1:]):
            edge_branch[frozenset((a, z))] = b["id"]

    def at(distance):
        return np.array([np.interp(distance, arc, points[:, a]) for a in range(3)])

    for i, group in enumerate(groups):
        first, last = group[0], group[-1]
        k = last["k"]
        next_arc = groups[i+1][0]["arc"] if i+1 < len(groups) else float(arc[-1])
        radius = float(c.radii_mm[ids[k]])
        # Stay well before the next decision and before the actual reachable end.
        available = next_arc-last["arc"]
        if available < .5:
            continue
        advance = min(max(1., radius*1.25), available*.55)
        marker_arc = last["arc"]+advance
        marker = at(marker_arc)
        cue_radius = max(.15, min(float(c.sample_radius(marker[None])[0])*.65, radius))
        branch_id = edge_branch[frozenset((int(ids[k]), int(ids[k+1])))]
        selected_ids=branches[branch_id]['point_ids']
        selected_ids=[p for p in selected_ids if p not in [int(ids[k])]]
        # A graph fork can still lie in the broad junction cavity. Search into
        # the selected daughter for its narrower, visible lumen. A deep anchor
        # behind a bend is rejected instead of outlining the intervening wall.
        options=[];eye=at(max(0,first['arc']-3))
        for shift in sorted(set(min(max(1.,radius*f),available*.55) for f in (1.25,2.,3.,4.))):
            distance=last['arc']+shift;point=at(distance)
            tangent=at(min(next_arc-.1,distance+.75))-at(max(last['arc']+.1,distance-.75))
            candidate=aperture(c,point,tangent,selected_ids,point_tree)
            if candidate:
                visible=visible_samples(c,eye,candidate)
                if visible:options.append((candidate['area_mm2'],distance,point,candidate,visible))
        if options:
            _,marker_arc,marker,gate,visible=min(options,key=lambda x:x[0])
            advance=marker_arc-last['arc'];gate['incoming_visible_samples']=visible
        else:
            tangent=at(min(next_arc-.1,marker_arc+.75))-at(max(last['arc']+.1,marker_arc-.75))
            gate=aperture(c,marker,tangent,selected_ids,point_tree)
        cue_radius=max(.15,float(c.sample_radius(marker[None])[0])*.65)
        result["events"].append(dict(
            id=len(result["events"]), junction_point_ids=[int(ids[v["k"]]) for v in group],
            junction_lps_mm=c.points_lps_mm[ids[first["k"]]].tolist(),
            junction_arc_mm=first["arc"], exit_arc_mm=last["arc"],
            selected_branch_id=int(branch_id), selected_exit_point_id=int(ids[k+1]),
            marker_lps_mm=marker.tolist(), marker_arc_mm=float(marker_arc),
            marker_radius_mm=cue_radius,
            aperture=gate,
            lumen=selected_lumen(c,branch_id,branches,voxels,owners,gate),
            show_from_mm=max(0., first["arc"]-min(24., max(10., radius*3))),
            hide_after_mm=min(marker_arc-min(.8,advance*.25),next_arc-.35),
        ))
    return result
