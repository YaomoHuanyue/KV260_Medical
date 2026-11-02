"""Identical stream bytes and complete checks without NumPy testing utilities."""
from pathlib import Path
import ctypes
import hashlib
import itertools
import math
import os
import numpy as np
from protocol_r1 import Native, encode_queries, SCENE, CAPACITY

HERE = Path(__file__).resolve().parent


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
        raise ValueError('Profile graph must preserve actual26neighbor offsets')
    offset = ((difference[:, 0]+1)*9+(difference[:, 1]+1)*3+difference[:, 2]+1).astype(np.uint32)
    if not np.array_equal(data.lengths, np.asarray(steps)[offset]):
        raise ValueError('Non-original graph edge lengths')
    scene[5+n:].view(np.uint32).ravel()[:m] = data.neighbors | (offset << 16)
    token = int.from_bytes(hashlib.sha256(scene.tobytes()).digest()[:8], 'little')
    scene[0, :5] = SCENE, n, m, data.root, token
    return scene, token


class CompleteChecks:
    def solve(self, graph, diameters, margin=.2, radius_weight=2.):
        scene, token = encode_scene(graph)
        ack, status = self.run(scene, 0)
        if status != 0 or int(ack[0, 1]) != token:
            raise RuntimeError('Profile scene acknowledgement mismatch')
        n = len(graph.coordinates_zyx); batch = (CAPACITY-1)//n
        distances, parents = [], []
        for start in range(0, len(diameters), batch):
            requested = diameters[start:start+batch]
            query = encode_queries(token, requested, margin, radius_weight)
            output, status = self.run(query, 1)
            if status != 0 or int(output[0, 1]) != n or int(output[0, 2]) != len(requested):
                raise RuntimeError('Profile output header mismatch')
            count = n*len(requested)
            words = output[1:1+count].reshape(len(requested), n, 8)
            if not np.array_equal(words[:, :, 2], np.broadcast_to(np.arange(n), (len(requested), n))):
                raise RuntimeError('Profile node IDs differ')
            if not np.array_equal(words[:, :, 3], np.broadcast_to(np.arange(len(requested))[:, None], (len(requested), n))):
                raise RuntimeError('Profile query IDs differ')
            if not np.all(output[1+count:] == 0) or not np.all(words[:, :, 4:] == 0):
                raise RuntimeError('Complete profile padding differs')
            distances.append(words.view(np.float64)[:, :, 0].copy())
            parents.append(words[:, :, 1].astype(np.uint32).view(np.int32))
        return np.concatenate(distances), np.concatenate(parents)


class NativeR2(CompleteChecks, Native):
    def __init__(self):
        library = HERE / 'build' / ('profile_native_r2.dll' if os.name == 'nt' else 'libprofile_native_r2.so')
        self.library = ctypes.CDLL(str(library))
        self.call = self.library.profile_model
        self.call.argtypes = [ctypes.c_void_p]*2 + [ctypes.c_uint]*3
        self.call.restype = ctypes.c_int


class R1AdapterSession(CompleteChecks):
    """The unchanged R1 PL runtime is composed separately by the board test."""
    pass
