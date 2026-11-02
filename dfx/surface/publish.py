"""Publish the independently verified SDF candidate against the frozen shell."""
from pathlib import Path
import hashlib, json, shutil

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / 'build'
RELEASE = ROOT / 'release'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def logtext(path):
    data = path.read_bytes()
    return data.decode('utf-16' if data[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig')

def main():
    marker = BUILD / 'OFFLINE_COMPLETE.txt'
    assert marker.exists(), 'No successful routed build'
    for name in ('hls/scope.cpp', 'hls/scope.hpp', 'hls/testbench.cpp', 'build_rm.tcl', 'implement.tcl', 'generate_wrapper.py'):
        assert (ROOT / name).stat().st_mtime <= marker.stat().st_mtime, 'Source newer than build: ' + name
    assert sha(ROOT.parent/'medical/build/static_routed.dcp') == '285f3d4a50af45cbea7f503f1f32789b0d84b55214163750a301267e2e72fcb9'
    assert 'CSim done with 0 errors.' in logtext(BUILD/'csim.log')
    assert 'All loop constraints were satisfied.' in logtext(BUILD/'hls.log'), 'Requested pipeline intervals were not achieved'
    for name in ('cosim.log', 'cosim_random.log'):
        assert 'C/RTL co-simulation finished: PASS' in logtext(BUILD/name), name
    assert 'ERROR:' not in logtext(BUILD/'pr_verify.log')
    RELEASE.mkdir(exist_ok=True)
    for source, target in [('config_scope_pblock_rp_partial.bin', 'medical_surface_partial.bin')] + [(x, x) for x in ('timing.rpt', 'utilization.rpt', 'drc.rpt', 'pr_verify.log', 'cosim.log', 'cosim_random.log')]:
        shutil.copy2(BUILD/source, RELEASE/target)
    files = {}
    for folder in ('hls', 'host', 'release', 'tests'):
        for path in (ROOT/folder).rglob('*'):
            if path.is_file() and path.name != 'manifest.json' and path.suffix not in ('.so', '.pyc') and '__pycache__' not in path.parts and not path.name.endswith('.new'):
                files[path.relative_to(ROOT).as_posix()] = sha(path)
    for name in ('prepare.py', 'runtime.py', 'worker.py', 'test_board.py', 'install.sh', 'build.ps1', 'build_rm.tcl', 'implement.tcl', 'generate_wrapper.py', 'publish.py'):
        files[name] = sha(ROOT/name)
    manifest = dict(schema='kv260.surface.dfx.v1', offline_verified=True, board_verified=False,
                    identity=198, clock_hz=100000000, field='signed_int16_q5_sparse_original_grid',
                    normal_computation='PL',normal_filter='depth_aware_3x3',pixel_bits=64,scene_magic='0x53554632',
                    static_manifest_sha256=sha(ROOT.parent/'medical/release/manifest.json'),
                    medical_extensions_sha256=sha(ROOT.parent/'medical/release/extensions.json'), files=files)
    (RELEASE/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    print('SDF candidate published; actual board verification is still required')

if __name__ == '__main__': main()
