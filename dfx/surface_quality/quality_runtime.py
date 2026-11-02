"""Independent C9 runtime. A verified routed release is mandatory before PL access."""
from pathlib import Path
import ctypes,hashlib,json,os,threading,time
import numpy as np
from prepare import SCENE_WORDS

ROOT=Path(__file__).resolve().parent
BASE_RELEASES={
    'medical':'ec51ff6cdf8077005a96c228f61e2d8ab2daa4f0c66f37865bd719c2f1eeefbc',
    'surface':'e9795aabf902acfd582ddda27d27ca6aa2659e3dc2ccb21078aa573e6ddd599b',
    'edt_volume':'50a7a050bea9bc0179fa07f529bb5f636545200cf2baad85f617d1f4954a0305',
}


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda:file.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def bound_files(values):
    for name,digest in values.items():
        file=(ROOT/name).resolve()
        if not file.is_relative_to(ROOT) or sha(file)!=digest:raise RuntimeError('Changed C9 source/artifact: '+name)


def verify(*,experimental=False):
    path=ROOT/'release/manifest.json'
    if not path.is_file():raise RuntimeError('C9 has no verified routed release; no PL access')
    manifest=json.loads(path.read_text())
    if (manifest.get('schema')!='kv260.surface_quality.dfx.v1' or manifest.get('identity')!=0xc9 or
            not manifest.get('offline_verified') or manifest.get('revision')!='R7_packed_70bit_reciprocal_10240_bricks'):
        raise RuntimeError('Unsupported C9 release; no PL access')
    if not experimental:
        path_accepted=ROOT/'docs/board_acceptance_r7.json'
        accepted=json.loads(path_accepted.read_text()) if path_accepted.is_file() else {}
        if (accepted.get('status')!='accepted_exact_and_faster_than_PS4' or
                accepted.get('release_manifest_sha256')!=sha(path)):
            raise RuntimeError('C9 board acceptance is pending; explicit experimental test required')
    for name,digest in BASE_RELEASES.items():
        if sha(ROOT.parent/name/'release/manifest.json')!=digest:raise RuntimeError('Changed accepted base release: '+name)
    bound_files({**manifest['source_sha256'],**manifest['artifact_sha256']})
    if sha(Path('/lib/firmware/medical_quality_partial.bin'))!=manifest['partial_bin_sha256']:
        raise RuntimeError('Installed C9 partial mismatch; no PL access')
    host=json.loads((ROOT/'build/host_compiled_r7.json').read_text())
    if host.get('status')!='compiled_on_ARM_no_PL_access' or host.get('architecture')!='aarch64':
        raise RuntimeError('No bound ARM C9 host build')
    bound_files(host['source_sha256'])
    bound_files({'build/'+name:digest for name,digest in host['library_sha256'].items()})
    return manifest


