"""QDQ graph executor. PL backend replaces every convolution; other operators run on PS."""
from collections import Counter
import ctypes
import json
from pathlib import Path
import time
import threading
import numpy as np


def scaled(v,scale,axis=1):
    if scale.size==1:return scale
    shape=[1]*v.ndim;shape[axis]=scale.size
    return scale.reshape(shape)


def pack_weights(w):
    co,ci,k,_=w.shape
    padded=np.zeros(((co+7)//8*8,(ci+3)//4*4,k,k),np.int8);padded[:co,:ci]=w
    # One 256-bit word per [output group, kernel row, kernel col, input group].
    return np.ascontiguousarray(padded.reshape((co+7)//8,8,(ci+3)//4,4,k,k).transpose(0,4,5,2,1,3))


def pack_input(x):
    ci,h,width=x.shape[1:];hwc=x[0].transpose(1,2,0)
    if ci%8==0:return np.ascontiguousarray(hwc)
    base=x.base;padded=(ci+7)//8*8
    # ContextPreparer already owns a padded HWC allocation. Verify the complete
    # allocation and view bounds rather than constructing an unchecked stride view.
    if isinstance(base,np.ndarray) and base.dtype==np.int8 and base.shape==(h,width,padded) and base.flags.c_contiguous and hwc.ctypes.data==base.ctypes.data and hwc.strides==base.strides:
        return base
    inp=np.zeros((h,width,(ci+7)//8*8),np.int8);inp[:,:,:ci]=hwc
    return inp


class TorchInteger:
    """Development oracle: integer-valued FP32 sums below 2**24 are exact here."""
    def __init__(self):
        import torch
        self.torch=torch;torch.set_num_threads(4);self.calls=0
    def conv(self,id,x,w):
        t=self.torch
        with t.no_grad():y=t.nn.functional.conv2d(t.from_numpy(x.astype(np.float32)),t.from_numpy(w.astype(np.float32)),padding=w.shape[2]//2).numpy()
        assert np.max(np.abs(y))<2**24 and np.all(y==np.rint(y))
        self.calls+=1
        return y.astype(np.int32)


class OutputLease:
    """The ctypes storage retains this lease through every NumPy view.

    C++ retains the context/device until the last lease is returned, even if the
    Python backend is explicitly closed. Leased buffers cannot be overwritten.
    """
    def __init__(self,lib,handle):self.lib=lib;self.handle=handle
    def __del__(self):
        if self.handle:self.lib.ct_output_release(self.handle);self.handle=None


class XRTInteger:
    def __init__(self,library,xclbin,pl_quantization=False,output_pool=False):
        self.execution_lock=threading.RLock()
        self.lib=ctypes.CDLL(str(library));L=self.lib
        L.ct_error.restype=ctypes.c_char_p
        L.ct_open.argtypes=[ctypes.c_char_p];L.ct_open.restype=ctypes.c_void_p
        L.ct_add_weights.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t];L.ct_add_weights.restype=ctypes.c_int
        L.ct_execute.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,*([ctypes.c_uint]*5)];L.ct_execute.restype=ctypes.c_int
        L.ct_execute_quantized.argtypes=L.ct_execute.argtypes+[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_float,ctypes.c_int];L.ct_execute_quantized.restype=ctypes.c_int
        L.ct_close.argtypes=[ctypes.c_void_p];L.ct_last_seconds.argtypes=[ctypes.c_void_p];L.ct_last_seconds.restype=ctypes.c_double
        self.output_pool=output_pool
        if output_pool:
            if not pl_quantization:raise ValueError('Mapped output requires PL quantization')
            L.ct_output_acquire.argtypes=[ctypes.c_void_p,ctypes.c_size_t];L.ct_output_acquire.restype=ctypes.c_void_p
            L.ct_output_map.argtypes=[ctypes.c_void_p];L.ct_output_map.restype=ctypes.c_void_p
            L.ct_output_release.argtypes=[ctypes.c_void_p];L.ct_output_release.restype=None
            L.ct_output_mark_ps_written.argtypes=[ctypes.c_void_p];L.ct_output_mark_ps_written.restype=None
            L.ct_execute_mapped.argtypes=L.ct_execute_quantized.argtypes;L.ct_execute_mapped.restype=ctypes.c_int
            L.ct_output_pool_bytes.argtypes=[ctypes.c_void_p];L.ct_output_pool_bytes.restype=ctypes.c_size_t
        if hasattr(L,'ct_last_phase'):
            L.ct_last_phase.argtypes=[ctypes.c_void_p,ctypes.c_uint];L.ct_last_phase.restype=ctypes.c_double
        if hasattr(L,'ct_skipped_sync'):
            L.ct_skipped_sync.argtypes=[ctypes.c_void_p,ctypes.c_uint];L.ct_skipped_sync.restype=ctypes.c_uint64
        self.handle=L.ct_open(str(xclbin).encode());self.ids={};self.quant_params={};self.calls=0;self.hardware_seconds=0.
        if not self.handle:raise RuntimeError(L.ct_error().decode())
        self.pl_quantization=pl_quantization
        self.activation_tables={};self.activation_uploaded=set()
        if pl_quantization:
            L.ct_set_writer_quantization.argtypes=[ctypes.c_void_p,ctypes.c_uint]
            L.ct_set_writer_quantization.restype=None
            L.ct_set_writer_quantization(self.handle,1)
    def conv(self,id,x,w):
        with self.execution_lock:return self._conv(id,x,w)

    def _conv(self,id,x,w):
        assert x.ndim==4 and x.shape[0]==1 and x.dtype==np.int8 and w.dtype==np.int8
        ci,h,width=x.shape[1:];co=w.shape[0];k=w.shape[2]
        if id not in self.ids:
            packed=pack_weights(w);idx=self.lib.ct_add_weights(self.handle,packed.ctypes.data,packed.nbytes)
            if idx<0:raise RuntimeError(self.lib.ct_error().decode())
            self.ids[id]=idx
        inp=pack_input(x)
        out=np.empty((h,width,(co+7)//8*8),np.int32)
        rc=self.lib.ct_execute(self.handle,self.ids[id],inp.ctypes.data,out.ctypes.data,h,width,ci,co,k)
        if rc:raise RuntimeError(self.lib.ct_error().decode())
        self.calls+=1;self.hardware_seconds+=self.lib.ct_last_seconds(self.handle)
        return out[:,:,:co].transpose(2,0,1)[None]
    def close(self):
        if self.handle:self.lib.ct_close(self.handle);self.handle=None

    def _mapped_array(self,shape):
        if not self.handle or not self.output_pool:raise RuntimeError('Mapped backend is not open')
        count=int(np.prod(shape));handle=self.lib.ct_output_acquire(self.handle,(count+31)//32*32)
        if not handle:raise RuntimeError(self.lib.ct_error().decode())
        lease=OutputLease(self.lib,handle);ptr=self.lib.ct_output_map(handle)
        if not ptr:raise RuntimeError(self.lib.ct_error().decode())
        storage=(ctypes.c_int8*count).from_address(ptr);storage._lease=lease
        return np.ctypeslib.as_array(storage).reshape(shape),handle

    def allocate_activation(self,shape):
        out,handle=self._mapped_array(shape)
        self.lib.ct_output_mark_ps_written(handle)
        return out

    def configure_activation(self,id,table):
        if not getattr(self,'pl_activation_lut',False):raise RuntimeError('Loaded writer does not support activation fusion')
        if id in self.quant_params:raise RuntimeError('Configure activation before executing layer')
        table=np.ascontiguousarray(table,dtype=np.int8)
        if table.shape!=(256,):raise ValueError('Expected 256-entry INT8 activation table')
        if id in self.activation_tables and not np.array_equal(table,self.activation_tables[id]):raise ValueError('Conflicting activation table')
        self.activation_tables[id]=table

    def conv_quantized(self,id,x,w,bias,scale,qscale,zero):
        with self.execution_lock:return self._conv_quantized(id,x,w,bias,scale,qscale,zero)

    def _conv_quantized(self,id,x,w,bias,scale,qscale,zero):
        assert x.ndim==4 and x.shape[0]==1 and x.dtype==np.int8 and w.dtype==np.int8
        ci,h,width=x.shape[1:];co=w.shape[0];k=w.shape[2];padded=(co+7)//8*8
        if id not in self.ids:
            packed=pack_weights(w);idx=self.lib.ct_add_weights(self.handle,packed.ctypes.data,packed.nbytes)
            if idx<0:raise RuntimeError(self.lib.ct_error().decode())
            self.ids[id]=idx
        if id not in self.quant_params:
            if id in self.activation_tables and id not in self.activation_uploaded:
                fn=self.lib.ct_set_activation_lut
                fn.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p];fn.restype=ctypes.c_int
                if fn(self.handle,self.ids[id],self.activation_tables[id].ctypes.data):raise RuntimeError(self.lib.ct_error().decode())
                self.activation_uploaded.add(id)
            bp=np.zeros(padded,np.int32);sp=np.zeros(padded,np.float32)
            bp[:co]=bias;sp[:co]=scale;self.quant_params[id]=(bp,sp)
        bp,sp=self.quant_params[id]
        inp=pack_input(x)
        if self.output_pool:
            out,lease_handle=self._mapped_array((h,width,padded))
            rc=self.lib.ct_execute_mapped(self.handle,self.ids[id],inp.ctypes.data,lease_handle,h,width,ci,co,k,bp.ctypes.data,sp.ctypes.data,float(qscale.item()),int(zero.item()))
        else:
            out=np.empty((h,width,padded),np.int8)
            rc=self.lib.ct_execute_quantized(self.handle,self.ids[id],inp.ctypes.data,out.ctypes.data,h,width,ci,co,k,bp.ctypes.data,sp.ctypes.data,float(qscale.item()),int(zero.item()))
        if rc:raise RuntimeError(self.lib.ct_error().decode())
        self.calls+=1;self.hardware_seconds+=self.lib.ct_last_seconds(self.handle)
        if self.output_pool:out.flags.writeable=False
        return out[:,:,:co].transpose(2,0,1)[None]


class Graph:
    def __init__(self,folder,backend):
        folder=Path(folder);self.plan=json.loads((folder/'graph.json').read_text());self.arrays=dict(np.load(folder/'tensors.npz',allow_pickle=False));self.backend=backend
        # Integer convolution reads its quantized input and constant parameters directly.
        # Remove the now-unused activation/weight/bias dequantization nodes rather than
        # allocating full floating-point feature maps that are immediately discarded.
        needed={self.plan['output']};kept=[]
        for node in reversed(self.plan['nodes']):
            if any(name in needed for name in node['outputs']):
                kept.append(node);needed.update(self.dependencies(node))
        self.nodes=list(reversed(kept))
        self.uses=Counter()
        for n in self.nodes:
            self.uses.update(self.dependencies(n))
    def dependencies(self,n):
        if 'integer' in n:return [n['integer']['input']]
        return [i for i in n['inputs'] if i]
    def __call__(self,x,callback=None):
        assert x.ndim==4 and x.shape[0]==1 and x.shape[2]%8==0 and x.shape[3]%8==0
        env={**self.arrays,self.plan['input']:x};uses=self.uses.copy()
        for n in self.nodes:
            op=n['op'];a=n['attrs'];v=[env.get(i) for i in n['inputs']]
            if op=='Constant':y=self.arrays[a['value']['tensor']]
            elif op=='QuantizeLinear':
                s=scaled(v[0],v[1],a.get('axis',1));zero=scaled(v[0],v[2],a.get('axis',1));bounds=np.iinfo(v[2].dtype)
                y=np.clip(np.rint(v[0]/s)+zero,bounds.min,bounds.max).astype(v[2].dtype)
            elif op=='DequantizeLinear':
                y=(v[0].astype(np.float32)-scaled(v[0],v[2],a.get('axis',1)))*scaled(v[0],v[1],a.get('axis',1))
            elif op=='Conv':
                c=n['integer'];qx=env[c['input']];qw=self.arrays[c['weights']]
                acc=self.backend.conv(c['id'],qx,qw)
                if callback:callback(c['id'],qx,qw,acc)
                acc=acc+self.arrays[c['bias']][None,:,None,None]
                scale=self.arrays[c['input_scale']]*self.arrays[c['weight_scale']]
                y=acc.astype(np.float32)*scale.reshape(1,-1,1,1)
            elif op=='Relu':y=np.maximum(v[0],np.float32(0))
            elif op=='Concat':y=np.concatenate(v,axis=a['axis'])
            elif op=='MaxPool':
                b,c,h,w=v[0].shape;assert h%2==0 and w%2==0
                y=v[0].reshape(b,c,h//2,2,w//2,2).max(axis=(3,5))
            elif op=='Resize':
                assert np.array_equal(v[2],np.array([1,1,2,2]))
                y=v[0].repeat(2,axis=2).repeat(2,axis=3)
            else:raise ValueError(op)
            assert len(n['outputs'])==1
            env[n['outputs'][0]]=y
            for i in self.dependencies(n):
                uses[i]-=1
                if uses[i]==0 and i not in self.arrays and i!=self.plan['output']:env.pop(i,None)
        return env[self.plan['output']]
