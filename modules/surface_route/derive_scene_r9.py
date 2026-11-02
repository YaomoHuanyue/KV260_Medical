"""Derive the candidate reader/runtime from sealed R8 sources; never edit R8."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    'bundle_reader_r8b.py': 'bb56ad96508225f74bdec97c57ab1c4f73fc2b0306dcb8f39e703902a6b3f78a',
    'scene_runtime_r8.py': 'f16cfa883b11716f57e331b045f8f85b664a3d1f34b3df57fc7f63f92b5beadb',
    'quality_worker_r8.py': 'd043fa831929301661678b691623815538cefa33f9c4d81ad628d606efab6a2e',
}


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    folder = Path(__file__).resolve().parent
    texts = {}
    for name, expected in EXPECTED.items():
        data = (folder/name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected, name
        texts[name] = data.decode().replace('\r\n', '\n')
    reader = replace_once(texts['bundle_reader_r8b.py'],
        "if not (np.array_equal(camera[key], wanted) if key == 'position_lps_mm' else np.allclose(camera[key], wanted, rtol=0, atol=1e-12)):",
        "if (np.shape(camera[key]) != wanted.shape or not np.isfinite(camera[key]).all()\n"
        "                or not (np.array_equal(camera[key], wanted) if key == 'position_lps_mm'\n"
        "                        else np.allclose(camera[key], wanted, rtol=0, atol=1e-12))):")
    runtime = replace_once(texts['scene_runtime_r8.py'],
        'from .bundle_r8 import verify_bundle, arrays',
        'from .bundle_reader_r9 import verify_bundle\nfrom .bundle_r8 import arrays')
    runtime = replace_once(runtime,
        "or not 0 <= arc <= self.route['arc_mm'][-1]):",
        "or isinstance(arc, bool) or not -1e-4 <= arc <= self.route['arc_mm'][-1]+1e-4):")
    runtime = replace_once(runtime,
        "raise ValueError('Frame outside the accepted physical route')",
        "raise ValueError('Frame outside the accepted physical route')\n"
        "        # Qt stores progress as float32. Clamp only endpoint roundoff;\n"
        "        # this does not extend the accepted physical route.\n"
        "        arc = float(np.clip(arc, 0., self.route['arc_mm'][-1]))")
    worker = replace_once(texts['quality_worker_r8.py'],
        'from modules.surface_route.scene_runtime_r8 import SceneSnapshot',
        'from modules.surface_route.scene_runtime_r9 import SceneSnapshot\n'
        'from modules.surface_route.frame_protocol_r9 import completed_frame')
    worker = worker.replace('Candidate only. The existing HDMI UI transport has not yet been migrated.',
                            'Candidate complete-scene transport; production promotion remains gated.')
    worker = worker.replace('isolated_C6_physical_encoder_for_R8', 'isolated_C6_physical_encoder_for_R9')
    first = worker.index("            emit('frame', **view,")
    last = worker.index("    emit('stopped'", first)
    worker = worker[:first]+'''            emit('frame', **completed_frame(plan, view, frame, normal,
                 snapshot.meta['renderer_scalar_sha256'], request,
                 upload=upload, timing=timing, total_seconds=perf_counter()-begin))
'''+worker[last:]
    derived = {'bundle_reader_r9.py': reader, 'scene_runtime_r9.py': runtime, 'quality_worker_r9.py': worker}
    hashes = {}
    for name, text in derived.items():
        compile(text, str(folder/name), 'exec')
        with (folder/name).open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
        hashes[name] = hashlib.sha256((folder/name).read_bytes()).hexdigest()
    record = dict(schema='kv260.surface_route.source_derivation.v1', parents=EXPECTED,
                  outputs=hashes, PL_access=False,
                  changes=['portable axis shape and finite checks',
                           'float32 endpoint progress rounding bounded to 0.1 micrometre',
                           'completed actual-pose and paired-normal Qt protocol'])
    with (folder/'scene_derivation_r9.json').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(record, indent=2)+'\n')


if __name__ == '__main__':
    main()
