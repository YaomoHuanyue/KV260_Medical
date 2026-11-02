"""Preserve native reader operations with the new explicit runtime certificate."""
from contextlib import contextmanager
import os,platform


def candidate_class(certificate,base,integer):
    class BurstReader(base):
        def __init__(self,library,admission):
            if platform.system()!='Linux' or platform.machine()!='aarch64' or os.geteuid()!=0:
                raise RuntimeError('Actual ARM/root reader context required')
            self.handle=None
            self.admission=certificate.require_xrt(admission,library)
            try:
                integer.__init__(self,library,certificate.artifact('xclbin'),pl_quantization=True,output_pool=True)
                self._bind_pool_api();self._bind_reader_api()
                certificate.check_unchanged()
            except BaseException:
                integer.close(self)
                raise
    return BurstReader


@contextmanager
def bind_reader(certificate):
    from modules.segmentation.axis_tensor_reader_r3.host_r1 import backend as native
    from ct_pl.runtime import XRTInteger
    original=native.ReaderXRT
    selected=candidate_class(certificate,original,XRTInteger)
    native.ReaderXRT=selected
    try:yield selected
    finally:
        unexpected=native.ReaderXRT is not selected
        native.ReaderXRT=original
        if unexpected:raise RuntimeError('Original stage did not release its reader tracker')
