"""Foreground systemd supervisor around the selected accepted UI launcher (profile "ui": v3, rollback v2).

Only the boot-time static-shell load is automatic. The UI retains ownership of
medical tasks and graceful graphics/DMA release. No worker is force-killed.
"""
from pathlib import Path, PurePosixPath
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import time
import traceback
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
RUN = Path('/run/kv260-medical-ui')
STOP = False


def notify(message):
    target = os.environ.get('NOTIFY_SOCKET')
    if target:
        if target.startswith('@'):
            target = '\0' + target[1:]
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(target)
            s.sendall(message.encode())


def status(message):
    print(message, flush=True)
    notify('STATUS=' + message)


def requested_stop(signum, frame):
    global STOP
    STOP = True


def save(name, value):
    path = RUN / name
    pending = path.with_suffix(path.suffix + '.pending')
    with pending.open('w', encoding='utf-8') as f:
        json.dump(value, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(pending, path)


def ui_name():
    name = json.loads((ROOT / 'system/autostart/profile.json').read_text()).get('ui', 'v2')
    if name not in ('v2', 'v3'):
        raise ValueError('Unsupported UI in autostart profile')
    return name


def load_launcher():
    spec = importlib.util.spec_from_file_location('accepted_%s_autostart_launcher' % ui_name(), ROOT / 'ui' / ui_name() / 'runtime.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project_path(name):
    rel = PurePosixPath(name)
    if not name or rel.is_absolute() or '..' in rel.parts or '\\' in name or ':' in name:
        raise ValueError('Profile paths must stay within this project')
    p = (ROOT / rel).resolve()
    if not p.is_relative_to(ROOT):
        raise ValueError('Profile path escapes this project')
    return p


def select_case(launcher):
    profile = json.loads((ROOT / 'system/autostart/profile.json').read_text())
    if profile['schema'] != 'kv260.medical_autostart.v1' or profile['compute_on_boot'] is not False:
        raise ValueError('Unsupported autostart profile')
    ct = project_path(profile['input'])
    digest = launcher.sha(ct)
    if digest != profile['input_SHA256']:
        raise ValueError('Configured CT SHA256 differs; update the profile explicitly')
    selected = project_path(profile['result']) if profile.get('result') else None
    if selected is not None:
        pipeline = selected / 'pipeline.json'
        if pipeline.is_file():
            value = json.loads(pipeline.read_text())
            if value.get('status') != 'passed' or value.get('input_sha256') != digest:
                raise ValueError('Saved result does not match the configured completed CT')
        elif profile.get('missing_result') == 'open_CT_only':
            status('Saved result missing: opening CT without running medical computation')
            selected = None
        else:
            raise FileNotFoundError(pipeline)
    return str(ct), None if selected is None else str(selected)


def prepare_platform(launcher):
    manifest = launcher.verify(installed=False)
    if launcher.running():
        raise RuntimeError('A project UI is already running; use it or close it normally before starting this service')
    status('Checking XRT and HDMI devices')
    drm = Path(json.loads((ROOT / 'ui/kms.json').read_text())['device'])
    deadline = time.monotonic() + 60
    while not drm.exists() or not Path('/dev/dri/renderD128').exists():
        if STOP:
            return False
        if time.monotonic() > deadline:
            raise RuntimeError('DRM/XRT devices not ready')
        time.sleep(.25)
    marker = Path('/run/kv260-dfx-medical-loaded.sha256')
    if marker.exists():
        if marker.read_text().strip() != manifest['static_sha256']:
            raise RuntimeError('Unrecognized static shell marker; clean reboot required')
        if Path('/sys/class/fpga_manager/fpga0/state').read_text().strip() != 'operating':
            raise RuntimeError('FPGA manager is not operating')
        status('Accepted DFX static platform already loaded; reusing it')
    else:
        if STOP:
            return False
        status('Loading the accepted DFX static platform')
        # Keep the original CU/owner/clock guards. Do not time out or kill a loader.
        subprocess.run(['/bin/bash', str(ROOT / 'dfx/medical/load_shell.sh')], cwd=ROOT, check=True)
    if STOP:
        return False
    launcher.verify(installed=True)
    # Cold SD-card/library reads can exceed the manual probe's 5-second default.
    subprocess.run([sys.executable, '-B', str(ROOT / 'tools/check_v2_environment.py'),
                    '--timeout-seconds', '30'], cwd=ROOT, check=True)
    return True


def sync_mutable_identity(launcher, started):
    path = ROOT / 'tools/storage_runtime_identity.json'
    if path.exists():
        state = json.loads(path.read_text())
        state.update(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                     medical_shell_marker=Path('/run/kv260-dfx-medical-loaded.sha256').read_text().strip(),
                     autostart_service='kv260-medical-ui.service')
        # A prior boot's open scene identity must not be asserted for this process.
        for key in ('scene', 'actual_selected_scene'):
            state.pop(key, None)
        launcher.save(path, state)


def run():
    if os.geteuid() != 0 or os.uname().machine != 'aarch64':
        raise RuntimeError('Run this service as root on the configured KV260')
    RUN.mkdir(mode=0o750, exist_ok=True)
    signal.signal(signal.SIGTERM, requested_stop)
    signal.signal(signal.SIGINT, requested_stop)
    launcher = load_launcher()
    ct, result = select_case(launcher)
    if not prepare_platform(launcher):
        return 0
    status('Starting %s and restoring the completed case' % ui_name().upper())
    launcher.launch(SimpleNamespace(input=ct, result=result, replace_running=False, activate=False))
    started = json.loads((ROOT / 'ui' / ui_name() / 'session/started.json').read_text())
    owner = started['owner']
    pid = owner['PID']
    assert launcher.proc(pid)['ticks'] == owner['ticks']
    assert launcher.sha(Path('/proc') / str(pid) / 'exe') == started['binary_SHA256']
    sync_mutable_identity(launcher, started)
    state = dict(schema='kv260.medical_autostart.state.v1', UI_PID=pid,
                 UI_ticks=owner['ticks'], supervisor_PID=os.getpid(), input=ct, result=result,
                 boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                 binary_SHA256=started['binary_SHA256'], compute_on_boot=False,
                 UI_prepare_seconds=started['prepare_seconds'], systemd_autostart=True, ui=ui_name())
    save('started.json', state)
    if not STOP:
        status('%s ready on HDMI; completed case restored' % ui_name().upper())
        notify('READY=1')
    stopping_sent = False
    while True:
        if STOP and not stopping_sent:
            status('Stopping %s gracefully; waiting for active tasks and graphics release' % ui_name().upper())
            notify('STOPPING=1')
            try:
                if launcher.proc(pid)['ticks'] == owner['ticks']:
                    os.kill(pid, signal.SIGTERM)
            except (FileNotFoundError, ProcessLookupError):
                pass
            stopping_sent = True
        try:
            done, status_code = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            done, status_code = pid, 0 if STOP else 256
        if done:
            code = os.waitstatus_to_exitcode(status_code)
            save('stopped.json', dict(UI_PID=pid, UI_exit_code=code, stop_requested=STOP))
            print(ui_name().upper(), 'exited with code', code, flush=True)
            return 0 if STOP or code == 0 else 1
        time.sleep(.2)


if __name__ == '__main__':
    try:
        sys.exit(run())
    except Exception:
        traceback.print_exc()
        try:
            notify('STATUS=Autostart failed; see journalctl -u kv260-medical-ui.service')
        except OSError:
            pass
        sys.exit(1)
