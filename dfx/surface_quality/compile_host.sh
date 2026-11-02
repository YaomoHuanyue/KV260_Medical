#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build results
g++ -O3 -std=c++17 -fPIC -shared host/validator.cpp -o build/libquality_validator.so
g++ -O3 -std=c++17 -fPIC -shared -fopenmp host/reference.cpp -o build/libquality_reference.so
g++ -O3 -std=c++17 -fPIC -shared -pthread -I/usr/include/xrt host/bridge.cpp -lxrt_coreutil -o build/libquality_bridge.so
../../.venv/bin/python - <<'PY'
from pathlib import Path
import hashlib,json,platform,subprocess
root=Path.cwd();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
files=[*sorted((root/'host').glob('*')),root/'compile_host.sh']
proof=dict(status='compiled_on_ARM_no_PL_access',compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0],
           architecture=platform.machine(),source_sha256={p.relative_to(root).as_posix():sha(p) for p in files if p.is_file()},
           library_sha256={p.name:sha(p) for p in sorted((root/'build').glob('libquality_*.so'))},
           PL_accessed=False,firmware_installed=False)
path=root/'build/host_compiled_r7.json'
if path.exists():raise RuntimeError('Do not overwrite compiled host evidence')
path.write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
print(proof['status'])
PY
