"""Check that portability tolerance accepts arithmetic roundoff, not wrong poses."""
from pathlib import Path
import argparse
import json
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.surface_route.bundle_r8 import arrays, sha, write_json
from modules.surface_route.bundle_reader_r8b import validate_geometry, verify_bundle
from modules.surface_route.guidance_r5 import ScalarField
from dfx.surface_quality.prepare import unpack_scene


def main():
    p = argparse.ArgumentParser(); p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    meta = verify_bundle(a.bundle)
    q, _ = unpack_scene((a.bundle/'scene_-1.bin').read_bytes())
    field = ScalarField(q, meta['geometry'], meta['bits'])
    mesh, route, camera = [arrays(a.bundle/n) for n in ['mesh.npz', 'route.npz', 'camera.npz']]
    report, guidance = [json.loads((a.bundle/n).read_text()) for n in ['route.json', 'guidance.json']]
    def check(candidate):
        validate_geometry(field, mesh['points'], mesh['faces'], meta['identity']['mesh_proof'],
                          route, report, candidate, guidance)
    cases = []
    tiny = {k: v.copy() for k, v in camera.items()}
    tiny['up_lps'][0, 0] = np.nextafter(tiny['up_lps'][0, 0], np.inf)
    check(tiny); cases.append(dict(name='single_ULP_normalized_axis_roundoff_accepted', passed=True))
    for name, key, change in [('changed_position_even_one_ULP', 'position_lps_mm', 'ulp'),
                               ('wrong_direction', 'forward_lps', 'large'),
                               ('nonfinite_up_direction', 'up_lps', 'nan')]:
        candidate = {k: v.copy() for k, v in camera.items()}
        value = candidate[key][0, 0]
        candidate[key][0, 0] = np.nextafter(value, np.inf) if change == 'ulp' else (
            value+1e-7 if change == 'large' else np.nan)
        try:
            check(candidate)
        except ValueError as error:
            cases.append(dict(name=name, passed=True, reason=str(error)))
        else:
            raise AssertionError('Portable reader accepted '+name)
    write_json(a.output, dict(status='portable_reader_roundoff_and_wrong_pose_rejection_passed',
        cases=cases, source_sha256={n: sha(ROOT/n) for n in [
            'modules/surface_route/test_portable_reader_r8b.py',
            'modules/surface_route/bundle_reader_r8b.py', 'modules/surface_route/bundle_r8.py']},
        bundle_sha256=sha(a.bundle/'scene.json'), PL_access=False))
    print('4 portable-reader checks passed')


if __name__ == '__main__':
    main()
