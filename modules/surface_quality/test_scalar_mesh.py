import unittest
import numpy as np
from .scalar_mesh import from_pl_words


def word(x, y, z): return np.uint64(x | y << 16 | z << 32)


class PLScalarEdges(unittest.TestCase):
    def test_crop_anisotropic_reflection_and_exact_plane(self):
        z, y, x = np.indices((8, 9, 10)); q = ((4*x - 9)*32).astype('<i2')
        # Crop xyz (1,2,3), global x crossing 2.25 -> crop midpoint x1.5.
        words = np.array([word(3, 0, 0), word(3, 2, 0), word(3, 0, 2)], np.uint64)
        d = np.array([[0,-1,0],[-1,0,0],[0,0,1]])
        p, f, stats = from_pl_words(words, q, np.array([3,2,1]), [.6,1.3,2.2], [15,-23,50], d)
        expected = (np.array([[2.25,2,3],[2.25,3,3],[2.25,2,4]]) * [.6,1.3,2.2]) @ d.T + [15,-23,50]
        # np.unique sorts integer words; compare point set independently.
        np.testing.assert_allclose(p[np.lexsort(p.T)], expected[np.lexsort(expected.T)], rtol=0, atol=3e-6)
        self.assertEqual(stats['maximum_linear_edge_zero_residual'], 0)
        self.assertFalse(stats['PS_Marching_Cubes_used'])
        np.testing.assert_allclose(p[f[0]], expected[[0,2,1]], rtol=0, atol=3e-6)

    def test_zero_endpoint_collapse_removes_only_degenerate_triangles(self):
        q = np.full((3,3,3), 32, '<i2'); q[0,0,0] = 0
        # Three distinct sign-changing edges meet at the same zero endpoint.
        collapsed = [word(1,0,0), word(0,1,0), word(0,0,1)]
        q[0,0,2] = -16
        valid = [word(3,0,0), word(3,2,0), word(3,0,2)]
        q[0,1,2] = -16; q[1,0,2] = -16
        p, f, stats = from_pl_words(np.array(collapsed+valid,np.uint64), q,
            np.zeros(3,np.int64), [1,1,1], [0,0,0], np.eye(3))
        self.assertEqual(len(f), 1)
        self.assertEqual(stats['zero_area_triangles_removed'], 1)
        np.testing.assert_allclose(p[f[0],0], 1+2/3, rtol=0, atol=1e-7)

    def test_reject_non_crossing_and_malformed_edge(self):
        q = np.ones((3,3,3), '<i2')
        good = np.array([word(1,0,0)]*3, np.uint64)
        for words, text in [(good, 'does not cross'), (np.array([word(1,1,0)]*3,np.uint64), 'single lattice'),
                            (good | np.uint64(1 << 48), 'reserved-zero'),
                            (np.array([word(7,0,0)]*3,np.uint64), 'outside')]:
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, text):
                from_pl_words(words, q, np.zeros(3, np.int64), [1,1,1], [0,0,0], np.eye(3))

    def test_PL_Lewiner_interior_fan_follows_its_scalar_edges(self):
        z,y,x=np.indices((3,3,3));q=(64*x-16).astype('<i2')
        centre=word(1,1,1)
        edges=[word(1,0,0),word(1,2,0),word(1,2,2),word(1,0,2)]
        words=np.array([v for i in range(4) for v in (edges[i],edges[(i+1)%4],centre)],np.uint64)
        p,f,stats=from_pl_words(words,q,np.zeros(3,np.int64),[1,1,1],[0,0,0],np.eye(3))
        self.assertEqual(len(f),4)
        self.assertEqual(stats['PL_Lewiner_interior_fan_vertices'],1)
        np.testing.assert_array_equal(p[:,0],np.full(len(p),.25))
        self.assertEqual(stats['maximum_interior_fan_trilinear_residual_q'],0)


if __name__ == '__main__': unittest.main()
