"""Persistent CPU library context, with every calculation performed anew."""
from pathlib import Path
import ctypes
import os
import numpy as np

HERE = Path(__file__).resolve().parent


class ProfilePS:
    def __init__(self):
        library = HERE / 'build' / ('profile_ps_r1.dll' if os.name == 'nt' else 'libprofile_ps_r1.so')
        self.library = ctypes.CDLL(str(library))
        self.function = self.library.profile_ps
        self.function.argtypes = [ctypes.c_uint32]*2 + [ctypes.c_void_p]*4 + [ctypes.c_uint32]*2 + [ctypes.c_void_p,
                                  ctypes.c_double, ctypes.c_double, ctypes.c_uint32] + [ctypes.c_void_p]*2
        self.function.restype = ctypes.c_int

    def solve(self, graph, diameters, margin=.2, radius_weight=2., threads=4):
        diameters = np.asarray(sorted({float(d) for d in diameters if float(d) > 0}), dtype=np.float64)
        if not 1 <= len(diameters) <= 64 or not np.isfinite(diameters).all():
            raise ValueError('Invalid original profile diameters')
        distances = np.empty((len(diameters), len(graph.coordinates_zyx)), dtype=np.float64)
        parents = np.empty(distances.shape, dtype=np.int32)
        code = self.function(len(graph.coordinates_zyx), len(graph.neighbors), graph.rows.ctypes.data,
            graph.neighbors.ctypes.data, graph.lengths.ctypes.data, graph.radii_mm.ctypes.data,
            graph.root, len(diameters), diameters.ctypes.data, margin, radius_weight, threads,
            distances.ctypes.data, parents.ctypes.data)
        if code:
            raise ValueError('Invalid original profile inputs: ' + str(code))
        return diameters, distances, parents
