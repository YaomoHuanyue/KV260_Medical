"""Unsigned Euclidean distance to actual triangle walls, not SDF amplitude.

PS KD trees prune candidates using a proven upper bound and enclosing triangle
balls. Every retained candidate uses a point-to-triangle calculation. No vertex
distance approximation, voxel EDT, case table, triangulation or PS MC is used.
This measures geometry only; it does not certify containment or clinical safety.
"""
from time import perf_counter
import numpy as np
from scipy.spatial import cKDTree


def paired_triangle_distances(points, triangles):
    p=np.asarray(points,np.float64);t=np.asarray(triangles,np.float64)
    if (p.ndim!=2 or p.shape[1]!=3 or t.shape!=(len(p),3,3) or
            not np.isfinite(p).all() or not np.isfinite(t).all()):
        raise ValueError('Finite paired points and triangles required')
    closest=[];squared=[]
    for first,last in ((0,1),(1,2),(2,0)):
        a=t[:,first];edge=t[:,last]-a;denom=np.einsum('ij,ij->i',edge,edge)
        factor=np.divide(np.einsum('ij,ij->i',p-a,edge),denom,
            out=np.zeros(len(p),np.float64),where=denom>0).clip(0,1)
        q=a+factor[:,None]*edge;closest.append(q)
        squared.append(np.einsum('ij,ij->i',p-q,p-q))
    a=t[:,0];ab=t[:,1]-a;ac=t[:,2]-a;normal=np.cross(ab,ac)
    denominator=np.einsum('ij,ij->i',normal,normal)
    v=np.divide(np.einsum('ij,ij->i',np.cross(p-a,ac),normal),denominator,
        out=np.zeros(len(p),np.float64),where=denominator>0)
    w=np.divide(np.einsum('ij,ij->i',np.cross(ab,p-a),normal),denominator,
        out=np.zeros(len(p),np.float64),where=denominator>0)
    interior=(denominator>0)&(v>=0)&(w>=0)&(v+w<=1)
    plane=a+v[:,None]*ab+w[:,None]*ac
    distance=np.einsum('ij,ij->i',p-plane,p-plane)
    distance[~interior]=np.inf;closest.append(plane);squared.append(distance)
    values=np.column_stack(squared);choice=values.argmin(axis=1);ids=np.arange(len(p))
    position=np.stack(closest,axis=1)[ids,choice]
    return np.sqrt(values[ids,choice]),position


class MeshClearance:
    def __init__(self,points,faces):
        start=perf_counter();p=np.asarray(points,np.float64);f=np.asarray(faces)
        if (p.ndim!=2 or p.shape[1]!=3 or not len(p) or f.ndim!=2 or f.shape[1]!=3 or
                not len(f) or f.dtype.kind not in 'iu' or f.min()<0 or f.max()>=len(p) or
                not np.isfinite(p).all()):
            raise ValueError('Finite nonempty triangle mesh with valid indices required')
        self.triangles=p[f].copy();self.centres=self.triangles.mean(axis=1)
        # Only referenced vertices lie on the actual wall. Orphan vertices
        # cannot provide an upper bound on distance to this triangle union.
        self.vertices=cKDTree(p[np.unique(f)])
        self.centroid_tree=cKDTree(self.centres)
        self.maximum_radius=float(np.linalg.norm(self.triangles-self.centres[:,None],axis=2).max())
        self.preparation_seconds=perf_counter()-start

    def candidates(self,points):
        p=np.asarray(points,np.float64)
        if p.ndim!=2 or p.shape[1]!=3 or not np.isfinite(p).all():
            raise ValueError('Finite physical query points required')
        upper=self.vertices.query(p,workers=1)[0]
        # If a triangle can beat the nearest referenced vertex distance U,
        # its centroid is within U+its enclosing radius <=U+global maximum R.
        radii=upper+self.maximum_radius
        radii=np.nextafter(radii,np.inf)+np.maximum(1.,radii)*1e-12
        return self.centroid_tree.query_ball_point(p,radii,workers=1),upper

    def distance(self,points):
        p=np.asarray(points,np.float64);start=perf_counter();groups,upper=self.candidates(p)
        results=np.empty(len(p),np.float64);closest=np.empty_like(p);triangle_ids=np.empty(len(p),np.int64)
        counts=np.array([len(x) for x in groups],np.int64)
        for index,group in enumerate(groups):
            if not len(group):raise RuntimeError('Triangle pruning lost a valid vertex upper bound')
            ids=np.asarray(group,np.int64)
            d,q=paired_triangle_distances(np.broadcast_to(p[index],(len(ids),3)),self.triangles[ids])
            selected=int(d.argmin());results[index]=d[selected];closest[index]=q[selected];triangle_ids[index]=ids[selected]
        if np.any(results>upper+np.maximum(1.,upper)*1e-10):
            raise RuntimeError('Actual wall distance exceeded the referenced-vertex upper bound')
        return results,closest,triangle_ids,dict(backend='PS_exact_point_to_triangle_float64_with_proven_KD_pruning',
            query_seconds=perf_counter()-start,preparation_seconds=self.preparation_seconds,
            queries=len(p),candidate_pairs=int(counts.sum()),all_triangles=len(self.triangles),
            minimum_candidate_triangles=int(counts.min()) if len(counts) else 0,
            maximum_candidate_triangles=int(counts.max()) if len(counts) else 0,
            maximum_triangle_enclosing_radius_mm=self.maximum_radius,
            measures='unsigned Euclidean distance to triangle union in physical LPS mm',
            containment_certified=False,clinical_safety_certified=False,PS_Marching_Cubes_used=False)
