#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
[[ $EUID -eq 0 ]] || { echo 'Use sudo for the manual HDMI UI'; exit 1; }
mkdir -p /run/kv260-ui-runtime
chmod 700 /run/kv260-ui-runtime
export XDG_RUNTIME_DIR=/run/kv260-ui-runtime
export LD_PRELOAD=/usr/lib/aarch64-linux-gnu/mali/wayland/libMali.so.9.0
export QT_QPA_PLATFORM=eglfs
export QT_QPA_EGLFS_INTEGRATION=eglfs_kms
export QT_QPA_EGLFS_KMS_CONFIG="$PWD/ui/kms.json"
export QT_QPA_EGLFS_KMS_ATOMIC=0
export QT_QPA_EGLFS_FORCE888=1
export PYTHONIOENCODING=utf-8
export KV260_SCOPE_MODULE="${KV260_SCOPE_MODULE:-surface}"
exec ui/releases/feature_completion_r6/build_batch_r4/medical_ui --root "$PWD" "$@"
