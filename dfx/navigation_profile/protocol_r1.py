"""Independent raw-profile stream format, with unchanged complete output capacity."""
from pathlib import Path
import ctypes
import hashlib
import itertools
import math
import os
import numpy as np

HERE = Path(__file__).resolve().parent
SCENE = 0x50524f46494c4531
QUERY = 0x5052515545525931
CAPACITY = 8706


def encode_scene(data):
    n, m = len(data.coordinates_zyx), len(data.neighbors)
    if not 1 <= n <= 4096 or m > n*26:
        raise ValueError('Raw graph exceeds explicit profile capacity; never downsample')
    scene = np.zeros((5+n+(m+15)//16, 8), dtype=np.uint64)
    steps = [math.sqrt(sum((delta*spacing)**2 for delta, spacing in zip(offset, data.spacing_zyx)))
             for offset in itertools.product((-1, 0, 1), repeat=3)]
    scene.view(np.float64)[1:5].ravel()[:27] = steps
    scene.view(np.float64)[5:5+n, 0] = data.radii_mm
    scene[5:5+n, 1] = data.rows[:-1]; scene[5:5+n, 2] = data.rows[1:]
    source = np.repeat(np.arange(n), np.diff(data.rows.astype(np.int64)))
    difference = data.coordinates_zyx[data.neighbors]-data.coordinates_zyx[source]
    if np.any(difference < -1) or np.any(difference > 1) or np.any(np.all(difference == 0, axis=1)):
        raise ValueError('Profile graph must preserve actual 26-neighbor offsets')
    offset = ((difference[:, 0]+1)*9+(difference[:, 1]+1)*3+difference[:, 2]+1).astype(np.uint32)
    np.testing.assert_array_equal(data.lengths, np.asarray(steps)[offset])
    code = data.neighbors | (offset << 16)
    scene[5+n:].view(np.uint32).ravel()[:m] = code
    token = int.from_bytes(hashlib.sha256(scene.tobytes()).digest()[:8], 'little')
    scene[0, :5] = SCENE, n, m, data.root, token
    return scene, token


def encode_queries(token, diameters, margin=.2, radius_weight=2.):
    diameters = np.asarray(diameters, dtype=np.float64)
    if diameters.ndim != 1 or not 1 <= len(diameters) <= 64 or not np.isfinite(diameters).all() or np.any(diameters <= 0):
        raise ValueError('Invalid complete profile diameter batch')
    if not np.isfinite([margin, radius_weight]).all() or min(margin, radius_weight) < 0:
        raise ValueError('Invalid original weighting parameters')
    query = np.zeros((1+len(diameters), 8), np.uint64)
    query[0, :3] = QUERY, token, len(diameters)
    query.view(np.float64)[1:, 0] = diameters
    query.view(np.float64)[1:, 1] = margin
    query.view(np.float64)[1:, 2] = radius_weight
    return query


class Native:
    """Numerical model only; no throughput or hardware DATAFLOW claim."""
    def __init__(self):
        library = HERE/'build'/('profile_native_r1.dll' if os.name == 'nt' else 'libprofile_native_r1.so')
        self.library = ctypes.CDLL(str(library))
        self.call = self.library.profile_model
        self.call.argtypes = [ctypes.c_void_p]*2 + [ctypes.c_uint]*3
        self.call.restype = ctypes.c_int

    def run(self, data, operation, *, output_count=None):
        data = np.ascontiguousarray(data, dtype=np.uint64)
        if data.ndim != 2 or data.shape[1] != 8:
            raise ValueError('Require complete 512-bit input words')
        count = output_count if output_count is not None else (1 if operation == 0 else CAPACITY)
        raw = np.full((count+2, 8), np.uint64(0x9A6172ED6B382054))
        output = raw[1:-1]
        status = self.call(data.ctypes.data, output.ctypes.data, len(data), count, operation)
        assert np.all(raw[0] == 0x9A6172ED6B382054) and np.all(raw[-1] == 0x9A6172ED6B382054)
        assert status == int(output[0, 0])
        return output, status

    def solve(self, graph, diameters, margin=.2, radius_weight=2.):
        scene, token = encode_scene(graph)
        ack, status = self.run(scene, 0)
        assert status == 0 and int(ack[0, 1]) == token
        n = len(graph.coordinates_zyx); batch = (CAPACITY-1)//n
        distances, parents = [], []
        for start in range(0, len(diameters), batch):
            requested = diameters[start:start+batch]
            query = encode_queries(token, requested, margin, radius_weight)
            output, status = self.run(query, 1)
            assert status == 0 and int(output[0, 1]) == n and int(output[0, 2]) == len(requested)
            count = n*len(requested)
            words = output[1:1+count].reshape(len(requested), n, 8)
            np.testing.assert_array_equal(words[:, :, 2], np.broadcast_to(np.arange(n), (len(requested), n)))
            np.testing.assert_array_equal(words[:, :, 3], np.broadcast_to(np.arange(len(requested))[:, None], (len(requested), n)))
            assert np.all(output[1+count:] == 0) and np.all(words[:, :, 4:] == 0)
            distances.append(words.view(np.float64)[:, :, 0].copy())
            parents.append(words[:, :, 1].astype(np.uint32).view(np.int32))
        return np.concatenate(distances), np.concatenate(parents)
