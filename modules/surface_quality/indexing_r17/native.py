"""Bounded native equivalent of the R7 Python vertex-link review.

Runs on PS; all coordinates and ordered triangles must remain exact.
No fallback generates topology if the native helper is missing.
"""
from pathlib import Path
from functools import lru_cache
import ctypes as c
import hashlib, json, os, sys
import numpy as np

HERE = Path(__file__).resolve().parent

@lru_cache(maxsize=1)
def library():
    windows = sys.platform == 'win32'
    folder = HERE / ('build_Windows' if windows else 'build_ARM')
    path = folder / ('indexing.dll' if windows else 'libindexing.so')
    meta = json.loads((folder/'build.json').read_text(encoding='utf-8'))
    for p, name in ((HERE/'split_links.cpp','source_sha256'),(path,'library_sha256')):
        if hashlib.sha256(p.read_bytes()).hexdigest() != meta[name]:
            raise RuntimeError('Native indexing source/library build binding mismatch')
    if windows:
        # MinGW's pthread runtime is resolved only for this library load.
        with os.add_dll_directory(str(Path(meta['argv'][0]).parent)):
            lib = c.CDLL(str(path))
    else:
        lib = c.CDLL(str(path))
    u64 = c.POINTER(c.c_uint64); doubles = c.POINTER(c.c_double)
    lib.split_vertex_links_r17.argtypes = [doubles,c.c_uint64,u64,c.c_uint64,
        doubles,c.c_uint64,u64,u64,c.POINTER(c.c_char),c.c_uint64]
    lib.split_vertex_links_r17.restype = c.c_int
    return lib

def split_vertex_links(points, faces):
    points, faces = np.asarray(points), np.asarray(faces)
    if (points.ndim != 2 or points.shape[1] != 3 or not len(points) or
        points.dtype not in (np.dtype('float32'),np.dtype('float64')) or not np.isfinite(points).all()):
        raise ValueError('Finite FLOAT32/FLOAT64 vertex coordinates required')
    if (faces.ndim != 2 or faces.shape[1] != 3 or not len(faces) or faces.dtype.kind not in 'iu'):
        raise ValueError('Nonempty integer triangle indices required')
    if np.any(faces < 0) or np.any(faces >= len(points)):
        raise ValueError('Face index outside vertex array')
    capacity = len(points) + faces.size
    if capacity > np.iinfo(faces.dtype).max:
        raise ValueError('Vertex-link output exceeds index dtype capacity')
    p = np.ascontiguousarray(points, dtype=np.float64)
    f = np.ascontiguousarray(faces, dtype=np.uint64)
    out_p = np.empty((capacity,3),np.float64)
    out_f = np.empty_like(f)
    stats = np.zeros(3,np.uint64)
    error = c.create_string_buffer(512)
    ptr = lambda a,t: a.ctypes.data_as(c.POINTER(t))
    code = library().split_vertex_links_r17(ptr(p,c.c_double),len(p),ptr(f,c.c_uint64),len(f),
        ptr(out_p,c.c_double),capacity,ptr(out_f,c.c_uint64),ptr(stats,c.c_uint64),error,len(error))
    if code:
        exception = ValueError if code == 1 else RuntimeError
        raise exception(error.value.decode('utf-8',errors='replace'))
    used, splits, copies = map(int,stats)
    if used != len(points)+copies or used > capacity or np.any(out_f >= used):
        raise RuntimeError('Invalid native indexing result dimensions')
    return out_p[:used].astype(points.dtype,copy=True), out_f.astype(faces.dtype,copy=False), splits, copies