class QualitySession:
    def __init__(self,*,experimental=False):self.experimental=experimental;self.handle=None;self.lock=threading.RLock()
    def __enter__(self):
        self.manifest=verify(experimental=self.experimental)
        self.previous=Path.cwd();os.chdir(ROOT.parent/'medical')
        try:
            lib=self.lib=ctypes.CDLL(str(ROOT/'build/libquality_bridge.so'))
            lib.quality_error.restype=ctypes.c_char_p;lib.quality_open.restype=ctypes.c_void_p
            lib.quality_close.argtypes=[ctypes.c_void_p]
            lib.quality_return_to_scope.argtypes=[ctypes.c_void_p];lib.quality_return_to_scope.restype=ctypes.c_int
            lib.quality_transfer.argtypes=[ctypes.c_void_p]*3+[ctypes.c_uint]*3+[ctypes.POINTER(ctypes.c_double)]*2
            lib.quality_transfer.restype=ctypes.c_int
            lib.quality_phase.argtypes=[ctypes.c_void_p,ctypes.c_uint];lib.quality_phase.restype=ctypes.c_double
            self.handle=lib.quality_open()
            if not self.handle:raise RuntimeError(lib.quality_error().decode())
        except BaseException:os.chdir(self.previous);raise
        return self
    def check(self,rc):
        if rc:raise RuntimeError(self.lib.quality_error().decode())
    def transfer(self,blob,out_words,operation):
        if not isinstance(blob,bytes) or len(blob)%64:raise ValueError('Immutable complete AXIS words required')
        if not (operation==0 and len(blob)==SCENE_WORDS*64 and out_words==1 or
                operation==1 and len(blob)==64 and 9<=out_words<=40961):raise ValueError('C9 transfer bounds')
        source=np.frombuffer(blob,np.uint8);output=np.empty(out_words*8,np.uint64)
        hardware,total=ctypes.c_double(),ctypes.c_double();start=time.perf_counter()
        with self.lock:
            if not self.handle:raise RuntimeError('Closed C9 context')
            self.check(self.lib.quality_transfer(self.handle,source.ctypes.data,output.ctypes.data,len(blob)//64,out_words,
                        operation,ctypes.byref(hardware),ctypes.byref(total)))
            names=['validation','allocation_copy_guards','sync_to','partial_select','hardware','sync_from','guard_check_readback_copy']
            phases={name:self.lib.quality_phase(self.handle,index) for index,name in enumerate(names)}
        return output,dict(backend='PL_C9_R7',hardware_seconds=hardware.value,host_run_seconds=total.value,
            total_seconds=time.perf_counter()-start,phases=phases,four_4096_byte_DMA_guards_passed=True,
            input_and_tokens_checked=True,production_accepted=not self.experimental)
    def load(self,blob):return self.transfer(blob,1,0)[1]
    def render(self,request):
        values=np.asarray(request)
        if values.shape!=(16,) or values.dtype.kind not in 'iu' or values.min()<-2147483648 or values.max()>2147483647:
            raise ValueError('16 bounded integer camera parameters required')
        p=np.ascontiguousarray(values,dtype='<i4');width,height=map(int,p[:2])
        if not (16<=width<=640 and width%16==0 and 4<=height<=512):raise ValueError('C9 frame dimensions')
        output,stats=self.transfer(p.tobytes(),1+width*height//8,1)
        return output[8:].reshape(height,width),stats
    def close(self):
        with self.lock:
            if self.handle:
                try:self.check(self.lib.quality_return_to_scope(self.handle))
                finally:self.lib.quality_close(self.handle);self.handle=None;os.chdir(self.previous)
    def __exit__(self,*args):self.close()


class PSReference:
    """Same integer renderer on one/four ARM cores; dense unpack occurs once."""
    def __init__(self,blob):
        from prepare import unpack_scene
        self.q,self.target=unpack_scene(blob)
        self.q=np.ascontiguousarray(self.q,np.int16);self.target=np.ascontiguousarray(self.target,np.uint8)
        header=np.frombuffer(blob,'<i4',count=16);self.matrix=np.ascontiguousarray(header[6:15],np.int32)
        self.bits=(int(header[15])>>8)&255
        self.lib=ctypes.CDLL(str(ROOT/'build/libquality_reference.so'))
        self.lib.quality_reference.argtypes=[ctypes.c_void_p]*2+[ctypes.c_int]*3+[ctypes.c_void_p]*3+[ctypes.c_int]*2
        self.lib.quality_reference.restype=None
        self.validator=ctypes.CDLL(str(ROOT/'build/libquality_validator.so'))
        self.validator.quality_validate.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_uint]
        self.validator.quality_validate.restype=ctypes.c_int
        self.validator.quality_validation_error.restype=ctypes.c_char_p
    def render(self,request,threads=4):
        if threads not in (1,4):raise ValueError('One/four CPU cores required')
        p=np.asarray(request)
        if p.shape!=(16,) or p.dtype!=np.dtype('<i4') or not p.flags.c_contiguous:raise ValueError('Contiguous INT32 camera parameters')
        width,height=map(int,p[:2]);out_words=1+width*height//8
        if self.validator.quality_validate(p.ctypes.data,1,out_words,1):raise ValueError(self.validator.quality_validation_error().decode())
        result=np.empty((height,width),np.uint64);nz,ny,nx=self.q.shape;start=time.perf_counter()
        self.lib.quality_reference(self.q.ctypes.data,self.target.ctypes.data,nx,ny,nz,p.ctypes.data,self.matrix.ctypes.data,
                                   result.ctypes.data,threads,self.bits)
        return result,time.perf_counter()-start
