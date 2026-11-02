"""Eight-row Q20 squared EDT, PS packing, and a task-owned native XRT session."""
import ctypes
import hashlib
import json
from pathlib import Path
import time
import numpy as np

ROOT=Path(__file__).resolve().parent
Q=1<<20
INF=np.uint64(0xffffffffffffffff)


def _digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def available(package=None):
    try:
        fw=Path('/sys/firmware/devicetree/base/fpga-region/firmware-name').read_bytes().split(b'\0')[0]
        package=ROOT/'package' if package is None else Path(package);manifest=json.loads((package/'manifest.json').read_text())
        return (fw==b'kv260_navigation.bit.bin' and (ROOT/'build/libnav_xrt.so').is_file()
            and Path('/run/kv260-navigation-loaded.sha256').read_text().strip()==manifest['bit_bin_sha256']
            and _digest(package/'kv260_navigation.xclbin')==manifest['xclbin_sha256'])
    except (OSError,ValueError,KeyError):return False


def pack_lines(volume,axis):
    moved=np.moveaxis(volume,axis,-1);length=moved.shape[-1]
    lines=int(np.prod(moved.shape[:-1]));groups=(lines+7)//8
    padded=np.zeros((groups*8,length),dtype=np.uint64)
    padded[:lines]=moved.reshape(lines,length)
    packed=np.ascontiguousarray(padded.reshape(groups,8,length).transpose(0,2,1))
    return packed,(moved.shape,axis,lines)


def unpack_lines(packed,layout):
    shape,axis,lines=layout
    restored=packed.transpose(0,2,1).reshape(-1,shape[-1])[:lines].reshape(shape)
    return np.ascontiguousarray(np.moveaxis(restored,-1,axis))


class Packing:
    def init_packing(self):
        for name in ('nav_pack','nav_unpack'):
            function=getattr(self.lib,name)
            function.argtypes=[ctypes.c_void_p,ctypes.c_void_p,*([ctypes.c_uint]*4)];function.restype=None

    def pack(self,volume,axis):
        if volume.ndim!=3 or min(volume.shape)<1 or axis not in (0,1,2):raise ValueError('Invalid 3D packing layout')
        volume=np.ascontiguousarray(volume,dtype=np.uint64);length=volume.shape[axis]
        lines=volume.size//length;groups=(lines+7)//8
        packed=np.empty((groups,length,8),dtype=np.uint64)
        self.lib.nav_pack(volume.ctypes.data,packed.ctypes.data,*volume.shape,axis)
        return packed,(volume.shape,axis)

    def unpack(self,packed,layout):
        shape,axis=layout;volume=np.empty(shape,dtype=np.uint64)
        if len(shape)!=3 or min(shape)<1 or axis not in (0,1,2):raise ValueError('Invalid 3D unpacking layout')
        length=shape[axis];groups=(int(np.prod(shape))//length+7)//8
        if packed.shape!=(groups,length,8) or packed.dtype!=np.uint64 or not packed.flags.c_contiguous:
            raise ValueError('Invalid packed buffer')
        self.lib.nav_unpack(packed.ctypes.data,volume.ctypes.data,*shape,axis)
        return volume


class NativeModel(Packing):
    def __init__(self):
        import sys
        filename='nav_model.dll' if sys.platform=='win32' else 'libnav_model.so'
        self.lib=ctypes.CDLL(str(ROOT/'build'/filename))
        self.lib.nav_native_run.argtypes=[ctypes.c_void_p,ctypes.c_void_p,*([ctypes.c_uint]*4)]
        self.lib.nav_native_run.restype=ctypes.c_int
        self.init_packing()

    def run(self,input,output,length,groups,weight,mode):
        _validate_job(input,output,length,groups,weight,mode)
        result=self.lib.nav_native_run(input.ctypes.data,output.ctypes.data,length,groups,weight,mode)
        if result:raise RuntimeError('Native EDT error '+str(result))
        return dict(hardware_seconds=None,host_run_seconds=None)


class XRTSession(Packing):
    def __init__(self,package=None):
        self.package=ROOT/'package' if package is None else Path(package).resolve()
        if not available(self.package):raise RuntimeError('Navigation firmware not loaded or package mismatch; no XRT or MMIO access')
        self.edt_compute_lanes=json.loads((self.package/'manifest.json').read_text()).get('edt_compute_lanes',8)
        import fcntl
        lock=Path('/tmp/kv260-ct-pl.lock')
        if not lock.exists():lock.touch(mode=0o660)
        self.lock=lock.open('rb')
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:self.lock.close();raise
        try:self._open()
        except BaseException:self.lock.close();raise

    def _open(self):
        self.lib=ctypes.CDLL(str(ROOT/'build/libnav_xrt.so'))
        self.init_packing()
        self.lib.nav_open.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_size_t];self.lib.nav_open.restype=ctypes.c_void_p
        self.lib.nav_run.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,*([ctypes.c_uint]*4),
            ctypes.POINTER(ctypes.c_double),ctypes.POINTER(ctypes.c_double),ctypes.c_char_p,ctypes.c_size_t]
        self.lib.nav_run.restype=ctypes.c_int
        self.lib.nav_close.argtypes=[ctypes.c_void_p]
        self.lib.nav_close.restype=None
        error=ctypes.create_string_buffer(2048)
        self.handle=self.lib.nav_open(str(self.package/'kv260_navigation.xclbin').encode(),error,len(error))
        if not self.handle:
            raise RuntimeError(error.value.decode(errors='replace'))

    def run(self,input,output,length,groups,weight,mode):
        _validate_job(input,output,length,groups,weight,mode)
        error=ctypes.create_string_buffer(2048);hardware=ctypes.c_double();host=ctypes.c_double()
        result=self.lib.nav_run(self.handle,input.ctypes.data,output.ctypes.data,length,groups,weight,mode,
            ctypes.byref(hardware),ctypes.byref(host),error,len(error))
        if result:raise RuntimeError(error.value.decode(errors='replace'))
        return dict(hardware_seconds=hardware.value,host_run_seconds=host.value)

    def close(self):
        if getattr(self,'handle',None):self.lib.nav_close(self.handle);self.handle=None
        if getattr(self,'lock',None):self.lock.close()


