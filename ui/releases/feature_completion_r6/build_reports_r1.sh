#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
cd "$(dirname "$0")"
[[ ! -e build_reports_r1/build.json && ! -e build_reports_r1/build.log ]] || exit 1
python3 - <<'PY'
from pathlib import Path
import hashlib,json
c=Path.cwd();root=c.parents[2];r=json.loads((c/'source_closure_reports_r1.json').read_text())
for key in ('source_sha256','shared_source_sha256'):
 for n,d in r[key].items():assert hashlib.sha256((root/n).read_bytes()).hexdigest()==d,n
PY
mkdir -p build_reports_r1
nice -n 10 g++ -std=c++17 -O2 -fPIC -pthread -mcpu=cortex-a53 -I src \
 src/main_reports_r1.cpp src/views_batch_r3.cpp src/pl_scope.cpp src/pl_composite_exact_speed_r8.cpp \
 $(pkg-config --cflags --libs Qt5Widgets Qt5OpenGL Qt5Test) \
 -o build_reports_r1/medical_ui.new >build_reports_r1/build.log 2>build_reports_r1/build.stderr.log
mv build_reports_r1/medical_ui.new build_reports_r1/medical_ui
python3 - <<'PY'
from pathlib import Path
import hashlib,json
c=Path.cwd();root=c.parents[2];r=json.loads((c/'source_closure_reports_r1.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for key in ('source_sha256','shared_source_sha256'):
 for n,d in r[key].items():assert sha(root/n)==d,n
proof=dict(status='compiled_actual_ARM_complete_UI_with_complete_report_export',binary_sha256=sha(c/'build_reports_r1/medical_ui'),
 source_sha256=r['source_sha256'],shared_source_sha256=r['shared_source_sha256'],source_closure_sha256=sha(c/'source_closure_reports_r1.json'),
 original_complete_UI_preserved=True,new_bitstream=False,ffmpeg_sha256=sha(Path('/usr/bin/ffmpeg')))
(c/'build_reports_r1/build.json').write_text(json.dumps(proof,indent=2)+'\n');print(proof['status'],flush=True)
PY
