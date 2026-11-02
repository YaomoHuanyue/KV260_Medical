#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/jupyter_notebooks/KV260_System
[[ $EUID -eq 0 ]] || { echo 'Use sudo for the explicit UI trial'; exit 1; }
c=ui/releases/feature_completion_r6
[[ ! -e "$c/results/state_after_exact_speed_manual_r1.json" && ! -e "$c/results/state_during_exact_speed_manual_r1.json" ]] || exit 1
mkdir -p "$c/results"
mapfile -t pids < <(pgrep -f '^ui/build/medical_ui --root /home/ubuntu/jupyter_notebooks/KV260_System$' || true)
[[ ${#pids[@]} -eq 1 ]] || { echo 'Expected one accepted UI; no display changed'; exit 1; }
ui_pid=${pids[0]}
original_scope=$(.venv/bin/python - "$ui_pid" <<'PY'
from pathlib import Path
import hashlib,json,sys
root=Path.cwd();c=root/'ui/releases/feature_completion_r6'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
b=json.loads((c/'build_exact_speed_r1/build.json').read_text())
for key in ('source_sha256','shared_source_sha256'):
 for n,d in b[key].items():assert sha(root/n)==d,n
assert sha(c/'build_exact_speed_r1/medical_ui')==b['binary_sha256']
assert sha(root/'ui/build/medical_ui')=='3c6c3f7984a06eaf6810c0072461181134ce3a5707f13b1840b3bfdd921b122f'
assert sha(root/'dfx/surface_quality/release/manifest.json')=='19f03f956438dc20d8fb4565fe166bdf9d5bac4e7315cfbfedcc38e7019e88bc'
assert sha(root/'fixtures/own_ct/CT-chest.nrrd')=='4507b664690840abb6cb9af2d919377ffc4ef75b167cb6fd0f747befdb12e38e'
r=json.loads((root/'modules/surface_export/results/roundtrip_board_r1.json').read_text())
assert r['status']=='surface_export_strict_roundtrip_passed'
assert r['structures']['airway']['original_UI_expanded_attributes_exact']
for n,d in r['source_sha256'].items():assert sha(root/n)==d
entries=Path('/proc/'+sys.argv[1]+'/environ').read_bytes().split(b'\0')
values=[v.split(b'=',1)[1].decode() for v in entries if v.startswith(b'KV260_SCOPE_MODULE=')]
scope=values[0] if values else 'visualization'
assert scope in ('surface','surface_quality','visualization');print(scope)
PY
)
UI_STOPPED=0
restore_ui(){
 saved_rc=$?;trap - EXIT
 if [[ $UI_STOPPED -eq 1 ]]; then
  set +e
  .venv/bin/python - <<'PY'
import sys
sys.path.insert(0,'dfx/edt_volume')
from volume_runtime import VolumeSession
with VolumeSession(experimental=False) as session:session.return_to_scope()
print('Full static echo and accepted C6 restored',flush=True)
PY
  restore_rc=$?
  [[ $restore_rc -eq 0 ]] || { echo 'Restoration failed; no forced recovery'; exit "$restore_rc"; }
  nohup env -u KV260_NAV_CONTROLS_TEST KV260_SCOPE_MODULE="$original_scope" bash ui/run.sh \
   > "$c/results/restored_UI_exact_speed_manual_r1.log" 2>&1 < /dev/null &
  restored_pid=$!;sleep 4
  kill -0 "$restored_pid" || exit 1
  RESTORED_UI_PID="$restored_pid" .venv/bin/python - <<'PY'
from pathlib import Path
import hashlib,json,os,fcntl
root=Path.cwd();c=root/'ui/releases/feature_completion_r6'
with open('/tmp/kv260-ct-pl.lock','rb') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
pid=int(os.environ['RESTORED_UI_PID'])
assert Path(f'/proc/{pid}/cmdline').read_bytes()==b'ui/build/medical_ui\0--root\0'+str(root).encode()+b'\0'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(root/'ui/build/medical_ui')=='3c6c3f7984a06eaf6810c0072461181134ce3a5707f13b1840b3bfdd921b122f'
assert sha(root/'dfx/surface_quality/release/manifest.json')=='19f03f956438dc20d8fb4565fe166bdf9d5bac4e7315cfbfedcc38e7019e88bc'
r=dict(status='original_UI_restored_after_tested_R6_manual_review',PID=pid,
 PL_lock_free=True,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
 accepted_UI_binary_sha256=sha(root/'ui/build/medical_ui'),
 C9_release_sha256=sha(root/'dfx/surface_quality/release/manifest.json'),
 static_shell_reloaded=False,driver_unloaded=False,production_UI_changed=False)
p=c/'results/state_after_exact_speed_manual_r1.json';assert not p.exists();p.write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r),flush=True)
PY
  state_rc=$?;[[ $state_rc -eq 0 ]] || exit "$state_rc"
 fi
 exit "$saved_rc"
}
trap restore_ui EXIT
kill -TERM "$ui_pid"
for attempt in $(seq 1 30); do
 if ! kill -0 "$ui_pid" 2>/dev/null; then UI_STOPPED=1;break;fi
 sleep 1
done
[[ $UI_STOPPED -eq 1 ]] || { echo 'UI did not gracefully drain; no test started'; exit 1; }
.venv/bin/python - <<'PY'
import fcntl
with open('/tmp/kv260-ct-pl.lock','rb') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
PY
export KV260_SCOPE_MODULE="$original_scope"
.venv/bin/python - <<'PY'
from pathlib import Path
import hashlib,json,shutil
root=Path.cwd();c=root/'ui/releases/feature_completion_r6'
a=json.loads((c/'results/exact_speed_UI_trial_summary_r1.json').read_text())
assert a['status']=='original_complete_exact_controls_and_continuous_preview_with_same_final_RGBA_passed' and len(a['trials'])==2
assert a['binary_sha256']==hashlib.sha256((c/'build_exact_speed_r1/medical_ui').read_bytes()).hexdigest()
import hashlib
for item in a['trials']:
 assert hashlib.sha256((root/item['receipt']).read_bytes()).hexdigest()==item['sha256']
proof=c/'evidence_r1/whole_comparison/original_numeric_r2.json'
r=json.loads(proof.read_text());assert r['all_costs_parents_paths_radii_selection_and_original_fields_exact']
proof=json.loads((root/'modules/navigation_comparison/results/selected_pipeline_ARM_verified_PL_C4_group0_r1.json').read_text())
source=Path(proof['output']);assert source.is_relative_to(c/'runs')
assert hashlib.sha256((source/'pipeline.json').read_bytes()).hexdigest()==proof['result_pipeline_sha256']
for name in ('segmentation','reconstruction','navigation'):
 assert (source/name).is_dir() and not (source/name).is_symlink()
 for p in (source/name).iterdir():assert not p.is_symlink(),p
# Reuse the already independent seed; no extra case copy is created.
seed=c/'runs/manual_selected_seed_r3';assert seed.is_dir() and not seed.is_symlink()
for name in ('segmentation','reconstruction','navigation','airway_detail'):
 if not (source/name).exists():continue
 for p in (source/name).iterdir():
  dest=seed/name/p.name
  assert dest.is_file() and not dest.is_symlink()
  assert hashlib.sha256(dest.read_bytes()).digest()==hashlib.sha256(p.read_bytes()).digest()
pipeline=json.loads((source/'pipeline.json').read_text());pipeline['manual_view_source_sha256']=proof['result_pipeline_sha256']
assert json.loads((seed/'pipeline.json').read_text())==pipeline

PY
export KV260_IMPORT_TEST_RUNS="$PWD/$c/runs"
bash "$c/run_exact_speed_r1.sh" --input "$PWD/fixtures/own_ct/CT-chest.nrrd" \
 > "$c/results/manual_exact_speed_r1.log" 2>&1 &
manual_pid=$!
sleep 7
kill -0 "$manual_pid"
MANUAL_REVIEW_PID="$manual_pid" .venv/bin/python - <<'PY'
from pathlib import Path
import hashlib,json,os
root=Path.cwd();c=root/'ui/releases/feature_completion_r6';pid=int(os.environ['MANUAL_REVIEW_PID'])
expected=b'ui/releases/feature_completion_r6/build_exact_speed_r1/medical_ui\0--root\0'+str(root).encode()+b'\0--input\0'+str(root/'fixtures/own_ct/CT-chest.nrrd').encode()+b'\0'
assert Path(f'/proc/{pid}/cmdline').read_bytes()==expected
r=dict(status='tested_transparent_preview_UI_shown_for_optional_physical_review',PID=pid,
 binary_sha256=hashlib.sha256((c/'build_exact_speed_r1/medical_ui').read_bytes()).hexdigest(),
 input_sha256=hashlib.sha256((root/'fixtures/own_ct/CT-chest.nrrd').read_bytes()).hexdigest(),
 boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
 production_binary_changed=False,new_bitstream_loaded=False,physical_review_passed=False,
 wrapper_sha256=hashlib.sha256((c/'show_tested_exact_speed_UI_with_restore_r1.sh').read_bytes()).hexdigest())
p=c/'results/state_during_exact_speed_manual_r1.json';assert not p.exists()
p.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8');print(json.dumps(r),flush=True)
PY
wait "$manual_pid"
