"""Run new export readback and full own-CT bundle tests on ARM, without PL."""
from pathlib import Path
import json
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from modules.surface_route.bundle_r8 import sha, write_json


def main():
    closure = json.loads((ROOT/'modules/surface_route/native_UI_source_closure_r10.json').read_text())
    for name, expected in closure['files_sha256'].items():
        assert sha(ROOT/name) == expected, name
    output = ROOT/'modules/surface_route/results/active_export_ARM_r10'
    output.mkdir(exist_ok=False)
    test = ROOT/'modules/surface_route/test_export_scene_r10.py'
    scene = ROOT/'modules/surface_route/results/native_scene_ARM_r9/network_probability_high_ported_bend_1p0/scene.json'
    before = Path('/sys/firmware/devicetree/base/fpga-region/firmware-name').read_bytes()
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    try:
        subprocess.run([str(ROOT/'.venv/bin/python'), str(test), '--platform', 'ARM'], check=True, cwd=ROOT)
        subprocess.run([str(ROOT/'.venv/bin/python'), str(test), '--scene', str(scene),
                        '--destination', str(output/'export')], check=True, cwd=ROOT)
        assert Path('/sys/firmware/devicetree/base/fpga-region/firmware-name').read_bytes() == before
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
        accepted = json.loads((output/'export_acceptance.json').read_text())
        write_json(output/'acceptance.json', dict(status='ARM_active_export_kernels_and_full_own_CT_bundle_passed',
            full_export=accepted, kernel_readback_sha256=sha(test.parent/'results/export_kernels_ARM_r10.json'),
            source_closure_sha256=sha(ROOT/'modules/surface_route/native_UI_source_closure_r10.json'),
            current_boot_id=boot, PL_access=False, production_promoted=False, new_bitstream=False))
        print('ARM active export kernels and full own CT bundle passed', flush=True)
    except BaseException as error:
        write_json(output/'failure.json', dict(status='failed_active_export_candidate',
            error=str(error), traceback=traceback.format_exc()))
        raise


if __name__ == '__main__':
    main()
