"""Two bounded HU AXIS submissions; no PS quantization or PS fallback here."""
from dataclasses import dataclass
from pathlib import Path
import ctypes
import hashlib
import json
import os
import threading
import time
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
MODULE=HERE.parent
RELEASE=MODULE/'dfx_r1/release_r1'
LIBRARY=HERE/'native_ARM_r2/libhu_dfx.so'
MAX_REQUEST=1<<23
PHASES=['argument_seconds','prepare_copy_seconds','to_device_sync_seconds','select_seconds',
        'register_seconds','observed_in_flight_seconds','from_device_sync_seconds',
        'validation_copy_seconds','request_to_completion_seconds','partial_load_seconds',
        'switch_seconds','prepared_to_launch_seconds']


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(4*1024**2),b''):h.update(block)
    return h.hexdigest()


def verify_release(experimental=False):
    if type(experimental) is not bool:raise TypeError('experimental must be bool')
    manifest=RELEASE/'manifest.json'
    if not manifest.is_file():raise RuntimeError('D6 firmware is not offline-qualified; no hardware access')
    value=json.loads(manifest.read_text())
    if (value['schema']!='kv260.HU_D6.offline.v1' or not value['full_PR_passed'] or
            value['clock_MHz']!=100 or value['identity']!=0xd6):raise RuntimeError('Invalid D6 release')
    for name,digest in value['runtime_files_SHA256'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts or ':' in name:raise RuntimeError('Invalid release path')
        path=ROOT/relative
        if not path.is_file() or sha(path)!=digest:raise RuntimeError('Changed D6 dependency: '+name)
    bit=RELEASE/'medical_hu_D6_32_r2_partial.bin'
    if sha(Path('/lib/firmware')/bit.name)!=sha(bit):raise RuntimeError('Installed D6 partial mismatch')
    if not experimental:
        qualification=MODULE/'board_qualification.json'
        if not qualification.is_file():raise RuntimeError('D6 has not passed actual board qualification; no PS fallback')
        proof=json.loads(qualification.read_text())
        if not proof['actual_correctness_passed'] or proof['release_manifest_SHA256']!=sha(manifest):
            raise RuntimeError('D6 board qualification does not match this release')
    return value


def validate_arrays(image,table,output=None):
    if not isinstance(image,np.ndarray) or image.dtype!=np.int16 or not image.flags.c_contiguous:
        raise ValueError('Contiguous signed int16 HU input required')
    if image.size>MAX_REQUEST:raise ValueError('Split HU input into bounded requests of at most 8388608 voxels')
    if not isinstance(table,np.ndarray) or table.dtype!=np.int8 or table.shape!=(1401,) or not table.flags.c_contiguous:
        raise ValueError('Contiguous int8 model LUT with 1401 entries required')
    if output is not None:
        if (not isinstance(output,np.ndarray) or output.dtype!=np.int8 or output.shape!=image.shape or
                not output.flags.c_contiguous or not output.flags.writeable):raise ValueError('Writable contiguous int8 output of the same shape required')
        left,right=output.ctypes.data,output.ctypes.data+output.nbytes
        for source in [image,table]:
            start,end=source.ctypes.data,source.ctypes.data+source.nbytes
            if left<end and start<right:raise ValueError('HU output overlaps its input/model LUT')


@dataclass
class Request:
    image:np.ndarray
    table:np.ndarray
    output:np.ndarray
    status:np.ndarray
    phases:object


class Session:
    submit_is_nonblocking=True
    maximum_outstanding=2
    in_flight_interval_is_host_observed_not_hardware_cycles=True
    def __init__(self,*,experimental=False):
        if type(experimental) is not bool:raise TypeError('experimental must be bool')
        self.experimental=experimental;self.handle=None;self.lib=None
        self.owner=(os.getpid(),threading.get_ident());self.pending={};self.orphans=[];self.failed=False
    def _owner(self,opened=True):
        if self.owner!=(os.getpid(),threading.get_ident()):raise RuntimeError('HU session belongs to another process/thread')
        if opened and not self.handle:raise RuntimeError('HU session is not open')
    def __enter__(self):
        self._owner(False)
        if self.handle:raise RuntimeError('HU session already open')
        started=time.perf_counter();verify_release(self.experimental);verified=time.perf_counter()
        L=self.lib=ctypes.CDLL(str(LIBRARY));p=ctypes.c_void_p
        L.hu_error.restype=ctypes.c_char_p;L.hu_open_root.argtypes=[ctypes.c_char_p];L.hu_open_root.restype=p
        L.hu_submit.argtypes=[p,p,ctypes.c_uint32,p,p,p,p];L.hu_submit.restype=ctypes.c_uint64
        L.hu_collect.argtypes=[p,ctypes.c_uint64];L.hu_collect.restype=ctypes.c_int
        L.hu_close.argtypes=[ctypes.POINTER(p)];L.hu_close.restype=ctypes.c_int
        self.handle=L.hu_open_root(os.fsencode(ROOT))
        if not self.handle:raise RuntimeError(L.hu_error().decode())
        self.open_metrics=dict(verification_seconds=verified-started,native_open_seconds=time.perf_counter()-verified,
                               full_open_seconds=time.perf_counter()-started)
        return self
    def submit(self,image,table,output=None):
        self._owner();validate_arrays(image,table,output)
        if self.failed:raise RuntimeError('Close the failed HU session before submitting again')
        if len(self.pending)>=2:raise RuntimeError('Collect one of the two outstanding HU requests')
        if output is None:output=np.empty(image.shape,np.int8)
        request=Request(image,table,output,np.empty(8,np.uint32),(ctypes.c_double*12)())
        ticket=int(self.lib.hu_submit(self.handle,image.ctypes.data,image.size,table.ctypes.data,
            output.ctypes.data,request.status.ctypes.data,request.phases))
        if not ticket:raise RuntimeError(self.lib.hu_error().decode())
        if ticket in self.pending:
            self.orphans.append(request);self.failed=True;raise RuntimeError('Native HU ticket reused; retain arrays until drained close')
        self.pending[ticket]=request;return ticket
    def collect(self,ticket):
        self._owner()
        if (isinstance(ticket,(bool,np.bool_)) or not isinstance(ticket,(int,np.integer)) or
                not 1<=int(ticket)<=0xffffffffffffffff or int(ticket) not in self.pending):raise ValueError('Unknown HU ticket')
        ticket=int(ticket)
        if self.lib.hu_collect(self.handle,ticket):
            self.failed=True;raise RuntimeError(self.lib.hu_error().decode())
        request=self.pending.pop(ticket)
        return request.output,dict(zip(PHASES,map(float,request.phases)))
    def close(self):
        self._owner(False)
        if not self.handle:return
        pointer=ctypes.c_void_p(self.handle);rc=self.lib.hu_close(ctypes.byref(pointer));self.handle=pointer.value
        if not self.handle:self.pending.clear();self.orphans.clear()
        if rc:raise RuntimeError(self.lib.hu_error().decode())
    def __exit__(self,*exc):self.close()


def quantize_volume(session,image,table,*,chunk_voxels=1<<20):
    """One DFX selection for a complete volume; two chunks occupy bounded BOs."""
    if type(chunk_voxels) is not int or not 1<=chunk_voxels<=MAX_REQUEST:raise ValueError('Invalid HU chunk size')
    if not isinstance(image,np.ndarray) or image.dtype!=np.int16 or not image.flags.c_contiguous:
        raise ValueError('Contiguous int16 volume required')
    flat=image.reshape(-1);output=np.empty(image.shape,np.int8);target=output.reshape(-1)
    pending=[];metrics=[];started=time.perf_counter()
    for start in range(0,len(flat),chunk_voxels):
        end=min(start+chunk_voxels,len(flat))
        ticket=session.submit(flat[start:end],table,output=target[start:end]);pending.append(ticket)
        if len(pending)==2:
            _,timing=session.collect(pending.pop(0));metrics.append(timing)
    for ticket in pending:
        _,timing=session.collect(ticket);metrics.append(timing)
    return output,dict(stream_wall_seconds=time.perf_counter()-started,chunks=len(metrics),
        chunk_voxels=chunk_voxels,per_chunk=metrics,backend='actual_DFX_PL_HU_AXIS_D6',
        no_per_chunk_DFX_switch=True,PS_quantization_used=False)
