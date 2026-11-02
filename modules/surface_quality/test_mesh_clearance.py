import unittest
import numpy as np
from .mesh_clearance import paired_triangle_distances,MeshClearance


class GeometricWallDistance(unittest.TestCase):
    def test_analytic_face_edges_vertices_and_rigid_transform(self):
        t=np.array([[0,0,0],[2,0,0],[0,2,0]],float)
        points=np.array([[.5,.5,3],[1,-2,0],[3,3,0],[-1,-1,0]],float)
        wanted=np.array([[.5,.5,0],[1,0,0],[1,1,0],[0,0,0]],float)
        angle=.37;r=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
        for matrix,origin in [(np.eye(3),np.zeros(3)),(r,np.array([15,-23,50]))]:
            d,q=paired_triangle_distances(points@matrix.T+origin,np.tile(t@matrix.T+origin,(4,1,1)))
            np.testing.assert_allclose(q,wanted@matrix.T+origin,rtol=0,atol=1e-12)
            np.testing.assert_allclose(d,[3,2,np.sqrt(8),np.sqrt(2)],rtol=0,atol=1e-12)

    def test_degenerate_segments_and_orphan_vertex_upper_bound(self):
        d,q=paired_triangle_distances(np.array([[1,2,0],[1,2,3]]),
            np.array([[[0,0,0],[2,0,0],[2,0,0]],[[0,0,0],[0,0,0],[0,0,0]]]))
        np.testing.assert_allclose(d,[2,np.sqrt(14)]);np.testing.assert_allclose(q,[[1,0,0],[0,0,0]])
        mesh=MeshClearance(np.array([[0,0,0],[2,0,0],[0,2,0],[.5,.5,100]]),np.array([[0,1,2]],np.uint32))
        d,_,_,stats=mesh.distance([[.5,.5,100]])
        self.assertEqual(d[0],100);self.assertEqual(stats['candidate_pairs'],1)

    def test_pruned_mesh_matches_independent_slow_triangle_oracle(self):
        rng=np.random.default_rng(53);points=rng.normal(size=(120,3))*8
        faces=np.arange(120,dtype=np.uint32).reshape(-1,3);query=rng.normal(size=(25,3))*11
        mesh=MeshClearance(points,faces);actual,_,_,_=mesh.distance(query)
        def oracle(p,t):
            a,b,c=t;n=np.cross(b-a,c-a);norm=np.dot(n,n)
            candidates=[]
            if norm:
                projected=p-n*np.dot(p-a,n)/norm
                # Independent 2x2 Gram solve for projected barycentric coords.
                u,v=np.linalg.solve([[np.dot(b-a,b-a),np.dot(b-a,c-a)],
                    [np.dot(b-a,c-a),np.dot(c-a,c-a)]],[np.dot(projected-a,b-a),np.dot(projected-a,c-a)])
                if u>=0 and v>=0 and u+v<=1:candidates.append(np.linalg.norm(p-projected))
            for first,last in [(a,b),(b,c),(c,a)]:
                edge=last-first;f=np.clip(np.dot(p-first,edge)/np.dot(edge,edge),0,1)
                candidates.append(np.linalg.norm(p-first-f*edge))
            return min(candidates)
        expected=[min(oracle(p,t) for t in points[faces]) for p in query]
        np.testing.assert_allclose(actual,expected,rtol=0,atol=2e-12)

    def test_reject_nonfinite_query_and_bad_indices(self):
        with self.assertRaises(ValueError):MeshClearance([[0,0,0]],np.array([[0,1,2]]))
        mesh=MeshClearance([[0,0,0],[1,0,0],[0,1,0]],np.array([[0,1,2]]))
        with self.assertRaises(ValueError):mesh.distance([[0,float('nan'),0]])


if __name__=='__main__':unittest.main()
