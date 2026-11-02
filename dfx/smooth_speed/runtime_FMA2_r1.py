"""Owner-thread-only compact C2 backend, gated on a real sealed full PR.

Use SmoothClient(Session); it returns Futures while this owner performs XRT
work. No process cwd mutation, PS fallback or automatic UI startup occurs.
"""
from pathlib import Path
import ctypes as C
import hashlib
import os
import sys
from threading import get_ident
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PARTIAL='medical_smooth_speed_FMA2_r1_partial.bin'


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda:stream.read(1048576),b''):
            h.update(b)
    return h.hexdigest()


def verify():
    sys.path.insert(0,str(ROOT/'tools'))
    from seal_FMA2_smoothing_release_r1 import verify_release
    manifest=verify_release()
    if sha(Path('/lib/firmware')/PARTIAL)!=manifest['partial_bin_sha256']:
        raise RuntimeError('Matching compact C2 firmware identity required; no XRT access')
    return manifest


class Session:
    def __init__(self,profile=False):
        self.profile_enabled=bool(profile)
        self.handle=None
        self.owner=None
        self.restored=False

    def _owner(self):
        if self.owner!=get_ident() or not self.handle:
            raise RuntimeError('Smoothing operation requires its open background owner')

    def __enter__(self):
        if self.handle:
            raise RuntimeError('Smoothing session already open')
        self.manifest=verify()
        self.owner=get_ident()
        self.lib=L=C.CDLL(str(HERE/'host_FMA2_r1/build_ARM/libsmooth_FMA2_r1.so'))
        L.speed_error.restype=C.c_char_p
        L.speed_open_root.argtypes=[C.c_char_p,C.c_bool]
        L.speed_open_root.restype=C.c_void_p
        L.speed_profile_snapshot.argtypes=[C.c_void_p,C.POINTER(C.c_uint64)]
        L.speed_profile_snapshot.restype=C.c_int
        L.speed_close.argtypes=[C.c_void_p]
        L.speed_restore.argtypes=[C.c_void_p]
        L.speed_run.argtypes=[C.c_void_p]*8+[C.c_uint]*3+[C.c_float,C.c_uint,C.POINTER(C.c_double)]
        L.speed_run.restype=C.c_int
        self.handle=L.speed_open_root(os.fsencode(ROOT),self.profile_enabled)
        if not self.handle:
            raise RuntimeError(L.speed_error().decode())
        return self

    def run(self,inputs,output,report,nv,nf,nnz,limit,iterations):
        self._owner()
        sizes=[nv*4,nv+1,nnz,nv,nf*4]
        dtypes=[np.dtype('<f4'),np.dtype('<u4'),np.dtype([('index','<u4'),('weight','<f4')]),np.dtype('<u4'),np.dtype('<u4')]
        if len(inputs)!=5:
            raise ValueError('Five smoothing arrays required')
        for value,size,dtype in zip(inputs,sizes,dtypes):
            if not isinstance(value,np.ndarray) or value.size!=size or value.dtype!=dtype or not value.flags.c_contiguous:
                raise ValueError('Invalid contiguous smoothing input buffer')
        if output.shape!=(nv,4) or output.dtype!=np.float32 or not output.flags.c_contiguous or not output.flags.writeable:
            raise ValueError('Invalid output points')
        if report.shape!=(16,) or report.dtype!=np.uint32 or not report.flags.c_contiguous or not report.flags.writeable:
            raise ValueError('Invalid output report')
        phases=(C.c_double*12)()
        self.restored=False
        code=self.lib.speed_run(self.handle,*[v.ctypes.data for v in inputs],output.ctypes.data,report.ctypes.data,nv,nf,nnz,limit,iterations,phases)
        if code:
            raise RuntimeError(self.lib.speed_error().decode())
        names=['validation','BO_capacity_growth','copy_and_red_zone_setup','input_and_guard_sync','partial_load','complete_switch','hardware','readback_and_all_red_zone_checks','output_copy','native_host_total']
        return {name:phases[i] for i,name in enumerate(names)}

    def profile_snapshot(self):
        self._owner()
        if not self.profile_enabled:
            raise RuntimeError('Diagnostic snapshots require an explicit profile session')
        values=(C.c_uint64*16)()
        if self.lib.speed_profile_snapshot(self.handle,values):
            raise RuntimeError(self.lib.speed_error().decode())
        names=['observation_cycles','read_bursts','read_beats','read_requested_bytes','read_address_backpressure_cycles','read_response_gap_cycles','read_data_backpressure_cycles','write_bursts','write_beats','write_enabled_bytes','write_address_backpressure_cycles','write_data_backpressure_cycles','write_response_backpressure_cycles','response_errors','maximum_pending_reads','maximum_pending_writes']
        result=dict(zip(names,map(int,values)))
        assert result['observation_cycles']>0 and result['read_bursts']>0 and result['write_bursts']>0 and result['response_errors']==0
        return result

    def restore(self):
        self._owner()
        if not self.restored:
            if self.lib.speed_restore(self.handle):
                raise RuntimeError(self.lib.speed_error().decode())
            self.restored=True

    def __exit__(self,*error):
        self._owner()
        # Native execute/echo retains active DMA forever on a timeout; these
        # calls are only reachable once accepted work has actually returned.
        try:
            self.restore()
        finally:
            self.lib.speed_close(self.handle)
            self.handle=None