def _validate_job(input,output,length,groups,weight,mode):
    if not 1<=length<=1024 or not 1<=groups<=131072 or not 1<=weight<=0xffffffff or mode not in (0,1) or length*groups*64>640000000:
        raise ValueError('Invalid EDT line job')
    for a in (input,output):
        if a.shape!=(groups,length,8) or a.dtype!=np.uint64 or not a.flags.c_contiguous:
            raise ValueError('EDT buffers must be contiguous uint64 (groups,length,8)')
    if not output.flags.writeable:raise ValueError('EDT output is read only')


def distance_transform(mask,spacing_zyx,session=None):
    if mask.ndim!=3 or min(mask.shape)<1 or max(mask.shape)>1024 or mask.size>80_000_000:
        raise ValueError('PL EDT requires a 3D crop with axes 1..1024, at most 80M voxels')
    spacing=np.asarray(spacing_zyx,dtype=float)
    if spacing.shape!=(3,) or not np.all(np.isfinite(spacing)) or min(spacing)<=0 or max(spacing)>32:
        raise ValueError('Unsupported PL spacing')
    weights=np.rint(spacing*spacing*Q).astype(np.uint64)
    if np.any(weights==0):raise ValueError('Spacing below Q20 resolution')
    start=time.perf_counter();owned=session is None
    if owned:session=XRTSession()
    setup=time.perf_counter()-start;passes=[];volume=mask.astype(np.uint64)
    try:
        for pass_id,axis in enumerate((2,1,0)):
            begin=time.perf_counter();packed,layout=session.pack(volume,axis)
            pack_seconds=time.perf_counter()-begin;output=np.empty_like(packed)
            groups,length,_=packed.shape
            stats=session.run(packed,output,length,groups,int(weights[axis]),0 if pass_id==0 else 1)
            begin=time.perf_counter();volume=session.unpack(output,layout)
            unpack_seconds=time.perf_counter()-begin
            passes.append(dict(axis_zyx=axis,length=length,groups=groups,pack_seconds=pack_seconds,
                unpack_seconds=unpack_seconds,**stats))
        if np.any(volume==INF):raise RuntimeError('Distance field has no finite background; require zero padding')
        begin=time.perf_counter();result=np.sqrt(volume.astype(np.float64)/Q).astype(np.float32)
        finish=time.perf_counter()-begin
        return result,dict(backend='pl_edt' if owned or isinstance(session,XRTSession) else 'native_c_model',lanes=8,
            compute_lanes=getattr(session,'edt_compute_lanes',None),
            q20_weights=weights.tolist(),session_setup_seconds=setup,passes=passes,
            sqrt_seconds=finish,total_seconds=time.perf_counter()-start)
    finally:
        if owned:session.close()
