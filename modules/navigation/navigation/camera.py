"""Renderer-independent LPS camera interface for future RM_RENDER."""
import numpy as np


def poses(points, arc, lookahead_mm=6.0):
    points = np.asarray(points,dtype=np.float64); arc = np.asarray(arc,dtype=np.float64)
    if lookahead_mm <= 0 or not np.isfinite(lookahead_mm):
        raise ValueError("lookahead_mm must be positive")
    if len(points) < 2:
        return dict(position_lps_mm=np.empty((0,3)), forward_lps=np.empty((0,3)), up_lps=np.empty((0,3)))
    ahead = np.column_stack([np.interp(np.minimum(arc[-1],arc+lookahead_mm),arc,points[:,i]) for i in range(3)])
    behind = np.column_stack([np.interp(np.maximum(0,arc-lookahead_mm),arc,points[:,i]) for i in range(3)])
    direction = ahead-points
    length = np.linalg.norm(direction,axis=1)
    direction[length<1e-9] = (points-behind)[length<1e-9]
    length = np.linalg.norm(direction,axis=1)
    if np.any(length<1e-9):
        raise ValueError("Degenerate camera route")
    forward = direction/length[:,None]; ups=[]; previous=np.array([0.,0.,1.])
    for f in forward:
        up=previous-f*np.dot(previous,f)
        if np.linalg.norm(up)<1e-6:
            axis=np.eye(3)[int(np.argmin(np.abs(f)))];up=axis-f*np.dot(axis,f)
        up/=np.linalg.norm(up)
        if np.dot(up,previous)<0:up=-up
        ups.append(up);previous=up
    return dict(position_lps_mm=points.copy(),forward_lps=forward,up_lps=np.asarray(ups))


def pose_at(camera, arc, distance_mm, yaw_degrees=0.0, pitch_degrees=0.0):
    if not len(camera["position_lps_mm"]):
        raise ValueError("No navigable camera path")
    distance=float(np.clip(distance_mm,0,arc[-1]))
    def interp(key):return np.array([np.interp(distance,arc,camera[key][:,i]) for i in range(3)])
    p=interp("position_lps_mm");f=interp("forward_lps");f/=np.linalg.norm(f)
    u=interp("up_lps");u-=f*np.dot(u,f);u/=np.linalg.norm(u);r=np.cross(f,u)
    yaw=np.deg2rad(yaw_degrees);pitch=np.deg2rad(np.clip(pitch_degrees,-85,85))
    f=(f*np.cos(yaw)+r*np.sin(yaw))*np.cos(pitch)+u*np.sin(pitch)
    u-=f*np.dot(u,f);u/=np.linalg.norm(u)
    return dict(position_lps_mm=p.tolist(),forward_lps=f.tolist(),up_lps=u.tolist(),distance_mm=distance)
