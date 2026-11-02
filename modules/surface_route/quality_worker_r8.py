"""Explicit C9 adapter consuming one complete scene, without old-route mixing.

Candidate only. The existing HDMI UI transport has not yet been migrated.
--prepare-only verifies the portable bundle without any PL/driver access.
"""
from pathlib import Path
import argparse
import json
import os
import re
import sys
from time import perf_counter
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.surface_route.scene_runtime_r8 import SceneSnapshot


def emit(event, **values):
    print(json.dumps(dict(event=event, **values), ensure_ascii=False, allow_nan=False), flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--revision', required=True)
    p.add_argument('--frame', type=Path)
    p.add_argument('--prepare-only', action='store_true')
    args = p.parse_args()
    snapshot = SceneSnapshot(args.bundle, args.revision)
    ready = dict(scene=str(snapshot.folder/'scene.json'), revision=snapshot.revision,
                 mesh_path=str(snapshot.folder/'airway.vertices'), mesh=snapshot.meta['mesh'],
                 route_path=str(snapshot.folder/'route.npz'), report=snapshot.report,
                 camera_path=str(snapshot.folder/'camera.npz'), guidance=snapshot.guidance,
                 hud=snapshot.hud, geometry=snapshot.meta['geometry'],
                 automatic_quality_changes=False, atomic_scene_activation_required=True)
    if args.prepare_only:
        emit('prepared', PL_access=False, **ready)
        return
    if args.frame is None:
        raise ValueError('--frame required for actual C9 rendering')
    frame = args.frame.resolve()
    if not (frame.is_relative_to(ROOT/'ui/cache') or
            frame.parent == Path('/run/kv260-ui-runtime') and re.fullmatch(r'pl_scope_[0-9]+\.rgba', frame.name)):
        raise ValueError('Frame outside accepted runtime directory')
    # Current boot must already have a manually loaded verified medical shell.
    # This adapter never loads static, unloads ZOCL, or enables autostart.
    firmware = Path('/sys/firmware/devicetree/base/fpga-region/firmware-name').read_bytes().rstrip(b'\0')
    if not firmware.startswith(b'dfx_medical.bin'):
        raise RuntimeError('Manual medical static initialization required; no PL access')
    sys.path.insert(0, str(ROOT/'dfx/surface_quality'))
    from quality_runtime import QualitySession
    helper = ROOT/'dfx/surface/prepare.py'
    encoder = {'__file__': str(helper), '__name__': 'isolated_C6_physical_encoder_for_R8'}
    exec(compile(helper.read_text(encoding='utf-8'), str(helper), 'exec'), encoder)
    normal = Path(str(frame)+'.normal.rgba')
    frame.parent.mkdir(parents=True, exist_ok=True)
    loaded, last_sequence, frames = None, -1, 0
    with QualitySession() as session:
        emit('ready', **ready)
        for line in sys.stdin:
            request = json.loads(line)
            if request.get('command') == 'stop':
                break
            if request.get('command') != 'frame':
                raise ValueError('Unknown frame command')
            begin = perf_counter()
            plan = snapshot.frame_plan(request)
            if plan['sequence'] <= last_sequence:
                raise ValueError('Nonincreasing frame sequence')
            last_sequence = plan['sequence']
            event = plan['branch_event']
            upload = {}
            if event != loaded:
                upload = session.load(plan['scene']); loaded = event
            params, view = encoder['frame_parameters'](plan['camera'], plan['forward'], plan['up'],
                snapshot.meta['geometry'], np.zeros(3), plan['width'], plan['height'], plan['sequence'])
            pixels, timing = session.render(params)
            for destination, values in [(frame, pixels & np.uint64(0xffffffff)),
                                         (normal, pixels >> np.uint64(32))]:
                temporary = destination.with_name(destination.name+'.new')
                values.astype('<u4').tofile(temporary); os.replace(temporary, destination)
            frames += 1
            emit('frame', **view, revision=snapshot.revision, path=str(frame), normal_frame_path=str(normal),
                 actual_camera_lps_mm=plan['camera'], actual_forward_lps=plan['forward'], actual_up_lps=plan['up'],
                 branch_event=event, hud=plan['hud'], hud_point=plan['hud_point'],
                 renderer_scalar_sha256=snapshot.meta['renderer_scalar_sha256'],
                 normal_computation='PL_C9', upload=upload, timing=timing,
                 total_seconds=perf_counter()-begin)
    emit('stopped', frames=frames, returned_to_C6=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        emit('error', text=str(error))
        raise
