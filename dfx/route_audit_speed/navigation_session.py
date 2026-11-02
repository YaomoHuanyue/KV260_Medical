"""Candidate EDT and audited routing in one gated static XRT session."""
from pathlib import Path
import ctypes,hashlib,json,sys
from audit_runtime import AuditSession, MEDICAL

SYSTEM=MEDICAL.parents[1]
PACKING_LIBRARY_SHA256='ca5d4df2c4d4d3a83588afed4b8ddd0f4807b3c2a09fe993ba5fe5a921d0c9c4'
sys.path.insert(0,str(SYSTEM/'modules/navigation'))
from pl.runtime import XRTSession,Packing,_validate_job


class NavigationSession(AuditSession,XRTSession):
    """Reuse accepted PS packing; EDT and route computation use this session."""
    def __init__(self):
        AuditSession.__init__(self)
        self.edt_compute_lanes=4

    def __enter__(self):
        accepted=json.loads((MEDICAL/'release/extensions_acceptance.json').read_text())
        path=MEDICAL/'host_extended/libmedical_dfx.so'
        # Reject an unaccepted CPU packing implementation before opening XRT.
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=PACKING_LIBRARY_SHA256 or digest!=accepted['library_sha256'] or accepted.get('status')!='passed':
            raise RuntimeError('Accepted packing library checksum mismatch')
        AuditSession.__enter__(self)
        try:
            # Packing is a CPU function, but still require the exact accepted
            # library whose behavior was used for the previous EDT pipeline.
            self.packing=Packing()
            self.packing.lib=ctypes.CDLL(str(path))
            self.packing.init_packing()
            self.lib.medical_edt.argtypes=[ctypes.c_void_p]*3+[ctypes.c_uint]*4+[ctypes.POINTER(ctypes.c_double)]*2
            return self
        except BaseException:
            self.close()
            raise

    def run(self,source,destination,length,groups,weight,mode):
        _validate_job(source,destination,length,groups,weight,mode)
        with self.lock:
            hardware,host=ctypes.c_double(),ctypes.c_double()
            self.check(self.lib.medical_edt(self.handle,source.ctypes.data,destination.ctypes.data,
                length,groups,weight,mode,ctypes.byref(hardware),ctypes.byref(host)))
            return dict(hardware_seconds=hardware.value,host_run_seconds=host.value,backend='dfx_pl_edt')

    def pack(self,volume,axis):
        return self.packing.pack(volume,axis)

    def unpack(self,packed,layout):
        return self.packing.unpack(packed,layout)
