"""Optional PS graph scheduler retaining quantized activations between PL calls.

LUTs reproduce the original float32 dequantize/requantize sequence, including
nearest-even rounding. Convolution math and the PL register ABI are unchanged.
"""
from dataclasses import dataclass
from collections import Counter
import numpy as np
from .runtime import Graph,scaled


@dataclass
class Quantized:
    data: np.ndarray
    scale: np.ndarray
    zero: np.ndarray


@dataclass
class Concatenated:
    values: list
    axis: int


class QuantizedGraph(Graph):
    def __init__(self,folder,backend):
        super().__init__(folder,backend)
        self.tables={}
        if hasattr(backend,'conv_quantized'):
            nodes=[];i=0
            while i<len(self.nodes):
                n=self.nodes[i]
                q=self.nodes[i+1] if i+1<len(self.nodes) else None
                if n['op']=='Conv' and q and q['op']=='QuantizeLinear' and q['inputs'][0]==n['outputs'][0] and self.uses[n['outputs'][0]]==1:
                    scale,zero=[self.arrays[name] for name in q['inputs'][1:]]
                    if scale.size==zero.size==1 and zero.dtype==np.int8:
                        n={**n,'outputs':q['outputs'],'fused_quant':q['inputs'][1:]};i+=1
                nodes.append(n);i+=1
            self.nodes=nodes;self.uses=Counter()
            for n in self.nodes:self.uses.update(self.dependencies(n))

    @staticmethod
    def floating(value):
        if isinstance(value,Quantized):
            return (value.data.astype(np.float32)-value.zero)*value.scale
        if isinstance(value,Concatenated):
            return np.concatenate([QuantizedGraph.floating(v) for v in value.values],axis=value.axis)
        return value

    def quantize(self,value,scale,zero,axis=1):
        if isinstance(value,Concatenated) and scale.size==zero.size==1:
            return np.concatenate([self.quantize(v,scale,zero,axis) for v in value.values],axis=value.axis)
        if isinstance(value,Quantized) and value.scale.size==value.zero.size==scale.size==zero.size==1:
            key=(value.data.dtype.str,value.scale.tobytes(),value.zero.tobytes(),scale.tobytes(),zero.dtype.str,zero.tobytes())
            if key not in self.tables:
                raw=np.arange(256,dtype=np.uint8).view(value.data.dtype)
                f=(raw.astype(np.float32)-value.zero)*value.scale
                bounds=np.iinfo(zero.dtype)
                self.tables[key]=np.clip(np.rint(f/scale)+zero,bounds.min,bounds.max).astype(zero.dtype)
            return self.tables[key][value.data.view(np.uint8)]
        value=self.floating(value)
        bounds=np.iinfo(zero.dtype)
        # A private scratch preserves fan-out tensors, while avoiding four large
        # temporary arrays for divide, rounding, offset, and clipping.
        work=np.divide(value,scaled(value,scale,axis))
        np.rint(work,out=work)
        np.add(work,scaled(value,zero,axis),out=work)
        np.clip(work,bounds.min,bounds.max,out=work)
        return work.astype(zero.dtype)

    def relu(self,value):
        if isinstance(value,Quantized) and np.all(value.scale>0):
            return Quantized(np.maximum(value.data,value.zero),value.scale,value.zero)
        return np.maximum(self.floating(value),np.float32(0))

    def pool(self,q):
        data=q.data if isinstance(q,Quantized) else self.floating(q)
        b,c,h,w=data.shape;assert h%2==0 and w%2==0
        pooled=data.reshape(b,c,h//2,2,w//2,2).max(axis=(3,5))
        return Quantized(pooled,q.scale,q.zero) if isinstance(q,Quantized) else pooled

    def resize(self,q):
        data=q.data if isinstance(q,Quantized) else self.floating(q)
        resized=data.repeat(2,axis=2).repeat(2,axis=3)
        return Quantized(resized,q.scale,q.zero) if isinstance(q,Quantized) else resized

    def pool_quantize(self,q,scale,zero,axis=1):
        return self.quantize(self.pool(q),scale,zero,axis)

    def __call__(self,x,callback=None):
        shape=x.data.shape if isinstance(x,Quantized) else x.shape
        assert len(shape)==4 and shape[0]==1 and shape[2]%8==0 and shape[3]%8==0
        env={**self.arrays,self.plan['input']:x};uses=self.uses.copy()
        for n in self.nodes:
            op=n['op'];a=n['attrs'];v=[env.get(i) for i in n['inputs']]
            if op=='Constant':y=self.arrays[a['value']['tensor']]
            elif op=='QuantizeLinear':y=self.quantize(v[0],v[1],v[2],a.get('axis',1))
            elif op=='DequantizeLinear':
                if v[1].size==v[2].size==1 and v[0].dtype in (np.int8,np.uint8):
                    y=Quantized(v[0],v[1],v[2])
                else:y=(v[0].astype(np.float32)-scaled(v[0],v[2],a.get('axis',1)))*scaled(v[0],v[1],a.get('axis',1))
            elif op=='Conv':
                c=n['integer'];qx=env[c['input']];qw=self.arrays[c['weights']]
                scale=self.arrays[c['input_scale']]*self.arrays[c['weight_scale']]
                if 'fused_quant' in n:
                    if callback:raise ValueError('Integer accumulator callback requires the unfused scheduler')
                    qs,qz=[self.arrays[name] for name in n['fused_quant']]
                    y=self.backend.conv_quantized(c['id'],qx,qw,self.arrays[c['bias']],scale,qs,qz)
                else:
                    acc=self.backend.conv(c['id'],qx,qw)
                    if callback:callback(c['id'],qx,qw,acc)
                    np.add(acc,self.arrays[c['bias']][None,:,None,None],out=acc)
                    y=acc.astype(np.float32)
                    np.multiply(y,scale.reshape(1,-1,1,1),out=y)
            elif op=='Relu':
                y=self.relu(v[0])
            elif op=='Concat':y=Concatenated(v,a['axis'])
            elif op=='MaxPool':
                y=self.pool(v[0])
            elif op=='PoolQuantize':
                y=self.pool_quantize(v[0],v[1],v[2],a.get('axis',1))
            elif op=='Resize':
                assert np.array_equal(v[2],np.array([1,1,2,2]))
                y=self.resize(v[0])
            else:raise ValueError(op)
            assert len(n['outputs'])==1
            env[n['outputs'][0]]=y
            for i in self.dependencies(n):
                uses[i]-=1
                if uses[i]==0 and i not in self.arrays and i!=self.plan['output']:env.pop(i,None)
        output=env[self.plan['output']]
        if getattr(self,'return_quantized',False) and isinstance(output,Quantized):return output
        return self.floating(output)
