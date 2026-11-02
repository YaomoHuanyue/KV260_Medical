from pathlib import Path
import ctypes,hashlib,json,os
import numpy as np
ROOT=Path(__file__).resolve().parent
def verify():
    m=json.loads((ROOT/'release/manifest.json').read_text())
    if m['schema']!='kv260.surface.dfx.v1' or not m['offline_verified']:raise RuntimeError('Surface offline verification missing')
    for name,key in [('manifest.json','static_manifest_sha256'),('extensions.json','medical_extensions_sha256')]:
        if hashlib.sha256((ROOT.parent/'medical/release'/name).read_bytes()).hexdigest()!=m[key]:raise RuntimeError('Medical release changed: '+name)
    for name,h in m['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=h:raise RuntimeError('Changed scope release: '+name)
    expected=m['files']['release/medical_surface_partial.bin']
    if hashlib.sha256(Path('/lib/firmware/medical_surface_partial.bin').read_bytes()).hexdigest()!=expected:raise RuntimeError('Scope firmware mismatch')
class Session:
    def __init__(self):self.handle=None
    def __enter__(self):
        verify();os.chdir(ROOT.parent/'medical');(ROOT/'results').mkdir(exist_ok=True)
        self.lib=L=ctypes.CDLL(str(ROOT/'host/libscope.so'))
        L.scope_error.restype=ctypes.c_char_p;L.scope_open.restype=ctypes.c_void_p;L.scope_close.argtypes=[ctypes.c_void_p]
        L.scope_transfer.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_uint,ctypes.POINTER(ctypes.c_double),ctypes.POINTER(ctypes.c_double)]
        self.handle=L.scope_open()
        if not self.handle:raise RuntimeError(L.scope_error().decode())
        return self
    def transfer(self,source,operation,out_words):
        src=np.frombuffer(source,dtype=np.uint8) if isinstance(source,bytes) else np.ascontiguousarray(source).view(np.uint8)
        if src.nbytes%64:raise ValueError('AXIS packet alignment')
        out=np.empty(out_words*16,np.uint32);hw=ctypes.c_double();total=ctypes.c_double()
        rc=self.lib.scope_transfer(self.handle,src.ctypes.data,out.ctypes.data,src.nbytes//64,out_words,operation,ctypes.byref(hw),ctypes.byref(total))
        if rc:raise RuntimeError(self.lib.scope_error().decode())
        return out,dict(hardware_seconds=hw.value,host_seconds=total.value)
    def __exit__(self,*exc):
        if self.handle:self.lib.scope_close(self.handle);self.handle=None
