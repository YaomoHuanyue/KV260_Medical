"""ARM PS1/PS4 baselines for the complete original-field/new-route scenes.

Full 640x363, max-1023-step integer renderer. No PL, static, ZOCL or UI access.
Save exact requests/pixels so actual C9 tests can reuse the same inputs later.
"""
from pathlib import Path
import argparse
import json
import resource
import sys
from time import perf_counter
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.surface_route.scene_runtime_r8 import SceneSnapshot
from modules.surface_route.bundle_r8 import sha, digest, write_json


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bundles', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if sys.platform != 'linux' or args.output.exists():
        raise ValueError('ARM Linux and a new output directory required')
    quality = ROOT/'dfx/surface_quality'
    host = json.loads((quality/'build/host_compiled_r7.json').read_text())
    closure = {}
    for name, wanted in host['source_sha256'].items():
        path = (quality/name).resolve()
        if not path.is_relative_to(ROOT) or sha(path) != wanted:
            raise ValueError('Changed accepted reference source: '+name)
        closure[path.relative_to(ROOT).as_posix()] = wanted
    for name, wanted in host['library_sha256'].items():
        path = quality/'build'/name
        if sha(path) != wanted:
            raise ValueError('Changed compiled renderer: '+name)
        closure[path.relative_to(ROOT).as_posix()] = wanted
    sys.path.insert(0, str(quality))
    from quality_runtime import PSReference
    helper = ROOT/'dfx/surface/prepare.py'
    encoder = {'__file__': str(helper), '__name__': 'isolated_R8_physical_frame_encoder'}
    exec(compile(helper.read_text(encoding='utf-8'), str(helper), 'exec'), encoder)
    args.output.mkdir(parents=True)
    bundles = json.loads((args.bundles/'acceptance.json').read_text())
    rows = []
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    for case in bundles['cases']:
        if case['points'] < 2:
            continue
        scene = SceneSnapshot(args.bundles/case['label'], case['revision'])
        event = scene.guidance['events'][0]
        arc = float(event['junction_arc_mm'])
        cpu, old_event = None, None
        for manual in [False, True]:
            pose = scene.pose(arc, 17. if manual else 0., -6. if manual else 0.)
            request = dict(revision=scene.revision, width=640, height=363,
                sequence=1+int(manual), arc_mm=arc, camera=pose['position_lps_mm'],
                forward=pose['forward_lps'], up=pose['up_lps'])
            plan = scene.frame_plan(request)
            preparation = 0.
            if old_event != plan['branch_event']:
                start = perf_counter(); cpu = PSReference(plan['scene'])
                preparation = perf_counter()-start; old_event = plan['branch_event']
            params, view = encoder['frame_parameters'](plan['camera'], plan['forward'], plan['up'],
                scene.meta['geometry'], np.zeros(3), 640, 363, plan['sequence'])
            one, seconds1 = cpu.render(params, 1)
            samples = []
            for _ in range(2):
                start = perf_counter(); four, seconds4 = cpu.render(params, 4)
                total4 = perf_counter()-start
                np.testing.assert_array_equal(four, one)
                samples.append(dict(compute_seconds=seconds4, full_call_seconds=total4))
            hits = int(np.count_nonzero((one & 65535) != 65535))
            if hits == 0:
                raise ValueError('New-route camera sees no original scalar surface')
            label = case['label']+('_manual' if manual else '_aligned')
            folder = args.output/label; folder.mkdir()
            params.tofile(folder/'request.i32'); one.tofile(folder/'reference.u64')
            write_json(folder/'request.json', request)
            record = dict(label=label, bundle_label=case['label'], revision=scene.revision,
                bundle_scene_sha256=sha(scene.folder/'scene.json'), scene_sha256=digest(plan['scene']),
                scene_event=plan['branch_event'], route_id=scene.meta['route_id'],
                scalar_sha256=scene.meta['renderer_scalar_sha256'], request_int32=params.tolist(),
                request_sha256=sha(folder/'request.i32'), pixels_sha256=sha(folder/'reference.u64'),
                width=640, height=363, max_steps=int(params[2]), surface_hit_pixels=hits,
                target_coverage_pixels=int(np.count_nonzero(((one >> np.uint64(16)) & 255) > 0)),
                outline_pixels=int(np.count_nonzero(((one >> np.uint64(24)) & 255) > 0)),
                PS1_compute_seconds=seconds1,
                PS4_median_full_call_seconds=float(np.median([x['full_call_seconds'] for x in samples])),
                PS4_samples=samples, cold_dense_unpack_seconds=preparation,
                every_depth_normal_target_outline_word_exact_PS1_PS4=True,
                actual_manual_camera_preserved=manual, view=view,
                files_sha256={p.name: sha(p) for p in folder.iterdir()})
            write_json(folder/'report.json', record)
            rows.append(record)
            print(label, 'PS1/PS4 exact', hits, 'surface pixels', flush=True)
        del scene, cpu
    if boot != Path('/proc/sys/kernel/random/boot_id').read_text().strip():
        raise RuntimeError('Board boot changed during PS reference test')
    write_json(args.output/'acceptance.json', dict(
        status='eight_original_field_new_route_full_resolution_PS1_PS4_reference_frames_passed',
        cases=rows, boot_id=boot, source_sha256={n: sha(ROOT/n) for n in [
            'modules/surface_route/reference_frames_r8b.py', 'modules/surface_route/bundle_r8.py',
            'modules/surface_route/scene_runtime_r8.py', 'dfx/surface/prepare.py',
            'dfx/surface_quality/quality_runtime.py', 'dfx/surface_quality/prepare.py']},
        reference_build_sha256=sha(quality/'build/host_compiled_r7.json'),
        reference_bound_files=closure, bundles_acceptance_sha256=sha(args.bundles/'acceptance.json'),
        PL_access=False, new_bitstream=False, production_promoted=False,
        maximum_test_process_RSS_MiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        actual_C9_same_input_and_UI_integration_pending=True,
        performance_scope='Warm integer render calls, not UI FPS or PS/PL acceleration; dense unpack separately reported'))


if __name__ == '__main__':
    main()
