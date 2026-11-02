"""Adversarial coincident fans, proper vertex links and refusal tests."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import unittest
import numpy as np
from .scalar_mesh_indexing_r7 import retain_PL_fan_indexing, _split_vertex_links


class Indexing(unittest.TestCase):
    def fan(self):
        p = np.array([[0,0,1],[0,0,0],[1,0,0],[0,1,0],[-1,0,0],[0,-1,0]], float)
        raw = np.array([[0,1,2],[0,2,3],[0,3,4],[0,4,5],[0,5,6],[0,6,1]], np.uint32)
        merged = np.array([0,1,2,3,1,4,5])
        return p, merged[raw].astype(np.uint32), raw, merged

    def test_pinched_fan_keeps_every_triangle_and_separates_sheet_links(self):
        p, f, raw, merged = self.fan()
        q, g, report = retain_PL_fan_indexing(p, f, raw, merged, [0], np.ones(6, bool))
        np.testing.assert_array_equal(q[g], p[f])
        self.assertEqual(report['split_PL_fans'], 1)
        self.assertEqual(report['coincident_fan_centres_added'], 1)
        self.assertEqual(report['split_disconnected_vertex_links'], 1)
        self.assertEqual(report['coincident_sheet_vertices_added'], 1)
        edges = np.sort(np.concatenate((g[:,[0,1]],g[:,[1,2]],g[:,[2,0]])), axis=1)
        self.assertLessEqual(int(np.unique(edges, axis=0, return_counts=True)[1].max()), 2)
        self.assertFalse(report['geometry_self_contact_removed'])

    def test_ordinary_closed_tetrahedron_is_unchanged(self):
        p = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], float)
        f = np.array([[0,2,1],[0,1,3],[0,3,2],[1,2,3]], np.uint32)
        q, g, count, copies = _split_vertex_links(p, f)
        np.testing.assert_array_equal(q, p)
        np.testing.assert_array_equal(g, f)
        self.assertEqual((count, copies), (0,0))

    def test_disjoint_closed_sheets_touching_at_one_vertex_stay_geometrically_exact(self):
        p = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1],[-1,0,0],[0,-1,0],[0,0,-1]], float)
        f = np.array([[0,2,1],[0,1,3],[0,3,2],[1,2,3],
                      [0,4,5],[0,6,4],[0,5,6],[4,6,5]], np.uint32)
        q, g, count, copies = _split_vertex_links(p, f)
        np.testing.assert_array_equal(q[g], p[f])
        self.assertEqual((count, copies), (1,1))

    def test_missing_original_fan_triangle_is_refused(self):
        p, f, raw, merged = self.fan()
        with self.assertRaisesRegex(ValueError, 'Open original PL interior fan'):
            retain_PL_fan_indexing(p, f[:-1], raw[:-1], merged, [0], np.ones(5, bool))

    def test_noncollapsed_collinear_removal_is_not_silently_repaired(self):
        p, f, raw, merged = self.fan()
        valid = np.ones(6, bool)
        valid[0] = False
        with self.assertRaisesRegex(ValueError, 'Collinear noncollapsed'):
            retain_PL_fan_indexing(p, f[valid], raw, merged, [0], valid)

    def test_unexplained_nonmanifold_edge_without_PL_fan_is_refused(self):
        p, f, raw, merged = self.fan()
        with self.assertRaisesRegex(ValueError, 'still branches'):
            retain_PL_fan_indexing(p, f, raw, merged, [], np.ones(6, bool))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--proof', type=Path, required=True)
    args = parser.parse_args()
    assert not args.proof.exists()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Indexing)
    names = [t.id() for t in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    assert result.wasSuccessful()
    root = Path(__file__).resolve().parents[2]
    proof = dict(status='six_coincident_fan_vertex_link_and_negative_indexing_tests_passed',
        platform=sys.platform, tests=names,
        source_sha256={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in (
            'modules/surface_quality/test_scalar_mesh_indexing_r7.py',
            'modules/surface_quality/scalar_mesh_indexing_r7.py')}, PL_access=False)
    args.proof.parent.mkdir(parents=True, exist_ok=True)
    args.proof.write_text(json.dumps(proof, indent=2)+'\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
