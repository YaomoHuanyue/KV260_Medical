#!/bin/bash
set -euo pipefail
cd /home/ubuntu/jupyter_notebooks/KV260_System/dfx/medical
test "$(id -u)" = 0
if [ ! -e /tmp/kv260-ct-pl.lock ]; then install -m 660 -o ubuntu -g ubuntu /dev/null /tmp/kv260-ct-pl.lock; fi
exec 7</tmp/kv260-ct-pl.lock;flock -n 7
if find /proc/[0-9]*/fd -lname '*renderD*' -print 2>/dev/null | grep -q .;then echo 'Live XRT client; unchanged';exit 1;fi
if find /sys/bus/platform/devices -maxdepth 1 -name 'CU.*' -print | grep -q .;then echo 'Initialized CUs; clean reboot required';exit 1;fi
python3 - <<'PY'
from pathlib import Path
import hashlib,json
r=Path('release');m=json.loads((r/'manifest.json').read_text())
assert m['offline_verified'] is True
for name,sha in m['files'].items():assert hashlib.sha256((r/name).read_bytes()).hexdigest()==sha,name
PY
mkdir -p /lib/firmware/xilinx/kv260-dfx-medical
for file in dfx_medical.bin dfx_medical.dtbo dfx_medical.xclbin shell.json;do install -m 644 "release/$file" "/lib/firmware/xilinx/kv260-dfx-medical/$file";done
for v in mc smooth;do install -m 644 "release/medical_${v}_partial.bin" "/lib/firmware/medical_${v}_partial.bin";done
if grep -q '^zocl ' /proc/modules;then modprobe -r zocl;fi
xmutil unloadapp
echo 0 >/sys/class/fpga_manager/fpga0/flags
xmutil loadapp kv260-dfx-medical
modprobe zocl
test "$(cat /sys/class/fpga_manager/fpga0/state)" = operating
python3 - <<'PY'
from pathlib import Path
rows=[r.split() for r in Path('/sys/kernel/debug/clk/clk_summary').read_text().splitlines()]
c=next(r for r in rows if r and r[0]=='pl0_ref')
assert int(c[1])>0 and int(c[2])>0 and abs(int(c[4])-100000000)<=100,c
print('PL0 verified',c[4])
PY
sha256sum release/dfx_medical.bin | cut -d' ' -f1 >/run/kv260-dfx-medical-loaded.sha256
