#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/jupyter_notebooks/KV260_System
[[ $EUID -eq 0 ]] || { echo 'Use sudo for explicit board comparison'; exit 1; }
c=ui/releases/feature_completion_r6
[[ ! -e "$c/results/transparent_interaction_trial_summary_r1.json" && ! -e "$c/results/state_after_transparent_interaction_r1.json" ]] || exit 1
mapfile -t pids < <(pgrep -f '^ui/build/medical_ui --root /home/ubuntu/jupyter_notebooks/KV260_System$' || true)
[[ ${#pids[@]} -eq 1 ]] || { echo 'Expected one accepted original UI'; exit 1; }
ui_pid=${pids[0]}
original_scope=$(.venv/bin/python - "$ui_pid" <<'PY'
from pathlib import Path
import hashlib,json,sys
root=Path.cwd();c=root/'ui/releases/feature_completion_r6'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(root/'ui/build/medical_ui')=='3c6c3f7984a06eaf6810c0072461181134ce3a5707f13b1840b3bfdd921b122f'
assert sha(root/'dfx/surface_quality/release/manifest.json')=='19f03f956438dc20d8fb4565fe166bdf9d5bac4e7315cfbfedcc38e7019e88bc'
r=json.loads((c/'build_interactive_r1/build.json').read_text())
for key in ('source_sha256','shared_source_sha256'):
 for n,d in r[key].items():assert sha(root/n)==d,n
assert sha(c/'build_interactive_r1/medical_ui')==r['binary_sha256']
proof=json.loads((root/'modules/navigation_comparison/results/selected_output_ARM_r1.json').read_text())
assert len(proof['cases'])==60
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
print('Full 1 MiB static echo and accepted C6 restored',flush=True)
PY
  restore_rc=$?
  [[ $restore_rc -eq 0 ]] || { echo 'Restoration failed; no forced recovery'; exit "$restore_rc"; }
  nohup env KV260_SCOPE_MODULE="$original_scope" bash ui/run.sh \
   > "$c/results/restored_UI_transparent_interaction_r1.log" 2>&1 < /dev/null &
  restored_pid=$!;sleep 4
  kill -0 "$restored_pid" || exit 1
  RESTORED_UI_PID="$restored_pid" .venv/bin/python - <<'PY'
from pathlib import Path
import hashlib,json,os,fcntl
root=Path.cwd();c=root/'ui/releases/feature_completion_r6';pid=int(os.environ['RESTORED_UI_PID'])
with open('/tmp/kv260-ct-pl.lock','rb') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert Path(f'/proc/{pid}/cmdline').read_bytes()==b'ui/build/medical_ui\0--root\0'+str(root).encode()+b'\0'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(root/'ui/build/medical_ui')=='3c6c3f7984a06eaf6810c0072461181134ce3a5707f13b1840b3bfdd921b122f'
r=dict(status='original_UI_restored_after_selected_path_actual_C4_test',PID=pid,PL_lock_free=True,
 boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
 accepted_UI_binary_sha256=sha(root/'ui/build/medical_ui'),static_shell_reloaded=False,driver_unloaded=False,
 production_UI_changed=False,full_static_echo_and_C6_restore_passed=True,
 wrapper_sha256=sha(c/'test_transparent_interaction_with_restore_r1.sh'))
p=c/'results/state_after_transparent_interaction_r1.json';assert not p.exists()
p.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
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
[[ $UI_STOPPED -eq 1 ]] || { echo 'UI did not gracefully drain; no PL trial'; exit 1; }
.venv/bin/python - <<'PY'
import fcntl
with open('/tmp/kv260-ct-pl.lock','rb') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
PY
source_result="$PWD/$c/runs/20261006_123452_51f02353"
.venv/bin/python - <<'PY'
from pathlib import Path
import hashlib,json
c=Path('modules/navigation_comparison');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
r=json.loads((c/'results/selected_action_original_fixtures_r1.json').read_text())
assert len(r['cases'])==22 and all(v['complete_original_output_padding_passed'] for v in r['cases'])
assert sha(c/'test_selected_action_fixtures_r1.py')==r['source_sha256']
b=Path('dfx/route_audit_speed');assert sha(b/'release/manifest.json')==r['manifest_sha256']
for n,d in r['fixture_sha256'].items():assert sha(b/n)==d
r=json.loads((c/'results/selected_pipeline_ARM_verified_PL_C4_group0_r1.json').read_text())
assert r['all_route_camera_fields_match_actual_C4'] and r['route_audit_backend']=='pl'
for n,d in r['source_sha256'].items():assert sha(c/n)==d
print('Unchanged complete C4 fixtures and actual PL producer bindings verified',flush=True)
PY
for mode in exact_controls interaction; do
 evidence="$PWD/$c/evidence_transparent_r1/$mode"
 [[ ! -e "$evidence" ]] || exit 1
 if [[ "$mode" = exact_controls ]]; then
  env KV260_IMPORT_TEST_RUNS="$PWD/$c/runs" KV260_COMPOSITE_UI_TEST=1 \
   bash "$c/run_interactive_r1.sh" --input "$PWD/fixtures/own_ct/CT-chest.nrrd" --evidence "$evidence" \
   > "$c/results/transparent_exact_controls_r1.log" 2>&1
 else
  env KV260_IMPORT_TEST_RUNS="$PWD/$c/runs" KV260_TRANSPARENT_INTERACTION_TEST=1 \
   bash "$c/run_interactive_r1.sh" --input "$PWD/fixtures/own_ct/CT-chest.nrrd" --evidence "$evidence" \
   > "$c/results/transparent_interaction_r1.log" 2>&1
 fi
done
.venv/bin/python - <<'PY'
from pathlib import Path
import hashlib,json
root=Path.cwd();c=root/'ui/releases/feature_completion_r6';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
a=c/'evidence_transparent_r1/exact_controls/ui_acceptance.json';b=c/'evidence_transparent_r1/interaction/transparent_interaction_UI.json'
x=json.loads(a.read_text());y=json.loads(b.read_text())
assert x['status']=='passed' and y['status']=='passed'
assert y['settled_pixels_equal_exact_only_baseline'] and y['no_automatic_mesh_or_layer_reduction']
assert y['no_exact_request_during_continuous_mouse_motion']
proof=dict(status='original_complete_exact_controls_and_continuous_preview_with_same_final_RGBA_passed',
 binary_sha256=sha(c/'build_interactive_r1/medical_ui'),new_medical_bitstream=False,physical_mouse_verified=False,
 trials=[dict(receipt=p.relative_to(root).as_posix(),sha256=sha(p)) for p in (a,b)],
 preview_actual_fps=y['actual_preview_update_fps'],baseline_exact_round_trip_seconds=y['baseline_exact_round_trip_seconds'])
out=c/'results/transparent_interaction_trial_summary_r1.json';assert not out.exists()
out.write_text(json.dumps(proof,indent=2)+'\n');print(proof['status'],flush=True)
PY
