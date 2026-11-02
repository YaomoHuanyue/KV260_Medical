"""Verified optimized native C4 algorithm for the production PS comparison."""
from pathlib import Path
import ctypes,hashlib,json,platform,time
import numpy as np

HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
class NativeSession:
    def __init__(self,threads=4):
        if threads not in (1,4):raise ValueError('Choose the checked PS1 or PS4 implementation')
        host='ARM' if platform.machine()=='aarch64' else 'Windows'
        proof=json.loads((HERE/f'results/selected_native_build_{host}_r1.json').read_text())
        origin=json.loads((HERE/'selected_native_origin_r1.json').read_text())
        if proof['origin_sha256']!=sha(HERE/'selected_native_origin_r1.json'):
            raise ValueError('Native build origin changed')
        for n,d in origin['new_source_sha256'].items():
            if sha(HERE/'selected_native_r1'/n)!=d:raise ValueError('Native source changed')
        item=next(v for v in proof['binaries'] if v['threads']==threads)
        path=HERE/item['binary']
        if sha(path)!=item['sha256']:raise ValueError('Native binary changed')
        self.lib=ctypes.CDLL(str(path));self.lib.route_model.argtypes=[ctypes.c_void_p]*2+[ctypes.c_uint]*3
        self.lib.route_model.restype=ctypes.c_int;self.threads=threads
    def run_route(self,data,operation):
        if data.dtype!=np.uint64 or data.ndim!=2 or data.shape[1]!=8 or not data.flags.c_contiguous:
            raise ValueError('Invalid native route packet')
        out=np.zeros((1 if operation==0 else 8706,8),np.uint64)
        start=time.perf_counter();status=self.lib.route_model(data.ctypes.data,out.ctypes.data,len(data),len(out),operation)
        return out,dict(status=status,kind='CPU native HLS model',hardware_seconds=None,
            host_run_seconds=time.perf_counter()-start,threads=self.threads)
