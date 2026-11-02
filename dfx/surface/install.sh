#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ $EUID -eq 0 ]] || { echo 'Run with sudo bash dfx/surface/install.sh'; exit 1; }
exec 9</tmp/kv260-ct-pl.lock
flock -n 9 || { echo 'PL is in use; finish the current task first.'; exit 1; }
python3 - <<'PY'
from pathlib import Path
import hashlib,json
root=Path.cwd();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((root/'release/manifest.json').read_text())
assert m['schema']=='kv260.surface.dfx.v1' and m['offline_verified'] and m['identity']==198
for f,h in m['files'].items():assert sha(root/f)==h,f
for f,k in [('manifest.json','static_manifest_sha256'),('extensions.json','medical_extensions_sha256')]:
    assert sha(root.parent/'medical/release'/f)==m[k],f
print('SDF candidate sources and frozen medical release verified',flush=True)
PY
g++ -std=c++17 -O3 -mcpu=cortex-a53 -fPIC -shared -I/usr/include/xrt host/scope_bridge.cpp -lxrt_coreutil -pthread -o host/libscope.so.new
g++ -std=c++17 -O3 -mcpu=cortex-a53 -fopenmp -fPIC -shared host/reference.cpp -o host/libsurface_reference.so.new
mv host/libscope.so.new host/libscope.so
mv host/libsurface_reference.so.new host/libsurface_reference.so
install -m 644 release/medical_surface_partial.bin /lib/firmware/medical_surface_partial.bin
echo 'SDF candidate installed. No bitstream was loaded and no service was registered.'
