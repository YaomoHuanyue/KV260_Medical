"""Explicit active-scene export adapter for the native Qt candidate."""
from pathlib import Path
import argparse
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    from modules.surface_route.bundle_r8 import sha
    from modules.surface_route.export_scene_r10 import export_scene
    from modules.surface_route.ui_bridge_r9 import verify_prepared
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['export'])
    p.add_argument('--active-scene', type=Path, required=True)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--result', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    p.add_argument('--minimum-candidate-volume', type=float, default=14.)
    a = p.parse_args()
    os.environ.setdefault('ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS', '2')
    if hasattr(os, 'nice'):
        os.nice(10)
    scene = verify_prepared(a.active_scene)
    if Path(scene['input']).resolve() != a.input.resolve() or Path(scene['result']).resolve() != a.result.resolve():
        raise ValueError('Selected CT/result differs from active scene')
    report = export_scene(a.active_scene, a.destination, sha(a.input), a.minimum_candidate_volume)
    print(json.dumps(dict(event='exported', path=str(a.destination.resolve()), files=len(report['files']),
        schema=report['schema'], active_revision=report['active_revision'],
        active_route_id=report['active_route_id'], renderer_scalar_sha256=report['renderer_scalar_sha256'],
        colored_surface_report=str(a.destination.resolve()/'surfaces/report.json'),
        surface_export_seconds=report['surface_export_seconds'],
        lesion_catalogue_state=report['lesion_catalogue_state'],
        minimum_candidate_volume_mm3=report['minimum_candidate_volume_mm3'],
        complete_reports=report['complete_reports'], complete_reports_scope=report['complete_reports_scope'],
        complete_report_seconds=report['complete_report_seconds']), allow_nan=False), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps(dict(event='error', text=str(error))), flush=True)
        sys.exit(1)
