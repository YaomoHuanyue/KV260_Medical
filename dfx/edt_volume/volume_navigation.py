"""Whole-volume EDT and accepted audited routing in one checked XRT context."""
from pathlib import Path
import ctypes,json
import numpy as np
from volume_runtime import VolumeSession
from audit_runtime import validate_diagnostic

class VolumeNavigationSession(VolumeSession):
    def __init__(self,*,experimental=False):
        super().__init__(experimental=experimental);self.audit_handle=None
    def __enter__(self):
        super().__enter__()
        try:
            L=self.lib;L.medical_error.restype=ctypes.c_char_p;L.medical_open.restype=ctypes.c_void_p
            L.medical_close.argtypes=[ctypes.c_void_p]
            L.medical_select.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
            L.medical_session_report.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
            L.medical_route.argtypes=[ctypes.c_void_p]*3+[ctypes.c_uint]*2+[ctypes.POINTER(ctypes.c_double)]*2+[ctypes.POINTER(ctypes.c_uint)]
            L.volume_same_context.argtypes=[ctypes.c_void_p]*2
            self.audit_handle=L.medical_open()
            if not self.audit_handle:raise RuntimeError(L.medical_error().decode())
            if L.volume_same_context(self.handle,self.audit_handle)!=1:raise RuntimeError('EDT and audit do not share one XRT context')
            return self
        except BaseException:
            self.close();raise
    def _audit_check(self,rc):
        if rc:raise RuntimeError(self.lib.medical_error().decode())
    def distance_transform(self,mask,spacing):
        field,_,stats=self.distance(mask,spacing)
        stats['backend']='pl_C8_volume';stats['shared_EDT_route_XRT_context']=True
        return field,stats
    def run_route(self,data,operation):
        if (not isinstance(data,np.ndarray) or data.dtype!=np.uint64 or data.ndim!=2 or data.shape[1]!=8 or
                not data.flags.c_contiguous or not 1<=len(data)<=131072 or operation not in (0,1,2)):
            raise ValueError('Invalid audit AXIS input')
        if operation==2:validate_diagnostic(data)
        with self.lock:
            if not self.handle or not self.audit_handle:raise RuntimeError('Volume navigation session is closed')
            result=np.empty((8706,8),np.uint64);hw,host,reloaded=ctypes.c_double(),ctypes.c_double(),ctypes.c_uint()
            self._audit_check(self.lib.medical_route(self.audit_handle,data.ctypes.data,result.ctypes.data,len(data),operation,
                ctypes.byref(hw),ctypes.byref(host),ctypes.byref(reloaded)))
            return result,dict(status=0,hardware_seconds=hw.value,host_run_seconds=host.value,kind='actual_kv260',dfx=True,
                scene_reloaded=bool(reloaded.value),dma_output_words=8706,shared_EDT_route_XRT_context=True)
    def select(self,name):
        with self.lock:
            if not self.audit_handle:raise RuntimeError('Volume navigation session is closed')
            self._audit_check(self.lib.medical_select(self.audit_handle,name.encode()))
    def report(self,path):
        with self.lock:
            if not self.audit_handle:raise RuntimeError('Volume navigation session is closed')
            path=Path(path).resolve()
            self._audit_check(self.lib.medical_session_report(self.audit_handle,str(path).encode()))
            report=json.loads(path.read_text());report['shared_EDT_route_context_pointer_match']=True
            report['EDT_core']='C8_volume';report['route_core']='accepted_R14'
            path.write_text(json.dumps(report,indent=2)+'\n')
    def close(self):
        with self.lock:
            if self.audit_handle:self.lib.medical_close(self.audit_handle);self.audit_handle=None
            super().close()
