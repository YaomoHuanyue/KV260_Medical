"""Compile the complete D8 XRT bridge and prove invalid roots fail before hardware."""
from pathlib import Path
import ctypes as C
import hashlib
import json
import os
import platform
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
OUT = HERE / 'build_ARM_r1'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    assert platform.machine() == 'aarch64' and os.name != 'nt'
    assert not OUT.exists(), 'Preserve actual compiler evidence'
    plan = json.loads((HERE / 'build_inputs_r1.json').read_text())
    for name, expected in plan.items():
        assert sha(ROOT / name) == expected, name
    derivation = json.loads((HERE / 'session_derivation.json').read_text())
    for record in derivation['derivations']:
        generated = ROOT / record['generated']
        parent = ROOT / record['parent']
        assert sha(generated) == record['generated_SHA256']
        assert sha(parent) == record['parent_SHA256']
        source = generated.read_text()
        for edit in reversed(record['edits']):
            assert source.count(edit['after']) == edit['count']
            source = source.replace(edit['after'], edit['before'])
        assert source == parent.read_text(), 'Unrecorded original lifecycle change'
    assert not (HERE / 'release_r1').exists(), 'This first compile cannot open a qualified D8 session'
    OUT.mkdir()
    output = OUT / 'libD8_XRT.so'
    argv = ['g++', '-std=c++17', '-O3', '-mcpu=cortex-a53', '-ffp-contract=off',
            '-fno-fast-math', '-fPIC', '-shared', '-I/usr/include/xrt',
            '-MD', '-MF', str(OUT / 'bridge.d'), str(HERE / 'bridge.cpp'),
            '-pthread', '-lxrt_coreutil', '-Wl,-z,defs', '-o', str(output)]
    start = time.perf_counter()
    with (OUT / 'compile.log').open('xb') as stream:
        proc = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, cwd=ROOT)
    receipt = dict(argv=argv, exit_code=proc.returncode, seconds=time.perf_counter()-start,
                   source_and_input_SHA256=plan, compile_log_SHA256=sha(OUT / 'compile.log'))
    with (OUT / 'compile_receipt.json').open('x') as stream:
        json.dump(receipt, stream, indent=2)
    assert proc.returncode == 0, (OUT / 'compile.log').read_text(errors='replace')[-6000:]
    lib = C.CDLL(str(output))
    lib.D8_error.restype = C.c_char_p
    lib.D8_open_root.argtypes = [C.c_char_p]
    lib.D8_open_root.restype = C.c_void_p
    tests = []
    # Every path is real metadata input to the production C API. No session
    # release exists, so even a canonical legitimate root must fail before
    # FileLock, MMIO, XRT device allocation, or any firmware operation.
    for name, value in [('null', None), ('empty', b''), ('relative', b'.'),
                        ('relative_parent', b'../KV260_System'),
                        ('missing', os.fsencode(ROOT / 'D8_missing_root')),
                        ('nondirectory', os.fsencode(HERE / 'bridge.cpp')),
                        ('noncanonical', os.fsencode(ROOT) + b'/.'),
                        ('qualified_root_without_D8_release', os.fsencode(ROOT))]:
        handle = lib.D8_open_root(value)
        assert not handle, 'Invalid metadata opened hardware: ' + name
        error = lib.D8_error().decode()
        assert ('before hardware access' in error or 'release marker' in error), error
        tests.append(dict(name=name, rejected=True, error=error))
    exports = subprocess.check_output(['nm', '-D', '--defined-only', str(output)], text=True)
    assert all(symbol in exports for symbol in ('D8_open_root','D8_run','D8_restore','D8_close','D8_error'))
    assert not any(line.rstrip().endswith(' mesh_smooth') for line in exports.splitlines()), 'No PS algorithm may be linked'
    result = dict(status='actual_ARM_complete_D8_XRT_bridge_compiled_and8_pre_hardware_root_refusals_passed',
        actual_machine=platform.machine(), compiler=subprocess.check_output(['g++','--version'], text=True),
        original_session_literal_derivations_reversed_byte_exact=True, invalid_root_tests=tests,
        complete_XRT_graph_memory_register_protocol_and_pool_bridge_compiled=True,
        source_and_input_SHA256=plan, library_SHA256=sha(output),
        no_PS_smoothing_implementation_linked=True, D8_release_absent_during_negative_tests=True,
        XRT_device_or_MMIO_or_PL_accessed=False, actual_D8_session_on_board_still_pending=True,
        production_promoted=False, whole_goal_completed=False)
    with (OUT / 'verified.json').open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print('PASS actual ARM full D8 XRT bridge compiled;8 malformed roots refused; no PL session opened', flush=True)


if __name__ == '__main__':
    main()
