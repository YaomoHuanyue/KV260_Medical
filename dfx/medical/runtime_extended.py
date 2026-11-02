"""One static XRT session for all medical RMs, with no whole-bit fallback."""
from pathlib import Path
import ctypes,hashlib,json,os,threading
import numpy as np
ROOT=Path(__file__).resolve().parent
SYSTEM=ROOT.parents[1]
def verify_extensions():
    from runtime import verify_release
    verify_release();r=ROOT/'release';m=json.loads((r/'extensions.json').read_text())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if not m['offline_verified'] or sha(r/'manifest.json')!=m['base_manifest_sha256']:raise RuntimeError('Extension/base mismatch')
    for n,h in m['files'].items():
        if sha(r/n)!=h:raise RuntimeError('Extension release mismatch: '+n)
    for v in ('ct','edt','route'):
        n=f'medical_{v}_partial.bin'
        if sha(Path('/lib/firmware')/n)!=m['files'][n]:raise RuntimeError('Installed extension mismatch: '+v)

class Session:
    def __init__(self):self.handle=None;self.lock=threading.RLock();self.edt_compute_lanes=4
    def __enter__(self):
        verify_extensions();os.chdir(ROOT)
        self.lib=L=ctypes.CDLL(str(ROOT/'host_extended/libmedical_dfx.so'))
        L.medical_error.restype=ctypes.c_char_p
        L.medical_open.restype=ctypes.c_void_p
        L.medical_close.argtypes=[ctypes.c_void_p]
        L.medical_select.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
        L.medical_echo.argtypes=[ctypes.c_void_p]
        L.medical_switches.argtypes=[ctypes.c_void_p];L.medical_switches.restype=ctypes.c_uint
        L.medical_session_report.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
        L.medical_reconstruction_job.argtypes=[ctypes.c_void_p,*([ctypes.c_char_p]*4)]
        L.medical_edt.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,*([ctypes.c_uint]*4),*([ctypes.POINTER(ctypes.c_double)]*2)]
        L.medical_route.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,*([ctypes.POINTER(ctypes.c_double)]*2),ctypes.POINTER(ctypes.c_uint)]
        for n in ('nav_pack','nav_unpack'):
            getattr(L,n).argtypes=[ctypes.c_void_p,ctypes.c_void_p,*([ctypes.c_uint]*4)];getattr(L,n).restype=None
        self.handle=L.medical_open()
        if not self.handle:raise RuntimeError(L.medical_error().decode())
        return self
    def check(self,rc):
        if rc:raise RuntimeError(self.lib.medical_error().decode())
    def select(self,name):
        with self.lock:self.check(self.lib.medical_select(self.handle,name.encode()))
    def echo(self):
        with self.lock:self.check(self.lib.medical_echo(self.handle))
    @property
    def switches(self):return self.lib.medical_switches(self.handle)
    def report(self,path):self.check(self.lib.medical_session_report(self.handle,str(Path(path).resolve()).encode()))
    def run(self,*args):
        with self.lock:
            if len(args)==4 and isinstance(args[0],str):
                op,folder,output,report=args
                self.check(self.lib.medical_reconstruction_job(self.handle,op.encode(),str(Path(folder).resolve()).encode(),str(Path(output).resolve()).encode(),str(Path(report).resolve()).encode()))
                return json.loads(Path(report).read_text())
            source,destination,length,groups,weight,mode=args
            from pl.runtime import _validate_job
            _validate_job(source,destination,length,groups,weight,mode)
            hw=ctypes.c_double();host=ctypes.c_double()
            self.check(self.lib.medical_edt(self.handle,source.ctypes.data,destination.ctypes.data,length,groups,weight,mode,ctypes.byref(hw),ctypes.byref(host)))
            return dict(hardware_seconds=hw.value,host_run_seconds=host.value,backend='dfx_pl_edt')
    def run_route(self,data,operation):
        if data.dtype!=np.uint64 or data.ndim!=2 or data.shape[1]!=8 or not data.flags.c_contiguous or len(data)<1:raise ValueError('Invalid AXIS route input')
        with self.lock:
            output=np.empty((8706,8),np.uint64);hw=ctypes.c_double();host=ctypes.c_double();reloaded=ctypes.c_uint()
            self.check(self.lib.medical_route(self.handle,data.ctypes.data,output.ctypes.data,len(data),operation,ctypes.byref(hw),ctypes.byref(host),ctypes.byref(reloaded)))
            return output,dict(status=0,hardware_seconds=hw.value,host_run_seconds=host.value,kind='actual_kv260',dfx=True,scene_reloaded=bool(reloaded.value),dma_output_words=8706)
    def pack(self,volume,axis):
        from pl.runtime import Packing
        return Packing.pack(self,volume,axis)
    def unpack(self,packed,layout):
        from pl.runtime import Packing
        return Packing.unpack(self,packed,layout)
    def close(self):
        if self.handle:self.lib.medical_close(self.handle);self.handle=None
    def __exit__(self,*exc):self.close()

def ct_backend(output_pool=False):
    from ct_pl.runtime import XRTInteger
    b=XRTInteger(ROOT/'host_extended/libmedical_dfx.so',ROOT/'release/dfx_medical.xclbin',pl_quantization=True,output_pool=output_pool)
    b.pointwise_streaming=True;b.spatial_streaming=True;b.pl_activation_lut=True
    return b
