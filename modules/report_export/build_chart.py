"""Build the existing Qt chart into a headless report helper on KV260."""
from pathlib import Path
import hashlib,json,platform,shlex,subprocess
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    assert platform.machine()=='aarch64'
    build=HERE/'build';build.mkdir(exist_ok=True)
    binary=build/'report_chart';proof=build/'build.json'
    assert not binary.exists() and not proof.exists()
    paths=[HERE/'chart.cpp',Path(__file__),ROOT/'ui/releases/feature_completion_r6/reachability_chart.hpp']
    sources={p.relative_to(ROOT).as_posix():sha(p) for p in paths}
    flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt5Widgets'],text=True))
    command=['g++','-O2','-std=c++17','-fPIC','-mcpu=cortex-a53',str(HERE/'chart.cpp'),*flags,'-o',str(binary)]
    result=subprocess.run(command,capture_output=True,text=True)
    assert sources=={p.relative_to(ROOT).as_posix():sha(p) for p in paths}
    record=dict(status='compiled_headless_native_Qt_chart' if result.returncode==0 else 'compile_failed',
        exit_code=result.returncode,command=command,source_sha256=sources,
        binary_sha256=sha(binary) if binary.exists() else None,stdout=result.stdout,stderr=result.stderr,
        no_new_Python_plotting_dependency=True,PL_accessed=False)
    proof.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    assert result.returncode==0,result.stderr
    print(record['status'],flush=True)
if __name__=='__main__':main()
