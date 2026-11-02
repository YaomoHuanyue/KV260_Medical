"""Compare all portable Windows/ARM bundle contents, not only metadata."""
from pathlib import Path
import argparse
import json
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.surface_route.bundle_r8 import arrays, sha, write_json
from modules.surface_route.bundle_reader_r8b import verify_bundle


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--windows', type=Path, required=True)
    p.add_argument('--arm', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    results = []
    windows = json.loads((a.windows/'acceptance.json').read_text())
    arm = json.loads((a.arm/'acceptance.json').read_text())
    assert {c['label'] for c in windows['cases']} == {c['label'] for c in arm['cases']}
    for case in windows['cases']:
        label = case['label']; w, b = a.windows/label, a.arm/label
        mw, mb = verify_bundle(w), verify_bundle(b)
        assert mw['geometry'] == mb['geometry'] and mw['bits'] == mb['bits']
        assert mw['renderer_scalar_sha256'] == mb['renderer_scalar_sha256']
        assert set(mw['scenes']) == set(mb['scenes'])
        for event in mw['scenes']:
            assert (w/mw['scenes'][event]['file']).read_bytes() == (b/mb['scenes'][event]['file']).read_bytes()
        wm, bm = arrays(w/'mesh.npz'), arrays(b/'mesh.npz')
        for key in wm:
            np.testing.assert_array_equal(wm[key], bm[key])
        maximum = 0.
        for filename in ('route.npz', 'camera.npz'):
            x, y = arrays(w/filename), arrays(b/filename)
            assert set(x) == set(y)
            for key in x:
                assert x[key].shape == y[key].shape
                np.testing.assert_array_equal(np.isfinite(x[key]), np.isfinite(y[key]))
                np.testing.assert_allclose(x[key], y[key], rtol=0, atol=1e-10)
                valid = np.isfinite(x[key])
                if valid.any():
                    maximum = max(maximum, float(np.max(np.abs(x[key][valid]-y[key][valid]))))
        x, y = [np.fromfile(f/'airway.vertices', '<f4').reshape(-1, 6) for f in (w, b)]
        np.testing.assert_array_equal(x[:, :3], y[:, :3])
        np.testing.assert_allclose(x[:, 3:], y[:, 3:], rtol=0, atol=1e-6)
        results.append(dict(label=label, scene_packets_scalar_targets_normals_byte_exact=True,
            mesh_triangle_coordinates_and_indices_exact=True, route_camera_maximum_difference=maximum,
            overview_normal_maximum_difference=float(np.max(np.abs(x[:, 3:]-y[:, 3:]))),
            windows_revision=mw['revision'], arm_revision=mb['revision']))
        print(label, 'cross-platform bundle passed', flush=True)
    write_json(a.output, dict(status='eight_complete_original_surface_bundles_cross_platform_passed',
        cases=results, input_sha256={str(f): sha(f) for f in [a.windows/'acceptance.json', a.arm/'acceptance.json']},
        source_sha256={n: sha(ROOT/n) for n in ['modules/surface_route/compare_bundles_r8b.py',
                                               'modules/surface_route/bundle_r8.py', 'modules/surface_route/bundle_reader_r8b.py']},
        PL_access=False, production_promoted=False))


if __name__ == '__main__':
    main()
