"""Fail closed until source-bound routing, PR, host and installed partial agree."""
from pathlib import Path
import ctypes,hashlib,json,os,sys,threading,time
import numpy as np
ROOT=Path(__file__).resolve().parent;SYSTEM=ROOT.parents[1]
sys.path.insert(0,str(ROOT.parent/'route_audit_speed'))
from audit_runtime import verify as verify_original
STATIC='ec51ff6cdf8077005a96c228f61e2d8ab2daa4f0c66f37865bd719c2f1eeefbc'
COMPOSITE='a3e9e7f17e0e3ba46895da9938253faed8211b9cbecefdd6b0c7977614324f2a'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def verify(experimental):
    path=ROOT/'release/manifest.json'
    if not path.is_file():raise RuntimeError('Volume candidate has no verified routed release; no PL access')
    m=json.loads(path.read_text())
    if m.get('schema')!='kv260.edt_volume.dfx.v1' or not m.get('offline_verified') or m.get('identity')!=0xc8:
        raise RuntimeError('Unsupported volume release; no PL access')
    if not experimental:
        accepted=ROOT/'docs/board_acceptance.json'
        receipt=json.loads(accepted.read_text()) if accepted.is_file() else {}
        if receipt.get('status')!='accepted_stronger_than_optimized_PS' or receipt.get('release_manifest_sha256')!=sha(path):
            raise RuntimeError('C8 is not production accepted; use explicit experimental test only')
    verify_original()
    if sha(ROOT.parent/'medical/release/manifest.json')!=STATIC or sha(ROOT.parent/'composite/release/manifest.json')!=COMPOSITE:
        raise RuntimeError('Original medical/composite release changed')
    composite=ROOT.parent/'composite/release';cm=json.loads((composite/'manifest.json').read_text())
    expected=cm['files']['medical_composite_partial.bin']
    if sha(composite/'medical_composite_partial.bin')!=expected or sha(Path('/lib/firmware/medical_composite_partial.bin'))!=expected:
        raise RuntimeError('Changed installed C7 partial')
    for name,digest in {**m['source_sha256'],**m['artifact_sha256']}.items():
        file=(ROOT/name).resolve()
        if not file.is_relative_to(ROOT) or sha(file)!=digest:raise RuntimeError('Changed C8 artifact '+name)
    if sha(Path('/lib/firmware/medical_edt_volume_partial.bin'))!=m['partial_bin_sha256']:
        raise RuntimeError('Installed C8 partial mismatch')
    proof=json.loads((ROOT/'docs/host_build.json').read_text())
    if proof['status']!='compiled_no_PL_access' or sha(ROOT/'build/libedt_volume.so')!=proof['library_sha256']:
        raise RuntimeError('Changed C8 host library')
    for name,digest in proof['source_sha256'].items():
        file=(ROOT/name).resolve()
        if not file.is_relative_to(ROOT) or sha(file)!=digest:raise RuntimeError('Changed C8 host source')
    return m


def validate(mask,spacing):
    if (not isinstance(mask,np.ndarray) or mask.ndim!=3 or min(mask.shape)<1 or max(mask.shape)>1024 or mask.size>80000000 or
            mask.dtype not in (np.dtype(bool),np.dtype('uint8')) or
            (mask.dtype==np.dtype('uint8') and mask.max()>1)):
        raise ValueError('C8 requires a bounded binary uint8/bool mask')
    spacing=np.asarray(spacing,float)
    if spacing.shape!=(3,) or not np.isfinite(spacing).all() or np.any(spacing<=0) or np.any(spacing>32):
        raise ValueError('Invalid C8 physical spacing')
    weights=np.rint(spacing*spacing*(1<<20)).astype(np.uint64)
    if np.any(weights==0) or mask.all():raise ValueError('C8 requires resolvable spacing and finite background')
    return weights


class VolumeSession:
    def __init__(self,*,experimental=False):self.experimental=experimental;self.handle=None;self.lock=threading.RLock()
    def __enter__(self):
        self.manifest=verify(self.experimental)
        self.previous=Path.cwd();os.chdir(ROOT.parent/'medical')
        try:self._open()
        except BaseException:os.chdir(self.previous);raise
        return self
    def _open(self):
        L=self.lib=ctypes.CDLL(str(ROOT/'build/libedt_volume.so'))
        L.volume_error.restype=ctypes.c_char_p;L.volume_open.restype=ctypes.c_void_p
        L.volume_close.argtypes=[ctypes.c_void_p];L.volume_return_to_scope.argtypes=[ctypes.c_void_p]
        L.volume_run.argtypes=[ctypes.c_void_p]*4+[ctypes.c_uint]*6+[ctypes.POINTER(ctypes.c_double)]*2
        L.volume_phase.argtypes=[ctypes.c_void_p,ctypes.c_uint];L.volume_phase.restype=ctypes.c_double
        self.handle=L.volume_open()
        if not self.handle:raise RuntimeError(L.volume_error().decode())
    def check(self,rc):
        if rc:raise RuntimeError(self.lib.volume_error().decode())
    def distance(self,mask,spacing,*,debug_squared=False):
        start=time.perf_counter();weights=validate(mask,spacing)
        # bool is already a binary byte mask; do not materialize two comparisons
        # and another cast for every volume. The PL interprets nonzero as true.
        source=np.ascontiguousarray(mask).view(np.uint8)
        result=np.empty(mask.shape,np.float32);squared=np.empty(mask.shape,np.uint64) if debug_squared else None
        preparation=time.perf_counter()-start
        hw,host=ctypes.c_double(),ctypes.c_double()
        with self.lock:
            if not self.handle:raise RuntimeError('C8 session is closed')
            self.check(self.lib.volume_run(self.handle,source.ctypes.data,result.ctypes.data,0 if squared is None else squared.ctypes.data,
                *mask.shape,*map(int,weights),ctypes.byref(hw),ctypes.byref(host)))
            phases={name:self.lib.volume_phase(self.handle,i) for i,name in enumerate(['input_copy_and_guards','input_sync','hardware_three_axes','readback_and_guard_sync','crop_copy_and_guard_check'])}
        return result,squared,dict(backend='PL_C8_volume_candidate',q20_weights=weights.tolist(),hardware_seconds=hw.value,
            host_run_seconds=host.value,total_seconds=time.perf_counter()-start,input_preparation_seconds=preparation,phases=phases,
            four_4096_byte_DMA_guards_passed=True,debug_squared_readback_included=debug_squared,
            production_accepted=not self.experimental)
    def return_to_scope(self):
        with self.lock:self.check(self.lib.volume_return_to_scope(self.handle))
    def close(self):
        with self.lock:
            if self.handle:self.lib.volume_close(self.handle);self.handle=None;os.chdir(self.previous)
    def __exit__(self,*args):self.close()
