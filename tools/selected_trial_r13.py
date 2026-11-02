"""Durable checked preparation/C4/C9 trial; no static reload or default mutation."""
from pathlib import Path
import fcntl,json,subprocess,sys,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json
from modules.surface_route.surface_actions_r13 import verify_sources


def main():
    source=verify_sources();output=ROOT/'modules/surface_route/results/selected_trial_ARM_r13';output.mkdir(exist_ok=False)
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    checkpoint=json.loads((ROOT/'modules/surface_route/work_checkpoint_r12.json').read_text())
    assert boot==checkpoint['current_board_state']['boot_id']
    for name,h in checkpoint['current_board_state']['preserved_defaults_sha256'].items():assert sha(ROOT/name)==h,name
    assert Path('/sys/firmware/devicetree/base/fpga-region/firmware-name').read_bytes().rstrip(b'\0')==b'dfx_medical.bin'
    with Path('/tmp/kv260-ct-pl.lock').open('rb') as lock:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        for name,args in [
            ('test_selected_r13.py',['--output','modules/surface_route/results/selected_kernels_ARM_r13.json']),
            ('own_selected_trial_r13.py',['--output','modules/surface_route/results/selected_own_CT_ARM_r13']),
            ('actual_selected_C9_r13.py',[])]:
            print('RUN',name,flush=True)
            subprocess.run([str(ROOT/'.venv/bin/python'),'-X','utf8',str(ROOT/'modules/surface_route'/name),*args],cwd=ROOT,check=True)
        assert boot==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        evidence=['modules/surface_route/results/selected_kernels_ARM_r13.json',
            'modules/surface_route/results/selected_own_CT_ARM_r13/acceptance.json',
            'modules/surface_route/results/selected_actual_PL_ARM_r13/acceptance.json']
        write_json(output/'acceptance.json',dict(status='ARM_selected_surface_kernels_four_fields_and_actual_C4_C9_passed',
            source_closure_sha256=source,supervisor_sha256=sha(Path(__file__)),boot_id=boot,
            evidence_sha256={n:sha(ROOT/n) for n in evidence},production_promoted=False))
    except BaseException as error:
        write_json(output/'failure.json',dict(error=str(error),traceback=traceback.format_exc()));raise


if __name__=='__main__':main()
