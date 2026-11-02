"""Durable ARM source-bound original-node surface comparison supervisor."""
from pathlib import Path
import fcntl,json,subprocess,sys,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json
from modules.surface_route.own_CT_comparison_r11 import verify_sources


def main():
    out=ROOT/'modules/surface_route/results/comparison_trial_ARM_r11'
    out.mkdir(exist_ok=False)
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    source=verify_sources()
    try:
        for p in Path('/proc').iterdir():
            try:
                if p.name.isdigit() and (p/'comm').read_text().strip()=='medical_ui':
                    raise RuntimeError('Medical UI active; test refused')
            except FileNotFoundError:pass
        assert Path('/sys/firmware/devicetree/base/fpga-region/firmware-name').read_bytes().rstrip(b'\0')==b'dfx_medical.bin'
        with Path('/tmp/kv260-ct-pl.lock').open('rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            fcntl.flock(lock,fcntl.LOCK_UN)
        for script,args in [
            ('modules/surface_route/test_comparison_r11.py',['--output','modules/surface_route/results/comparison_kernels_ARM_r11.json']),
            ('modules/surface_route/own_CT_comparison_r11.py',['--output','modules/surface_route/results/comparison_own_CT_ARM_r11','--actual-PL','--repeats','3'])]:
            print('RUN',script,flush=True)
            subprocess.run([str(ROOT/'.venv/bin/python'),'-X','utf8',str(ROOT/script),*args],cwd=ROOT,check=True)
        assert boot==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        evidence=['modules/surface_route/results/comparison_kernels_ARM_r11.json',
                  'modules/surface_route/results/comparison_own_CT_ARM_r11/acceptance.json']
        write_json(out/'acceptance.json',dict(status='ARM_kernels_and_four_own_CT_actual_PL_full_comparisons_passed',
            evidence_sha256={p:sha(ROOT/p) for p in evidence},source_closure_sha256=source,
            supervisor_sha256=sha(Path(__file__)),boot_id=boot,production_promoted=False))
    except BaseException as error:
        write_json(out/'failure.json',dict(status='failed_comparison_trial',error=str(error),traceback=traceback.format_exc()))
        raise


if __name__=='__main__':main()
