import unittest
import numpy as np
from .mesh_clearance import MeshClearance
from .mesh_clearance_batch import BatchedMeshClearance


class BoundedBatchDistance(unittest.TestCase):
    def test_exact_reference_across_small_and_large_batch_boundaries(self):
        rng = np.random.default_rng(97)
        vertices = rng.normal(size=(120, 3))*8
        faces = np.arange(120, dtype=np.uint32).reshape(-1, 3)
        query = rng.normal(size=(25, 3))*11
        reference = MeshClearance(vertices, faces).distance(query)
        batch = BatchedMeshClearance(vertices, faces)
        for budget in (1, 7, 17, 32768):
            actual = batch.distance(query, pair_budget=budget)
            for x, y in zip(actual[:3], reference[:3]):
                np.testing.assert_array_equal(x, y)
            self.assertLessEqual(actual[3]['peak_batch_pairs'], budget)

    def test_equal_triangles_keep_original_first_tie_across_batches(self):
        vertices = np.array([[0, 0, 0], [2, 0, 0], [0, 2, 0]], float)
        faces = np.tile([[0, 1, 2]], (20, 1)).astype(np.uint32)
        p = [[.5, .5, 3], [1, -2, 0]]
        ref = MeshClearance(vertices, faces).distance(p)
        got = BatchedMeshClearance(vertices, faces).distance(p, pair_budget=7)
        for x, y in zip(got[:3], ref[:3]):
            np.testing.assert_array_equal(x, y)
        self.assertEqual(got[3]['candidate_pairs'], 40)

    def test_reject_invalid_budget_and_query(self):
        mesh = BatchedMeshClearance([[0, 0, 0], [2, 0, 0], [0, 2, 0]],
                                   np.array([[0, 1, 2]], np.uint32))
        for budget in (0, -1, .5):
            with self.assertRaises(ValueError):
                mesh.distance([[.5, .5, 3]], pair_budget=budget)
        with self.assertRaises(ValueError):
            mesh.distance([[float('inf'), 0, 0]])


if __name__ == '__main__':
    unittest.main()
