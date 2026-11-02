"""Owner-thread D9 PL session; complete BO and DFX lifetimes, no PS fallback."""
from pathlib import Path
import ctypes as C
import os
from threading import get_ident
import time

import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[5]
POINT=np.dtype('<f4')
EDGE=np.dtype([('index','<u4'),('weight','<f4')])
U32=np.dtype('<u4')


def _array(value,dtype,size,writable=False):
    if (not isinstance(value,np.ndarray) or value.dtype!=dtype or value.size!=size or
            not value.flags.c_contiguous or (writable and not value.flags.writeable)):
        raise ValueError('D9 requires exact contiguous input/output dtype, size and writeability')


class Session:
    def __init__(self):
        self.handle=None
        self.owner=None
        self.restored=False
        self.last_metrics=None

    def _owner(self):
        if not self.handle or self.owner!=get_ident():
            raise RuntimeError('D9 operation requires its open background owner')

    def __enter__(self):
        if self.handle:
            raise RuntimeError('D9 session already open')
        if not (HERE/'release_r1/manifest.json').is_file():
            raise RuntimeError('D9 qualified release missing; no hardware access')
        from .seal_release import verify
        manifest=verify(installed=True)
        self.manifest=manifest
        self.owner=get_ident()
        self.lib=lib=C.CDLL(str(HERE/'build_ARM_r1/libD9_XRT.so'))
        lib.D9_error.restype=C.c_char_p
        lib.D9_open_root.argtypes=[C.c_char_p];lib.D9_open_root.restype=C.c_void_p
        lib.D9_run.argtypes=[C.c_void_p]*12+[C.c_uint32]*3+[C.c_float,C.c_uint32,C.c_bool,C.POINTER(C.c_double),C.POINTER(C.c_uint64)]
        lib.D9_run.restype=C.c_int
        for name in ('D9_restore','D9_close'):
            function=getattr(lib,name);function.argtypes=[C.c_void_p];function.restype=C.c_int
        self.handle=lib.D9_open_root(os.fsencode(ROOT))
        if not self.handle:
            raise RuntimeError(lib.D9_error().decode())
        return self

    def _run(self,inputs,outputs,report,nv,nf,nnz,limit,iterations,all_work):
        self._owner()
        if (any(isinstance(v,bool) or not isinstance(v,(int,np.integer)) for v in (nv,nf,nnz,iterations)) or
            not 1<=nv<=1_000_000 or not 0<=nf<=2_000_000 or not 0<=nnz<=12_000_000 or
            not 1<=iterations<=16 or not np.isfinite(limit) or limit<=0):
            raise ValueError('Invalid D9 medical configuration')
        if len(inputs)!=5 or len(outputs)!=5:
            raise ValueError('D9 requires five input slots and five work-bank slots')
        sizes=[nv*4,nv+1,nnz,nv,nf*4]
        for value,dtype,size in zip(inputs,(POINT,U32,EDGE,U32,U32),sizes):
            _array(value,dtype,size)
        for index,value in enumerate(outputs):
            if index==0 or all_work:
                _array(value,POINT,nv*4,True)
            elif value is not None:
                raise ValueError('Use run_full for all five explicit work buffers')
        _array(report,U32,16,True)
        all_arrays=list(inputs)+[v for v in outputs if v is not None]+[report]
        for i,first in enumerate(all_arrays):
            for second in all_arrays[i+1:]:
                if np.shares_memory(first,second):
                    raise ValueError('D9 input/work/report buffers must not overlap')
        phases=(C.c_double*12)();counters=(C.c_uint64*8)()
        self.restored=False
        started=time.perf_counter()
        code=self.lib.D9_run(self.handle,*[v.ctypes.data for v in inputs],
            *[v.ctypes.data if v is not None else None for v in outputs],report.ctypes.data,
            int(nv),int(nf),int(nnz),float(limit),int(iterations),bool(all_work),phases,counters)
        if code:
            raise RuntimeError(self.lib.D9_error().decode())
        names=['validation','BO_capacity_growth','copy_and_guards','input_sync','partial_load','complete_switch',
               'hardware_and_header_service','readback_and_all24_guard_checks','output_copy','native_total',
               'graph_single_upload','control']
        result=dict(phases=dict(zip(names,map(float,phases))),
            graph_requests=int(counters[0]),graph_beats=int(counters[1]),graph_DMA_bytes=int(counters[2]),
            stream_errors=int(counters[3]),allocations=int(counters[4]),reuses=int(counters[5]),
            pool_capacity_bytes=int(counters[6]),session_partial_switches=int(counters[7]),
            Python_call_seconds=time.perf_counter()-started,
            all_five_work_banks_read_back=bool(all_work),algorithm_backend='DFX_PL_D9_AXIS512')
        self.last_metrics=result
        return result

    def run(self,inputs,output,report,nv,nf,nnz,limit,iterations):
        return self._run(inputs,[output,None,None,None,None],report,nv,nf,nnz,limit,iterations,False)

    def run_full(self,inputs,outputs,report,nv,nf,nnz,limit,iterations):
        return self._run(inputs,outputs,report,nv,nf,nnz,limit,iterations,True)

    def restore(self):
        self._owner()
        if not self.restored:
            if self.lib.D9_restore(self.handle):
                raise RuntimeError(self.lib.D9_error().decode())
            self.restored=True

    def __exit__(self,*exception):
        self._owner()
        try:
            self.restore()
        finally:
            # An active DMA failure is retained forever in C++; it cannot reach
            # this close. A refused close also preserves the opaque handle.
            if self.lib.D9_close(self.handle):
                raise RuntimeError(self.lib.D9_error().decode())
            self.handle=None
