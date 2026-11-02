#!/usr/bin/env python3
"""Read-only admission for V2's external MP4 encoder dependency.

Run on the target Linux board before delivery/startup. This complements, and
does not replace, ui/v2/runtime.py --verify-only --installed. It checks the
exact executable and encoder requested by the frozen V2 Encoder class. It
does not install packages, encode media, start the UI, access PL or write files.
Only Python's standard library is required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time


FFMPEG = Path('/usr/bin/ffmpeg')
RECHECK = 'python3 -B tools/check_v2_environment.py'
ENCODER_LINE = re.compile(r'^\s*V[A-Z.]{5}\s+libx264(?:\s|$)', re.MULTILINE)


def check_environment(timeout_seconds: float = 5.0) -> dict:
    """Inspect the installed executable without allocating FPGA resources."""
    if not math.isfinite(timeout_seconds) or not 1 <= timeout_seconds <= 30:
        raise ValueError('timeout_seconds must be finite and between 1 and 30')
    command = [str(FFMPEG), '-hide_banner', '-encoders']
    report = {
        'schema': 'kv260.v2.encoder_environment.v1',
        'scope': 'External MP4 dependency only; existing V2 manifest/firmware checks remain required',
        'passed': False,
        'read_only': True,
        'checks': {
            'ffmpeg_executable': {'path': str(FFMPEG), 'status': 'not_checked'},
            'libx264_video_encoder': {'name': 'libx264', 'status': 'not_checked'},
        },
        'probe': {'command': command, 'timeout_seconds': timeout_seconds, 'started': False},
        'issues': [],
        'repair_commands': [],
        'recheck_command_from_project_root': RECHECK,
    }

    def fail(code: str, message: str, commands: list[str]) -> dict:
        report['issues'].append({'code': code, 'message': message})
        report['repair_commands'] = commands
        return report

    executable = report['checks']['ffmpeg_executable']
    try:
        is_file = FFMPEG.is_file()
        is_executable = is_file and os.access(FFMPEG, os.X_OK)
    except OSError as error:
        executable['status'] = 'failed'
        return fail('ffmpeg_path_error', str(error), [f'ls -l {FFMPEG}'])
    if not is_file:
        executable['status'] = 'missing'
        return fail(
            'ffmpeg_missing',
            'V2 MP4 export requires /usr/bin/ffmpeg; the file is absent or is not a regular file.',
            ['sudo apt-get install --no-install-recommends ffmpeg'],
        )
    if not is_executable:
        executable['status'] = 'not_executable'
        return fail(
            'ffmpeg_not_executable',
            '/usr/bin/ffmpeg exists but is not executable for this user.',
            ['sudo apt-get install --reinstall --no-install-recommends ffmpeg'],
        )
    executable['status'] = 'passed'
    encoder = report['checks']['libx264_video_encoder']
    report['probe']['started'] = True
    start = time.monotonic()
    # Match Encoder::work: the CPU codec must not inherit the UI's Mali/Qt setup.
    probe_environment = dict(os.environ, LC_ALL='C')
    probe_environment.pop('LD_PRELOAD', None)
    probe_environment.pop('QT_QPA_PLATFORM', None)
    try:
        completion = subprocess.run(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=timeout_seconds, check=False,
            encoding='utf-8', errors='replace', env=probe_environment,
        )
    except subprocess.TimeoutExpired:
        encoder['status'] = 'probe_timeout'
        report['probe']['elapsed_seconds'] = round(time.monotonic() - start, 6)
        return fail(
            'ffmpeg_probe_timeout',
            'Encoder listing exceeded the timeout; no encoder availability is claimed. '
            'Inspect executable startup/resource problems, then rerun this check.',
            ['timeout 5s /usr/bin/ffmpeg -hide_banner -encoders'],
        )
    except OSError as error:
        encoder['status'] = 'probe_failed'
        report['probe']['elapsed_seconds'] = round(time.monotonic() - start, 6)
        return fail(
            'ffmpeg_start_failed', str(error),
            ['sudo apt-get install --reinstall --no-install-recommends ffmpeg'],
        )
    output = completion.stdout or ''
    report['probe'].update({
        'elapsed_seconds': round(time.monotonic() - start, 6),
        'returncode': completion.returncode,
        'output_SHA256': hashlib.sha256(output.encode('utf-8')).hexdigest(),
    })
    if completion.returncode != 0:
        encoder['status'] = 'probe_failed'
        report['probe']['diagnostic_excerpt'] = output[-2000:]
        return fail(
            'ffmpeg_probe_failed',
            f'FFmpeg encoder listing returned {completion.returncode}; inspect the diagnostic excerpt.',
            ['timeout 5s /usr/bin/ffmpeg -hide_banner -encoders',
             'sudo apt-get install --reinstall --no-install-recommends ffmpeg'],
        )
    if not ENCODER_LINE.search(output):
        encoder['status'] = 'missing'
        return fail(
            'libx264_missing',
            'The installed FFmpeg does not list the libx264 video encoder required by V2. '
            'libx264rgb alone does not satisfy this dependency.',
            ['sudo apt-get install --reinstall --no-install-recommends ffmpeg'],
        )
    encoder['status'] = 'passed'
    report['passed'] = True
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout-seconds', type=float, default=5.0,
                        help='Encoder-listing timeout, from 1 to 30 seconds (default: 5).')
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout_seconds) or not 1 <= args.timeout_seconds <= 30:
        parser.error('--timeout-seconds must be finite and between 1 and 30')
    report = check_environment(args.timeout_seconds)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
