#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/jupyter_notebooks/KV260_System
base=ui/docs/route_canonical_r1
mkdir -p "$base"
test ! -e "$base/trial.json"
test ! -e "$base/native"
test ! -e ui/build/route_metrics_release_r1.json
boot=$(cat /proc/sys/kernel/random/boot_id)
.venv/bin/python - <<'PY'
from pathlib import Path
import hashlib,json,sys
root=Path.cwd();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
sys.path.insert(0,str(root/'tools'));from accepted_native_ui import accepted
release=accepted(root);p=root/'ui/candidates/route_metrics_r2/canonical_adapters'
proposal=json.loads((p/'proposal.json').read_text())
for name,digest in proposal['evidence_sha256'].items():assert sha(root/name)==digest,name
for name,digest in proposal['current_canonical_source_sha256'].items():assert sha(root/name)==digest,name
for name,digest in proposal['proposed_source_sha256'].items():assert sha(p/name.removeprefix('ui/'))==digest,name
native_path=root/'ui/candidates/route_metrics_r2/docs/native_acceptance_r2.json';native=json.loads(native_path.read_text())
assert native['actual_HDMI'] and native['protocol3_PS_recalculation_forbidden_and_passed']
for name,digest in native['evidence_sha256'].items():assert sha(root/name)==digest,name
for name,digest in native['source_sha256'].items():assert sha(root/name)==digest,name
board=root/'dfx/route_audit_speed/docs/board_acceptance_r14.json';r=json.loads(board.read_text())
assert r['PL_audit_is_faster_than_optimized_PS']
for name,digest in r['source_sha256'].items():assert sha(root/name)==digest,name
for name,digest in r['evidence_sha256'].items():assert sha(root/'dfx/route_audit_speed'/name)==digest,name
archive=root/'ui/archive/20261004_route_metrics_r2';inventory=archive/'inventory.json'
for name,digest in json.loads(inventory.read_text())['inventory'].items():assert sha(archive/name)==digest,name
pid=int((root/'ui/docs/live_ui.pid').read_text());process=Path('/proc')/str(pid)
assert (process/'exe').resolve()==root/'ui/build/medical_ui' and sha(process/'exe')==release['binary_sha256']
for child in (process/'task'/str(pid)/'children').read_text().split():
 cmd=Path('/proc')/child/'cmdline'
 if cmd.exists():
  args=cmd.read_bytes().split(b'\0');assert not (any(a.endswith(b'/backend.py') for a in args) and b'run' in args),'Medical task still running'
before=root/'ui/docs/route_canonical_r1/before.json';assert not before.exists()
before.write_text(json.dumps(dict(binary_sha256=release['binary_sha256'],UI_source_sha256=release['source_sha256'],
 old_adapters_sha256=proposal['current_canonical_source_sha256'],new_adapters_sha256=proposal['proposed_source_sha256'],
 archive_inventory_sha256=sha(inventory),proposal_sha256=sha(p/'proposal.json'),native_acceptance_sha256=sha(native_path)),indent=2)+'\n')
print('Actual candidate, identical-precision speed, preserved UI and canonical proposal verified',flush=True)
PY
old_pid=$(cat ui/docs/live_ui.pid)
kill -TERM "$old_pid"
for i in $(seq 1 600);do [[ ! -d /proc/$old_pid ]] && break;sleep .1;done
[[ ! -d /proc/$old_pid ]] || { echo 'UI still completing work; defer canonical trial';exit 1; }
restore_ui(){
 result=$?;trap - EXIT;restored=0
 if (exec 9</tmp/kv260-ct-pl.lock;flock -n 9);then
  if [[ "$result" -ne 0 ]];then
   python3 - <<'PY'
from pathlib import Path
import hashlib,json,shutil
root=Path.cwd();before=json.loads((root/'ui/docs/route_canonical_r1/before.json').read_text());archive=root/'ui/archive/20261004_route_metrics_r2'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(archive/'inventory.json')==before['archive_inventory_sha256']
for name,digest in before['old_adapters_sha256'].items():
 assert sha(archive/name)==digest;target=root/name;tmp=target.with_name(target.name+'.rollback.new');shutil.copy2(archive/name,tmp);assert sha(tmp)==digest;tmp.replace(target)
PY
  fi
  nohup bash ui/run.sh >ui/docs/live_route_canonical_r1.log 2>&1 </dev/null &
  restored=$!;echo "$restored" >ui/docs/live_ui.pid;sleep 3
 else echo 'PL owned by a live worker; retain worker and buffers';fi
 python3 - "$result" "$restored" "$boot" <<'PY'
from pathlib import Path
import hashlib,json,sys,time
root=Path.cwd();base=root/'ui/docs/route_canonical_r1';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=json.loads((base/'before.json').read_text());code,pid=int(sys.argv[1]),int(sys.argv[2]);exe=Path('/proc')/str(pid)/'exe'
alive=pid>0 and exe.exists();digest=sha(exe) if alive else None;boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
expected=before['new_adapters_sha256'] if code==0 else before['old_adapters_sha256']
for name,h in expected.items():assert sha(root/name)==h,name
passed=code==0 and alive and digest==before['binary_sha256'] and boot==sys.argv[3]
record=dict(trial_terminal=True,trial_exit_code=code,trial_passed=passed,restored_ui_pid=pid,restored_UI_alive=alive,
 restored_UI_binary_sha256=digest,boot_id_before=sys.argv[3],boot_id_after=boot,
 script_sha256=sha(root/'tools/run_route_metrics_canonical_trial_r1.sh'),before_sha256=sha(base/'before.json'),
 adapters_sha256=expected,rollback_performed=code!=0)
(base/'trial.json').write_text(json.dumps(record,indent=2)+'\n')
if alive:
 (root/'ui/docs/live_state_after_route_canonical_r1.json').write_text(json.dumps(dict(running_pid=pid,binary_sha256=digest,
  boot_id=boot,observed_UTC=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),default_UI_source_changed=code==0),indent=2)+'\n')
if code==0:assert passed
PY
 exit "$result"
}
trap restore_ui EXIT
python3 - <<'PY'
from pathlib import Path
import hashlib,json,shutil
root=Path.cwd();p=root/'ui/candidates/route_metrics_r2/canonical_adapters';proposal=json.loads((p/'proposal.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name,digest in proposal['proposed_source_sha256'].items():
 target=root/name;tmp=target.with_name(target.name+'.route.new');shutil.copy2(p/name.removeprefix('ui/'),tmp);assert sha(tmp)==digest;tmp.replace(target)
PY
export KV260_MEDICAL_BATCH_VERTICES=96000 KV260_COMPOSITE_UI_TEST=0 PYTHONIOENCODING=utf-8
bash ui/run.sh --acceptance-run --evidence "$PWD/$base/native"
.venv/bin/python tools/collect_route_metrics_canonical_r1.py
test "$boot" = "$(cat /proc/sys/kernel/random/boot_id)"
echo 'Canonical complete medical native trial and independent audit/route/camera checks passed'
