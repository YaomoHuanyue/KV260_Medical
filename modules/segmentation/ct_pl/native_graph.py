"""Keep PS feature maps contiguous in pixel/channel order between PL layers."""
import ctypes
from pathlib import Path
import numpy as np
from .quantized_runtime import QuantizedGraph,Quantized,Concatenated


class NativeGraph(QuantizedGraph):
    def __init__(self,folder,backend,library=None):
        super().__init__(folder,backend)
        self.identity_tables=set()
        if library is None:
            import sys
            library=Path(__file__).parent/'build'/('ct_graph_ops.dll' if sys.platform=='win32' else 'libct_graph_ops.so')
        self.ops=ctypes.CDLL(str(library));L=self.ops;ptr=ctypes.c_void_p;u=ctypes.c_uint
        L.ct_lut.argtypes=[ptr,ptr,ctypes.c_size_t,ptr]
        L.ct_relu.argtypes=[ptr,ptr,ctypes.c_size_t,ctypes.c_int]
        L.ct_pool2.argtypes=L.ct_resize2.argtypes=[ptr,ptr,u,u,u]
        L.ct_concat2.argtypes=[ptr,ptr,ptr,u,u,u]
        for name in ['ct_lut','ct_relu','ct_pool2','ct_resize2','ct_concat2']:getattr(L,name).restype=None

    @staticmethod
    def hwc(x):
        assert x.ndim==4 and x.shape[0]==1 and x.dtype==np.int8
        return np.ascontiguousarray(x[0].transpose(1,2,0))

    @staticmethod
    def nchw(x):return x.transpose(2,0,1)[None]

    def empty(self,shape):return np.empty(shape,np.int8)

    def quantize(self,value,scale,zero,axis=1):
        if isinstance(value,Concatenated) and len(value.values)==2 and value.axis==1 and scale.size==zero.size==1 and zero.dtype==np.int8:
            a,b=[self.hwc(self.quantize(v,scale,zero,axis)) for v in value.values]
            assert a.shape[:2]==b.shape[:2]
            h,w,ca=a.shape;cb=b.shape[2];out=self.empty((h,w,ca+cb))
            self.ops.ct_concat2(a.ctypes.data,b.ctypes.data,out.ctypes.data,h*w,ca,cb)
            return self.nchw(out)
        if isinstance(value,Quantized) and value.data.dtype==np.int8 and value.scale.size==value.zero.size==scale.size==zero.size==1 and zero.dtype==np.int8:
            key=(value.scale.tobytes(),value.zero.tobytes(),scale.tobytes(),zero.tobytes())
            if key not in self.tables:
                raw=np.arange(256,dtype=np.uint8).view(np.int8)
                f=(raw.astype(np.float32)-value.zero)*value.scale
                self.tables[key]=np.clip(np.rint(f/scale)+zero,-128,127).astype(np.int8)
                if np.array_equal(self.tables[key],raw):self.identity_tables.add(key)
            if key in self.identity_tables:return value.data
            data=self.hwc(value.data);out=self.empty(data.shape)
            self.ops.ct_lut(data.ctypes.data,out.ctypes.data,data.size,self.tables[key].ctypes.data)
            return self.nchw(out)
        return super().quantize(value,scale,zero,axis)

    def relu(self,q):
        if isinstance(q,Quantized) and q.data.dtype==np.int8 and q.zero.size==1 and np.all(q.scale>0):
            data=self.hwc(q.data);out=self.empty(data.shape)
            self.ops.ct_relu(data.ctypes.data,out.ctypes.data,data.size,int(q.zero.item()))
            return Quantized(self.nchw(out),q.scale,q.zero)
        return super().relu(q)

    def pool(self,q):
        if isinstance(q,Quantized) and q.data.dtype==np.int8:
            data=self.hwc(q.data);h,w,c=data.shape;assert h%2==0 and w%2==0
            out=self.empty((h//2,w//2,c))
            self.ops.ct_pool2(data.ctypes.data,out.ctypes.data,h,w,c)
            return Quantized(self.nchw(out),q.scale,q.zero)
        return super().pool(q)

    def resize(self,q):
        if isinstance(q,Quantized) and q.data.dtype==np.int8:
            data=self.hwc(q.data);h,w,c=data.shape;out=self.empty((h*2,w*2,c))
            self.ops.ct_resize2(data.ctypes.data,out.ctypes.data,h,w,c)
            return Quantized(self.nchw(out),q.scale,q.zero)
        return super().resize(q)
