"""Verified ARM native 1/4-core CPU baseline, without any PL access."""
import ctypes
import hashlib
import itertools
import json
from pathlib import Path
from time import perf_counter
import numpy as np
from .mesh_clearance import MeshClearance

ROOT = Path(__file__).resolve().parent


class NativeMeshClearance(MeshClearance):
    def __init__(self, points, faces):
        manifest = json.loads((ROOT/'host/build/build.json').read_text(encoding='utf-8'))
        sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        for name, digest in manifest['files_sha256'].items():
            p = (ROOT/name).resolve()
            if not p.is_relative_to(ROOT) or sha(p) != digest:
                raise RuntimeError('Native CPU baseline build/source hash mismatch')
        super().__init__(points, faces)
        self.lib = ctypes.CDLL(str(ROOT/'host/build/libmesh_distance.so'))
        self.lib.mesh_distance_abi.restype = ctypes.c_uint64
        if self.lib.mesh_distance_abi() != 0x4d455348434c0001:
            raise RuntimeError('Native geometric baseline ABI mismatch')
        self.lib.mesh_distance_native.argtypes = [ctypes.c_void_p]*4 + [ctypes.c_uint]*2 + [ctypes.c_uint64,ctypes.c_uint] + [ctypes.c_void_p]*3
        self.lib.mesh_distance_native.restype = ctypes.c_int

    def distance(self, points, *, threads=4):
        if threads not in (1, 4):
            raise ValueError('Baseline compares exactly 1 or 4 CPU cores')
        p = np.ascontiguousarray(points, np.float64)
        if not 1 <= len(p) <= 4096:
            raise ValueError('Native baseline supports 1 through 4096 query points')
        start = perf_counter()
        groups, upper = self.candidates(p)
        pruned = perf_counter()
        counts = np.array([len(x) for x in groups], np.uint64)
        if np.any(counts == 0):
            raise RuntimeError('Triangle pruning lost a valid vertex upper bound')
        offsets = np.r_[np.uint64(0), np.cumsum(counts, dtype=np.uint64)]
        indices = np.fromiter(itertools.chain.from_iterable(groups), np.uint64, count=int(offsets[-1]))
        packed = perf_counter()
        result = np.empty(len(p), np.float64)
        closest = np.empty_like(p)
        ids = np.empty(len(p), np.uint64)
        code = self.lib.mesh_distance_native(p.ctypes.data,self.triangles.ctypes.data,
            offsets.ctypes.data,indices.ctypes.data,len(p),len(self.triangles),len(indices),
            threads,result.ctypes.data,closest.ctypes.data,ids.ctypes.data)
        finished = perf_counter()
        if code:
            raise RuntimeError('Native geometric baseline rejected input: '+str(code))
        if not np.isfinite(result).all() or np.any(result > upper+np.maximum(1.,upper)*1e-9):
            raise RuntimeError('Invalid native geometric wall distance')
        return result,closest,ids,dict(backend='PS_ARM_native_exact_triangle_float64',
            threads=threads,query_seconds=finished-start,preparation_seconds=self.preparation_seconds,
            KD_pruning_seconds=pruned-start,CSR_pack_seconds=packed-pruned,
            native_compute_with_input_validation_seconds=finished-packed,
            queries=len(p),candidate_pairs=len(indices),all_triangles=len(self.triangles),
            containment_certified=False,clinical_safety_certified=False,PL_access=False,
            PS_Marching_Cubes_used=False)
