"""ARM XRT compilation only; never construct a Session or touch firmware."""
from pathlib import Path
import hashlib
import json
import os
import platform
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'dfx/smooth_speed/host_BRAM_r2634'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):
            h.update(b)
    return h.hexdigest()


def main():
    assert os.name=='posix' and platform.machine()=='aarch64'
    proof=json.loads((HERE/'derivation.json').read_text())
    for n,h in proof['source_sha256'].items():
        assert sha(ROOT/n)==h,n
    for row in proof['derivations']:
        text=(ROOT/row['parent']).read_text()
        for e in row['literal_edits']:
            assert text.count(e['before'])==e['occurrences']
            text=text.replace(e['before'],e['after'])
        assert text==(ROOT/row['candidate']).read_text()
    dest=HERE/'build_ARM'
    assert not dest.exists()
    dest.mkdir()
    logs=HERE/'results'
    assert not logs.exists()
    logs.mkdir()
    library=dest/'libsmooth_BRAM_r2634.so'
    command=['g++','-std=c++17','-O3','-mcpu=cortex-a53','-ffp-contract=off','-fPIC','-shared','-I/usr/include/xrt',str(HERE/'bridge.cpp'),'-lxrt_coreutil','-pthread','-o',str(library)]
    started=time.perf_counter()
    with (dest/'compile.log').open('xb') as out,(dest/'compile.stderr.log').open('xb') as err:
        result=subprocess.run(command,stdout=out,stderr=err,check=False)
    binding=dict(proof['source_sha256'])
    for p in [Path(__file__),HERE/'derivation.json']:
        binding[p.relative_to(ROOT).as_posix()]=sha(p)
    record=dict(status='actual_ARM_compact_smoothing_XRT_host_compiled_no_Session' if result.returncode==0 else 'compact_smoothing_host_compile_failure_preserved',compile_command=command,exit_code=result.returncode,elapsed_seconds=time.perf_counter()-started,
                source_sha256=binding,artifact_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in [dest/'compile.log',dest/'compile.stderr.log']+([library] if library.is_file() else [])},
                library_loaded=False,XRT_session_created=False,default_UI_or_firmware_changed=False,PL_accessed=False,production_promoted=False,whole_goal_completed=False)
    with (dest/'compile_receipt.json').open('x',encoding='utf8') as f:
        json.dump(record,f,indent=2);f.write('\n')
    assert result.returncode==0,'Compilation failed; retain outputs, no automatic retry'
    print(record['status'],flush=True)


if __name__=='__main__':
    main()
