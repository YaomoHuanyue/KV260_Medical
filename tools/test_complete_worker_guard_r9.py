"""Test candidate worker prepare/prohibited-static guard without accessing PL."""
from pathlib import Path
import json
import subprocess
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json


def main():
    firmware=Path('/sys/firmware/devicetree/base/fpga-region/firmware-name')
    before=firmware.read_bytes()
    if before.rstrip(b'\0').startswith(b'dfx_medical.bin'):
        raise RuntimeError('This negative test requires starter-kit static; no test run')
    folder=ROOT/'modules/surface_route/results/complete_bundles_ARM_r8/network_probability_high_ported_bend_1p0'
    meta=json.loads((folder/'scene.json').read_text())
    worker=ROOT/'modules/surface_route/quality_worker_r9.py'
    argv=[str(ROOT/'.venv/bin/python'),str(worker),'--bundle',str(folder),'--revision',meta['revision']]
    start=perf_counter()
    prepared=subprocess.run(argv+['--prepare-only'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True)
    ready=json.loads(prepared.stdout)
    assert ready['event']=='prepared' and ready['PL_access'] is False
    frame=ROOT/'ui/cache/pl_scope_guard_r9.rgba';assert not frame.exists()
    rejected=subprocess.run(argv+['--frame',str(frame)],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    assert rejected.returncode!=0
    error=json.loads(rejected.stdout)
    assert error['event']=='error' and error['text']=='Manual medical static initialization required; no PL access'
    assert not frame.exists() and not Path(str(frame)+'.normal.rgba').exists()
    assert firmware.read_bytes()==before
    write_json(ROOT/'modules/surface_route/results/worker_guard_ARM_r9.json',dict(
        status='candidate_prepared_and_rejected_starter_static_before_QualitySession',
        worker_sha256=sha(worker),revision=meta['revision'],error=error['text'],
        static_firmware=before.rstrip(b'\0').decode(),total_seconds=perf_counter()-start,
        PL_access=False,frame_files_created=False,new_bitstream=False))
    print('worker prepared; starter static safely rejected before any PL access',flush=True)


if __name__=='__main__':main()
