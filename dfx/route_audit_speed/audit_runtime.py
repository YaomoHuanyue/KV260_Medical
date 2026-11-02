"""Gated candidate session; no whole-bit reload or fallback to unverified PL."""
from pathlib import Path
import ctypes
import hashlib
import json
import os
import threading
import numpy as np

ROOT = Path(__file__).resolve().parent
MEDICAL = ROOT.parent/'medical'
STATIC_MANIFEST = 'ec51ff6cdf8077005a96c228f61e2d8ab2daa4f0c66f37865bd719c2f1eeefbc'
SURFACE_MANIFEST = 'e9795aabf902acfd582ddda27d27ca6aa2659e3dc2ccb21078aa573e6ddd599b'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_diagnostic(data):
    """Reject unsupported raw inputs before any DMA or core access.

    The diagnostic radii use the same float32 storage as production scene
    radii. A finite double outside that storage range would become infinity.
    """
    n = int(data[0, 1])
    values = data.view(np.float64)
    if (data[0, 0] != 0x4155444954303031 or n > 4096 or len(data) != n+1 or
            not np.isfinite(values[0, 2:6]).all() or np.any(values[0, 2:6] < 0)):
        raise ValueError('Malformed raw audit command')
    rows = values[1:, :5]
    if (not np.isfinite(rows).all() or np.any(np.diff(rows[:, 3]) < 0) or
            np.any(rows[:, 4] < 0) or np.any(rows[:, 4] > np.finfo(np.float32).max)):
        raise ValueError('Raw audit requires finite ordered geometry and float32-representable radii')


def verify():
    # Import current medical verification only after the candidate is complete.
    manifest_path = ROOT/'release/manifest.json'
    if not manifest_path.exists():
        raise RuntimeError('Audit candidate has no verified routed release; PL access refused')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if (manifest.get('schema') != 'kv260.route_audit.dfx.v1' or not manifest.get('offline_verified') or
            manifest.get('static_manifest_sha256') != STATIC_MANIFEST or manifest.get('identity') != 196 or
            manifest.get('protocol') != 3 or manifest.get('dma_output_words') != 8706):
        raise RuntimeError('Audit candidate is not compatible with frozen medical static')
    if sha(MEDICAL/'release/manifest.json') != STATIC_MANIFEST:
        raise RuntimeError('Medical static release changed')
    if sha(ROOT.parent/'surface/release/manifest.json') != SURFACE_MANIFEST:
        raise RuntimeError('Tested surface release changed')
    if manifest.get('surface_manifest_sha256') != SURFACE_MANIFEST or sha(MEDICAL/'release/extensions.json') != manifest.get('medical_extensions_sha256'):
        raise RuntimeError('Candidate dependency manifest mismatch')
    import sys
    sys.path.insert(0, str(MEDICAL))
    from runtime_extended import verify_extensions
    verify_extensions()
    for file, digest in manifest['files'].items():
        path = (ROOT/'release'/file).resolve()
        if path.parent != (ROOT/'release').resolve() or sha(path) != digest:
            raise RuntimeError('Audit release checksum mismatch: '+file)
    for file, digest in manifest['source_sha256'].items():
        path = (ROOT/file).resolve()
        if not path.is_relative_to(ROOT.resolve()) or sha(path) != digest:
            raise RuntimeError('Audit source checksum mismatch: '+file)
    partial = 'medical_route_audit_fast_partial.bin'
    if sha(Path('/lib/firmware')/partial) != manifest['files'][partial]:
        raise RuntimeError('Installed audit partial mismatch')
    if sha(ROOT/'host/libroute_audit_fast.so') != manifest['host_library_sha256']:
        raise RuntimeError('Audit host library mismatch')
    return manifest


class AuditSession:
    def __init__(self):
        self.handle = None
        self.lock = threading.RLock()

    def __enter__(self):
        verify()
        self.previous_cwd = Path.cwd()
        os.chdir(MEDICAL)
        L = self.lib = ctypes.CDLL(str(ROOT/'host/libroute_audit_fast.so'))
        L.medical_error.restype = ctypes.c_char_p
        L.medical_open.restype = ctypes.c_void_p
        L.medical_close.argtypes = [ctypes.c_void_p]
        L.medical_select.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        L.medical_switches.argtypes = [ctypes.c_void_p]
        L.medical_switches.restype = ctypes.c_uint
        L.medical_session_report.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        L.medical_route.argtypes = [ctypes.c_void_p]*3 + [ctypes.c_uint]*2 + [ctypes.POINTER(ctypes.c_double)]*2 + [ctypes.POINTER(ctypes.c_uint)]
        self.handle = L.medical_open()
        if not self.handle:
            os.chdir(self.previous_cwd)
            raise RuntimeError(L.medical_error().decode())
        return self

    def check(self, code):
        if code:
            raise RuntimeError(self.lib.medical_error().decode())

    def run_route(self, data, operation):
        if data.dtype != np.uint64 or data.ndim != 2 or data.shape[1] != 8 or not data.flags.c_contiguous or not 1 <= len(data) <= 131072 or operation not in (0, 1, 2):
            raise ValueError('Invalid audit AXIS input')
        if operation == 2:
            validate_diagnostic(data)
        with self.lock:
            output = np.empty((8706, 8), np.uint64)
            hardware, host, reloaded = ctypes.c_double(), ctypes.c_double(), ctypes.c_uint()
            self.check(self.lib.medical_route(self.handle, data.ctypes.data, output.ctypes.data, len(data), operation,
                                              ctypes.byref(hardware), ctypes.byref(host), ctypes.byref(reloaded)))
            return output, dict(status=0, hardware_seconds=hardware.value, host_run_seconds=host.value,
                                kind='actual_kv260', dfx=True, scene_reloaded=bool(reloaded.value), dma_output_words=8706)

    def select(self, name):
        with self.lock:
            self.check(self.lib.medical_select(self.handle, name.encode()))

    def report(self, path):
        self.check(self.lib.medical_session_report(self.handle, str(Path(path).resolve()).encode()))

    def close(self):
        if self.handle:
            self.lib.medical_close(self.handle)
            self.handle = None
            os.chdir(self.previous_cwd)

    def __exit__(self, *exception):
        self.close()
