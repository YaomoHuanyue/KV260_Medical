"""DFX MC candidate runtime: one uploaded mask, actual count/produce AXIS passes.

Native calls wait in the application's background worker; Python never computes
MC vertices and never falls back to a PS mesher.
"""
from pathlib import Path
import ctypes as C
import hashlib
import json
import os
import platform
import sys
import threading
import time
import numpy as np

HERE=Path(__file__).resolve().parent
MODULE=HERE.parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT))
from modules.reconstruction.axis_mc_8_r2.protocol import plan,decode

PHASES=('allocation_and_canaries','guard_to_device','DFX_selection','control',
        'execution','output_from_device','validate_and_copy','total_host',
        'partial_load','switch_total')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4*1024**2),b''):h.update(b)
    return h.hexdigest()


def verify_release():
    release=HERE/'release_r1'
    manifest=json.loads((release/'manifest.json').read_text())
    if not manifest['full_PR_passed'] or not manifest['actual_RM_synthesis_passed']:
        raise RuntimeError('Unqualified offline D7 firmware; no hardware access')
    if manifest['identity']!=0xd7 or manifest['RP_bits']!=1830:
        raise RuntimeError('Wrong D7 DFX boundary')
    for name,digest in manifest['runtime_files_SHA256'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Invalid D7 runtime path')
        unresolved=ROOT/relative;path=unresolved.resolve()
        links=[unresolved,*[p for p in unresolved.parents if p.is_relative_to(ROOT)]]
        if not path.is_relative_to(ROOT) or any(p.is_symlink() for p in links) or sha(path)!=digest:
            raise RuntimeError('Changed D7 runtime: '+name)
    partial=MODULE/'dfx_r1/release_r1/medical_mc_D7_axis8_r2_partial.bin'
    if sha(partial)!=manifest['partial_SHA256'] or sha(Path('/lib/firmware')/partial.name)!=manifest['partial_SHA256']:
        raise RuntimeError('Installed D7 firmware differs; no hardware access')
    base=MODULE/'dfx_r1/release_r1/manifest.json'
    if sha(base)!=manifest['MC_base_manifest_SHA256']:
        raise RuntimeError('Changed MC base firmware qualification')
    # This separate candidate is only used by explicit board-qualification
    # commands. Full offline physical/PR, source, host and installed firmware
    # identities are required here; UI promotion additionally requires board
    # correctness and same-input optimized-PS timing evidence.
    fma=ROOT/'dfx/smooth_speed/release_FMA2_r1/manifest.json'
    if sha(fma)!=manifest['FMA2_manifest_SHA256']:
        raise RuntimeError('Changed FMA2 firmware qualification')
    partial=ROOT/'dfx/smooth_speed/release_FMA2_r1/medical_smooth_speed_FMA2_r1_partial.bin'
    if sha(partial)!=manifest['FMA2_partial_SHA256'] or sha(Path('/lib/firmware')/partial.name)!=manifest['FMA2_partial_SHA256']:
        raise RuntimeError('Installed FMA2 firmware differs')
    return manifest


class Session:
    def __init__(self):
        self._handle=C.c_void_p();self._lib=None;self._plan=None;self._count=None
        self._lock=threading.RLock();self.uploads=0;self.frames=0;self.open_seconds=0

    def __enter__(self):
        with self._lock:
            if self._handle.value:raise RuntimeError('MC context already open')
            if platform.machine()!='aarch64' or os.geteuid()!=0:
                raise RuntimeError('MC hardware entry requires the KV260 ARM runtime')
            verify_release();(HERE/'results').mkdir(exist_ok=True)
            library=C.CDLL(str(HERE/'native_ARM_r1/libmc_axis_dfx.so'))
            library.mc_error.restype=C.c_char_p
            library.mc_open_root.argtypes=[C.c_char_p];library.mc_open_root.restype=C.c_void_p
            library.mc_upload.argtypes=[C.c_void_p,C.c_void_p,C.c_uint64,*([C.c_uint32]*3),C.c_void_p]
            library.mc_upload.restype=C.c_int
            library.mc_stream.argtypes=[C.c_void_p,*([C.c_uint32]*3),C.c_void_p,C.c_uint64,C.c_void_p,C.c_void_p]
            library.mc_stream.restype=C.c_int
            library.mc_close.argtypes=[C.POINTER(C.c_void_p)];library.mc_close.restype=C.c_int
            library.mc_smooth_job.argtypes=[C.c_void_p,C.c_char_p,C.c_char_p,C.c_char_p];library.mc_smooth_job.restype=C.c_int
            library.mc_session_report.argtypes=[C.c_void_p,C.c_char_p];library.mc_session_report.restype=C.c_int
            started=time.perf_counter();handle=library.mc_open_root(os.fsencode(ROOT));elapsed=time.perf_counter()-started
            if not handle:raise RuntimeError(library.mc_error().decode())
            self._lib=library;self._handle=C.c_void_p(handle);self.open_seconds=elapsed;return self

    def _require(self):
        if not self._handle.value or self._lib is None:raise RuntimeError('MC context is not open')

    def _check(self,code):
        if code:raise RuntimeError(self._lib.mc_error().decode())

    def upload(self,mask):
        with self._lock:
            self._require()
            if not isinstance(mask,np.ndarray) or mask.dtype!=np.uint8 or mask.ndim!=3 or not mask.flags.c_contiguous:
                raise ValueError('MC requires an existing contiguous uint8 ZYX mask; no implicit conversion')
            configuration=plan(mask.shape[::-1]);metrics=np.zeros(4,np.float64)
            self._plan=None;self._count=None
            self._check(self._lib.mc_upload(self._handle,mask.ctypes.data,mask.nbytes,*mask.shape[::-1],metrics.ctypes.data))
            self._plan=configuration;self.uploads+=1
            return dict(zip(('allocation','copy_and_tail','input_to_device','total_host'),map(float,metrics)))

    def _stream(self,configuration):
        self._require()
        if self._plan is None:raise RuntimeError('Upload a mask before MC execution')
        started=time.perf_counter();payload=np.empty(configuration.output_bytes,np.uint8)
        allocated=time.perf_counter()-started
        footer=np.zeros(16,np.uint32);metrics=np.zeros(10,np.float64)
        self._check(self._lib.mc_stream(self._handle,int(configuration.count_only),configuration.capacity,
            configuration.expected,payload.ctypes.data,payload.nbytes,footer.ctypes.data,metrics.ctypes.data))
        self.frames+=1
        if not np.array_equal(payload[-64:].view('<u4'),footer):raise RuntimeError('MC footer copy mismatch')
        result=decode(payload,configuration)
        timings=dict(zip(PHASES,map(float,metrics)));timings['Python_output_allocation']=allocated
        return result,timings

    def count(self):
        with self._lock:
            self._require()
            if self._plan is None:raise RuntimeError('Upload a mask before counting')
            self._count=None
            result,timings=self._stream(self._plan);self._count=result.required
            return result.required,timings

    def produce(self):
        with self._lock:
            self._require()
            if self._plan is None or self._count is None:raise RuntimeError('Successful count required before MC production')
            p=self._plan
            configuration=plan((p.nx,p.ny,p.nz),count_only=False,capacity=self._count,expected=self._count)
            try:result,timings=self._stream(configuration)
            except BaseException:
                self._count=None
                raise
            # Retains the payload allocation; no Python per-vertex loop/copy.
            vertices=np.frombuffer(result.vertices,dtype='<u8')
            return vertices,timings

    def reconstruct(self,mask):
        with self._lock:
            started=time.perf_counter();upload=self.upload(mask);count,c=self.count();vertices,p=self.produce()
            return vertices,dict(backend='DFX_PL_MC_AXIS_D7',triangles=count,input_uploads=1,
                algorithm_stream_passes=2,upload=upload,count=c,produce=p,total_host_seconds=time.perf_counter()-started)

    @staticmethod
    def _output(filename):
        path=Path(filename).resolve()
        if not path.is_relative_to(ROOT) or not path.parent.is_dir() or path.exists():
            raise ValueError('Choose a new output inside the medical project')
        return path

    def run(self,operation,folder,output,report):
        with self._lock:
            self._require()
            if operation not in ('mc','smooth'):raise ValueError('Unsupported reconstruction operation')
            folder=Path(folder).resolve(strict=True)
            if not folder.is_relative_to(ROOT) or not folder.is_dir():raise ValueError('Owned reconstruction input folder required')
            output=self._output(output);report=self._output(report)
            if output==report:raise ValueError('Distinct model and report outputs required')
            if operation=='smooth':
                self._plan=None;self._count=None
                self._check(self._lib.mc_smooth_job(self._handle,os.fsencode(folder),os.fsencode(output),os.fsencode(report)))
                info=json.loads(report.read_text())
                if info['kernel']!='FMA2' or info['DMA_red_zones_checked']!=22 or info['report_words'][0]!=0:
                    raise RuntimeError('Qualified FMA2 result metadata required')
                return info
            started=time.perf_counter()
            dimensions=tuple(int(v) for v in (folder/'dimensions.txt').read_text().split())
            configuration=plan(dimensions)
            source=folder/'mask.u8'
            if source.stat().st_size!=configuration.voxels:raise ValueError('MC mask dimensions/byte count mismatch')
            mask=np.fromfile(source,np.uint8).reshape(dimensions[::-1])
            vertices,details=self.reconstruct(mask);vertices.tofile(output)
            count,produce=details['count'],details['produce']
            info=dict(backend='dfx_pl',kernel='AXIS_D7',transport='AXIS512',triangles=details['triangles'],
                generation_passes=2,compute_seconds=count['execution']+produce['execution'],
                partial_seconds=count['partial_load']+produce['partial_load'],
                switch_seconds=count['switch_total']+produce['switch_total'],
                host_seconds=time.perf_counter()-started,phases=details)
            report.write_text(json.dumps(info,indent=2)+'\n');return info

    def report(self,filename):
        with self._lock:
            self._require();path=self._output(filename)
            self._check(self._lib.mc_session_report(self._handle,os.fsencode(path)))
            return json.loads(path.read_text())

    def close(self):
        with self._lock:
            if self._handle.value:
                self._check(self._lib.mc_close(C.byref(self._handle)))
                if self._handle.value:raise RuntimeError('MC close did not release the context')
            self._plan=None;self._count=None;self._lib=None

    def __exit__(self,*error):self.close()
