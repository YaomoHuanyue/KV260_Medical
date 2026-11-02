#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p host/build
g++ -std=c++17 -O3 -fPIC -shared -fopenmp -ffp-contract=off -mcpu=cortex-a53 host/mesh_distance_native.cpp -o host/build/libmesh_distance.so.new
mv host/build/libmesh_distance.so.new host/build/libmesh_distance.so
python3 - <<'PY'
from pathlib import Path
import hashlib,json
root=Path.cwd();files=['host/mesh_distance_native.cpp','host/build_native.sh','host/build/libmesh_distance.so','mesh_clearance_native.py']
record=dict(status='compiled_ARM_CPU_geometric_baseline_no_hardware_access',flags='-O3 -fopenmp -ffp-contract=off -mcpu=cortex-a53',files_sha256={f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in files})
(root/'host/build/build.json').write_text(json.dumps(record,indent=2)+'\n')
PY
