import unittest
import numpy as np
from .mesh_clearance import MeshClearance
from .mesh_clearance_native import NativeMeshClearance


class NativeDistanceBaseline(unittest.TestCase):
    def test_native_reference_random_mesh_and_both_thread_counts(self):
        rng=np.random.default_rng(317)
        p=rng.normal(size=(120,3))*8;f=np.arange(120,dtype=np.uint32).reshape(-1,3)
        query=rng.normal(size=(25,3))*11
        expected=MeshClearance(p,f).distance(query)
        mesh=NativeMeshClearance(p,f)
        for threads in (1,4):
            actual=mesh.distance(query,threads=threads)
            np.testing.assert_allclose(actual[0],expected[0],rtol=0,atol=1e-12)
            np.testing.assert_allclose(actual[1],expected[1],rtol=0,atol=1e-12)
            np.testing.assert_array_equal(actual[2],expected[2])

    def test_native_degenerate_and_orphan_bounds(self):
        points=[[0,0,0],[2,0,0],[2,0,0],[.5,.5,100]];faces=np.array([[0,1,2]],np.uint32)
        mesh=NativeMeshClearance(points,faces)
        d,q,ids,_=mesh.distance([[1,2,0],[.5,.5,100]])
        np.testing.assert_allclose(d,[2,np.sqrt(10000.25)],rtol=0,atol=1e-12)
        np.testing.assert_array_equal(q,[[1,0,0],[.5,0,0]])

    def test_native_rejects_invalid_csr_before_index_access(self):
        mesh=NativeMeshClearance([[0,0,0],[2,0,0],[0,2,0]],np.array([[0,1,2]],np.uint32))
        p=np.array([[1,1,1]],np.float64);offset=np.array([0,1],np.uint64);index=np.array([1],np.uint64)
        d=np.empty(1);q=np.empty((1,3));ids=np.empty(1,np.uint64)
        code=mesh.lib.mesh_distance_native(p.ctypes.data,mesh.triangles.ctypes.data,offset.ctypes.data,index.ctypes.data,
             1,1,1,4,d.ctypes.data,q.ctypes.data,ids.ctypes.data)
        self.assertEqual(code,3)
        index[0]=0;offset[1]=2
        code=mesh.lib.mesh_distance_native(p.ctypes.data,mesh.triangles.ctypes.data,offset.ctypes.data,index.ctypes.data,
             1,1,1,4,d.ctypes.data,q.ctypes.data,ids.ctypes.data)
        self.assertEqual(code,2)


if __name__=='__main__':unittest.main()
