#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
cd "$(dirname "$0")"
[[ ! -e build_selected_r1/build.json && ! -e build_selected_r1/build.log ]] || exit 1
python3 - <<'PY'
from pathlib import Path
import hashlib,json
c=Path.cwd();root=c.parents[2];r=json.loads((c/'source_closure_selected_r1.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for key in ('source_sha256','shared_source_sha256','old_source_sha256'):
 for n,d in r[key].items():assert sha(root/n)==d,n
assert sha(root/'ui/build/medical_ui')==r['accepted_UI_binary_sha256']
assert sha(root/'dfx/surface_quality/release/manifest.json')==r['C9_release_sha256']
PY
mkdir -p build_selected_r1
nice -n 10 g++ -std=c++17 -O2 -fPIC -mcpu=cortex-a53 -I src \
 src/main_selected_r1.cpp src/views.cpp src/pl_scope.cpp src/pl_composite.cpp \
 $(pkg-config --cflags --libs Qt5Widgets Qt5OpenGL Qt5Test) \
 -o build_selected_r1/medical_ui.new >build_selected_r1/build.log 2>build_selected_r1/build.stderr.log
mv build_selected_r1/medical_ui.new build_selected_r1/medical_ui
python3 - <<'PY'
from pathlib import Path
import hashlib,json
c=Path.cwd();root=c.parents[2];r=json.loads((c/'source_closure_selected_r1.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for key in ('source_sha256','shared_source_sha256','old_source_sha256'):
 for n,d in r[key].items():assert sha(root/n)==d,n
proof=dict(status='selected_path_application_UI_compiled_actual_ARM',
 binary_sha256=sha(c/'build_selected_r1/medical_ui'),source_sha256=r['source_sha256'],
 shared_source_sha256=r['shared_source_sha256'],
 source_closure_sha256=sha(c/'source_closure_selected_r1.json'),medical_PL_cores_changed=False,
 runtime_candidate_folder_dependency=False,production_UI_promoted=False)
(c/'build_selected_r1/build.json').write_text(json.dumps(proof,indent=2)+'\n')
print(proof['status'])
PY
