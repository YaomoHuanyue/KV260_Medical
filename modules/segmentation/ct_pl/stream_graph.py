"""Fuse PS activation passes; prepare the next CT context while PL computes.

Deferred tensors own their source arrays. No in-place writes may corrupt U-Net
skip connections. The two-slot input pipeline bounds memory independently of Z.
"""
import ctypes
import os
from collections import Counter
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from .native_graph import NativeGraph
from .quantized_runtime import Quantized,Concatenated
from airway.ct_geometry import context_indices


@dataclass
class Deferred(Quantized):
    clamp: bool=False
    factor: int=1


class StreamGraph(NativeGraph):
    def __init__(self,folder,backend,library=None):
        super().__init__(folder,backend,library)
        p=ctypes.c_void_p;u=ctypes.c_uint
        self.ops.ct_transform.argtypes=[p,p,u,u,u,u,p]
        self.ops.ct_join_transform.argtypes=[p,p,p,u,u,u,u,u,u,p,p]
        self.ops.ct_context.argtypes=[p,p,p,p,u,u,u,u]
        self.ops.ct_hu_lut.argtypes=[p,p,ctypes.c_size_t,p]
        self.ops.ct_context5.argtypes=[p,p,p,p,p,p,u,u,u,u]
        self.ops.ct_pool_transform.argtypes=[p,p,u,u,u,p]
        for name in ['ct_transform','ct_join_transform','ct_context','ct_hu_lut','ct_context5','ct_pool_transform']:getattr(self.ops,name).restype=None
        self.fused_pools=[]
        if os.environ.get('CT_PS_POOL_FUSION','1')=='1':
            nodes=[];i=0
            while i<len(self.nodes):
                pool=self.nodes[i];q=self.nodes[i+1] if i+1<len(self.nodes) else None
                a=pool['attrs']
                if (pool['op']=='MaxPool' and q and q['op']=='QuantizeLinear'
                    and q['inputs'][0]==pool['outputs'][0] and self.uses[pool['outputs'][0]]==1
                    and a.get('kernel_shape')==[2,2] and a.get('strides')==[2,2]
                    and a.get('pads',[0,0,0,0])==[0,0,0,0]
                    and a.get('dilations',[1,1])==[1,1] and a.get('ceil_mode',0)==0):
                    nodes.append({'op':'PoolQuantize','inputs':[pool['inputs'][0],*q['inputs'][1:]],'outputs':q['outputs'],'attrs':q['attrs']})
                    self.fused_pools.append(pool['outputs'][0]);i+=2;continue
                nodes.append(pool);i+=1
            self.nodes=nodes;self.uses=Counter()
            for n in nodes:self.uses.update(self.dependencies(n))

    @staticmethod
    def eligible(q):
        return isinstance(q,Quantized) and q.data.dtype==np.int8 and q.zero.size==q.scale.size==1 and q.scale.item()>0

    def table(self,q,scale,zero):
        clamp=isinstance(q,Deferred) and q.clamp
        key=('deferred',q.scale.tobytes(),q.zero.tobytes(),scale.tobytes(),zero.tobytes(),clamp)
        if key not in self.tables:
            raw=np.arange(256,dtype=np.uint8).view(np.int8)
            source=np.maximum(raw,q.zero) if clamp else raw
            f=(source.astype(np.float32)-q.zero)*q.scale
            self.tables[key]=np.clip(np.rint(f/scale)+zero,-128,127).astype(np.int8)
            if np.array_equal(self.tables[key],raw):self.identity_tables.add(key)
        return key,self.tables[key]

    def quantize(self,value,scale,zero,axis=1):
        if scale.size==zero.size==1 and zero.dtype==np.int8:
            if isinstance(value,Concatenated) and value.axis==1 and len(value.values)==2 and all(self.eligible(q) for q in value.values):
                qa,qb=value.values;a,b=[self.hwc(q.data) for q in value.values]
                fa,fb=[getattr(q,'factor',1) for q in value.values]
                h,w,ca=a.shape;h*=fa;w*=fa;cb=b.shape[2]
                assert (h,w)==(b.shape[0]*fb,b.shape[1]*fb)
                ta=self.table(qa,scale,zero)[1];tb=self.table(qb,scale,zero)[1]
                out=self.empty((h,w,ca+cb))
                self.ops.ct_join_transform(a.ctypes.data,b.ctypes.data,out.ctypes.data,h,w,ca,cb,fa,fb,ta.ctypes.data,tb.ctypes.data)
                return self.nchw(out)
            if self.eligible(value):
                key,table=self.table(value,scale,zero);factor=getattr(value,'factor',1)
                if key in self.identity_tables and factor==1:return value.data
                data=self.hwc(value.data);h,w,c=data.shape;out=self.empty((h*factor,w*factor,c))
                self.ops.ct_transform(data.ctypes.data,out.ctypes.data,h,w,c,factor,table.ctypes.data)
                return self.nchw(out)
        return super().quantize(value,scale,zero,axis)

    def relu(self,q):
        if self.eligible(q):return Deferred(q.data,q.scale,q.zero,True,getattr(q,'factor',1))
        return super().relu(q)

    def resize(self,q):
        if self.eligible(q):return Deferred(q.data,q.scale,q.zero,getattr(q,'clamp',False),getattr(q,'factor',1)*2)
        return super().resize(q)

    def pool(self,q):
        if isinstance(q,Deferred) and q.factor==1:
            # max(max(x, zero)) == max(max(x), zero), so postpone the clamp.
            result=super().pool(Quantized(q.data,q.scale,q.zero))
            return Deferred(result.data,q.scale,q.zero,q.clamp)
        if isinstance(q,Deferred):q=Quantized(self.quantize(q,q.scale,q.zero),q.scale,q.zero)
        return super().pool(q)

    def pool_quantize(self,q,scale,zero,axis=1):
        if self.eligible(q) and getattr(q,'factor',1)==1 and scale.size==zero.size==1 and zero.dtype==np.int8:
            data=self.hwc(q.data);h,w,c=data.shape
            assert h%2==w%2==0
            out=self.empty((h//2,w//2,c));table=self.table(q,scale,zero)[1]
            # Select the signed maximum first, then apply the original float32
            # dequantize/clamp/requantize LUT exactly once to that maximum.
            self.ops.ct_pool_transform(data.ctypes.data,out.ctypes.data,h,w,c,table.ctypes.data)
            return self.nchw(out)
        return super().pool_quantize(q,scale,zero,axis)

    @staticmethod
    def floating(q):
        if isinstance(q,Deferred):
            data=np.maximum(q.data,q.zero) if q.clamp else q.data
            if q.factor!=1:data=data.repeat(q.factor,axis=2).repeat(q.factor,axis=3)
            q=Quantized(data,q.scale,q.zero)
        if isinstance(q,Concatenated):return np.concatenate([StreamGraph.floating(v) for v in q.values],axis=q.axis)
        return NativeGraph.floating(q)


class MappedGraph(StreamGraph):
    """PS transforms write into leased, cacheable XRT buffers ready for DMA."""
    def empty(self,shape):return self.backend.allocate_activation(shape)


class ContextPreparer:
    def __init__(self,graph,ct,spacing_z=None):
        if ct.ndim!=3 or not np.issubdtype(ct.dtype,np.integer):raise ValueError('Integer HU ZYX CT required')
        if ct.dtype!=np.int16:ct=np.clip(ct,-1000,400).astype(np.int16)
        self.ct=np.ascontiguousarray(ct);self.spacing_z=spacing_z;self.graph=graph
        self.planes={}
        first=next(n for n in graph.nodes if n['op']=='QuantizeLinear' and n['inputs'][0]==graph.plan['input'])
        self.scale,self.zero=[graph.arrays[n] for n in first['inputs'][1:]]
        assert self.scale.size==self.zero.size==1 and self.zero.dtype==np.int8
        hu=np.arange(65536,dtype=np.uint16).view(np.int16)
        normalized=(np.clip(hu.astype(np.float32),-1000,400)+1000)/1400
        self.table=np.clip(np.rint(normalized/self.scale)+self.zero,-128,127).astype(np.int8)

    def __call__(self,z):
        ct=self.ct;_,h,w=ct.shape;hp=(h+7)//8*8;wp=(w+7)//8*8
        indices=context_indices(z,len(ct),self.spacing_z) if self.spacing_z is not None else np.clip(np.arange(z-2,z+3),0,len(ct)-1)
        # Adjacent contexts reuse source slices; retain only this context's planes.
        self.planes={i:q for i,q in self.planes.items() if i in indices}
        for i in indices:
            if i not in self.planes:
                q=np.empty((h,w),np.int8)
                self.graph.ops.ct_hu_lut(ct[i].ctypes.data,q.ctypes.data,q.size,self.table.ctypes.data)
                self.planes[i]=q
        out=np.empty((hp,wp,8),np.int8)
        pointers=[self.planes[i].ctypes.data for i in indices]
        self.graph.ops.ct_context5(*pointers,out.ctypes.data,h,w,hp,wp)
        return Quantized(self.graph.nchw(out[:,:,:5]),self.scale,self.zero)

    def slices(self):
        # One in-flight future plus the current input, with exceptions propagated.
        self.planes.clear() # Each measured volume includes its own cache startup.
        with ThreadPoolExecutor(max_workers=1,thread_name_prefix='ct-context') as pool:
            pending=pool.submit(self,0)
            for z in range(len(self.ct)):
                value=pending.result()
                if z+1<len(self.ct):pending=pool.submit(self,z+1)
                yield z,value
