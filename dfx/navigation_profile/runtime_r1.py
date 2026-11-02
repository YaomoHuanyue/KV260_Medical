"""Explicit profile access only after source-bound RTL/route/host/firmware checks."""
from pathlib import Path
import ctypes as C
import hashlib
import json
import os
import numpy as np
from protocol_r1 import Native, CAPACITY

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SHA = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def verify():
    path = HERE / 'release_r1/manifest.json'
    if not path.is_file():
        raise RuntimeError('No completely verified profile release; no PL access')
    manifest = json.loads(path.read_text())
    if manifest.get('schema') != 'kv260.navigation_profile.dfx.v1' or manifest.get('identity') != 0xcd or not manifest.get('offline_verified'):
        raise RuntimeError('Unsupported profile release; no PL access')
    for key in ('source_sha256', 'artifact_sha256'):
        for name, digest in manifest[key].items():
            p = (HERE / name).resolve()
            if not p.is_relative_to(HERE) or SHA(p) != digest:
                raise RuntimeError('Changed profile release file ' + name)
    if SHA(ROOT / 'dfx/medical/release/manifest.json') != manifest['static_base_manifest_sha256']:
        raise RuntimeError('Changed static platform identity')
    if SHA(Path('/lib/firmware/medical_navigation_profile_r1_partial.bin')) != manifest['partial_bin_sha256']:
        raise RuntimeError('Profile firmware mismatch')
    host = json.loads((HERE / 'docs/host_build_ARM_r1.json').read_text())
    if host['status'] != 'compiled_no_PL_access' or SHA(HERE / 'build/libprofile_xrt_r1.so') != host['library_sha256']:
        raise RuntimeError('Changed profile XRT host binary')
    for name, digest in host['source_sha256'].items():
        if SHA(HERE / name) != digest:
            raise RuntimeError('Changed profile host source ' + name)
    if SHA(ROOT / 'dfx/surface_quality/release/manifest.json') != '19f03f956438dc20d8fb4565fe166bdf9d5bac4e7315cfbfedcc38e7019e88bc':
        raise RuntimeError('Changed accepted quality release')
    return manifest


class Session(Native):
    def __init__(self):
        self.handle = None
        self.restored = False
        self.calls = []

    def __enter__(self):
        self.manifest = verify()
        self.previous = Path.cwd()
        os.chdir(ROOT / 'dfx/medical')
        self.library = L = C.CDLL(str(HERE / 'build/libprofile_xrt_r1.so'))
        L.profile_error_r1.restype = C.c_char_p
        L.profile_open_r1.restype = C.c_void_p
        L.profile_close_r1.argtypes = [C.c_void_p]
        L.profile_restore_r1.argtypes = [C.c_void_p]
        L.profile_transfer_r1.argtypes = [C.c_void_p]*3 + [C.c_uint]*2 + [C.c_void_p]*2
        try:
            self.handle = L.profile_open_r1()
            if not self.handle:
                raise RuntimeError(L.profile_error_r1().decode())
        except BaseException:
            os.chdir(self.previous)
            raise
        return self

    def run(self, data, operation, *, output_count=None):
        if not self.handle:
            raise RuntimeError('Open a verified profile session first')
        data = np.ascontiguousarray(data, dtype=np.uint64)
        if data.ndim != 2 or data.shape[1] != 8 or operation not in (0, 1):
            raise ValueError('Complete 512-bit profile input words required')
        if output_count is not None and output_count != (1 if operation == 0 else CAPACITY):
            raise ValueError('Fixed full output capacity required')
        output = np.empty((CAPACITY, 8), dtype=np.uint64)
        phases = (C.c_double * 10)()
        status = C.c_uint32()
        code = self.library.profile_transfer_r1(self.handle, data.ctypes.data, output.ctypes.data,
            len(data), operation, C.byref(status), phases)
        if code:
            raise RuntimeError(self.library.profile_error_r1().decode())
        names = ('BO_capacity_growth', 'full_input_output_and_guard_setup_sync', 'partial_load',
            'complete_DFX_switch', 'hardware', 'full_readback_and_four_full_guards', 'full_output_copy', 'native_host_total')
        self.calls.append(dict(operation=operation, input_words=len(data), output_words=CAPACITY,
            status=status.value, phases_seconds={n: phases[i] for i, n in enumerate(names)},
            all_four_full_4096_byte_DMA_guards_checked=True))
        self.restored = False
        return output, status.value

    def restore(self):
        if not self.restored:
            if self.library.profile_restore_r1(self.handle):
                raise RuntimeError(self.library.profile_error_r1().decode())
            self.restored = True

    def __exit__(self, *exception):
        try:
            self.restore()
        finally:
            self.library.profile_close_r1(self.handle)
            self.handle = None
            os.chdir(self.previous)
