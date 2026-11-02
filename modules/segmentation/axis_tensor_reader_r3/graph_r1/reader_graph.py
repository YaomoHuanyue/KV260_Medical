"""Keep reader transforms deferred through Conv; never materialize them on PS."""
from dataclasses import dataclass
import numpy as np
from modules.segmentation.ct_pool_fusion_r1.integration_r1.pool_graph import PoolGraph
from ct_pl.quantized_runtime import Quantized,Concatenated


@dataclass(frozen=True)
class ReaderSource:
    data: np.ndarray
    factor: int

    def __post_init__(self):
        a=self.data
        if not isinstance(a,np.ndarray) or a.dtype!=np.int8 or a.ndim!=4 or a.shape[0]!=1:
            raise ValueError('Reader source requires an INT8 NCHW tensor')
        c,h,w=map(int,a.shape[1:]);padded=(c+7)//8*8
        if not (1<=c<=64 and h>=1 and w>=1 and self.factor in (1,2)):
            raise ValueError('Unsupported reader source geometry or scale')
        # Only inspect strides and retain the original array/BO lease. A source
        # requiring a bulk layout conversion must be rejected, not copied here.
        hwc=a[0].transpose(1,2,0)
        if tuple(hwc.strides)!=(w*padded,padded,1):
            raise ValueError('Reader source must already use padded HWC storage')

    @property
    def channels(self):return int(self.data.shape[1])

    @property
    def output_hw(self):return tuple(int(v)*self.factor for v in self.data.shape[2:])


@dataclass(frozen=True)
class ReaderInput:
    sources: tuple
    tables: np.ndarray

    def __post_init__(self):
        if len(self.sources) not in (1,2) or not all(isinstance(s,ReaderSource) for s in self.sources):
            raise ValueError('Reader requires one or two typed sources')
        hw=self.sources[0].output_hw
        if any(s.output_hw!=hw for s in self.sources) or not all(1<=v<=512 for v in hw):
            raise ValueError('Reader output dimensions disagree or exceed512')
        if sum(s.channels for s in self.sources)>64:raise ValueError('Reader channels exceed64')
        t=self.tables
        if not isinstance(t,np.ndarray) or t.dtype!=np.int8 or t.shape!=(len(self.sources),256):
            raise ValueError('Reader requires exactly256 INT8 LUT entries per source')
        # At most512 bytes of control data; source tensor storage remains shared.
        t=np.array(t,dtype=np.int8,order='C',copy=True);t.flags.writeable=False
        object.__setattr__(self,'tables',t)

    @property
    def shape(self):return (1,sum(s.channels for s in self.sources),*self.sources[0].output_hw)

    @property
    def ndim(self):return 4

    @property
    def dtype(self):return np.dtype('int8')

    @property
    def mode(self):return len(self.sources)

    def __array__(self,*args,**kwargs):
        raise TypeError('Deferred reader input must execute in PL; PS materialization is disabled')


class ReaderDispatch:
    def __init__(self,backend):self.backend=backend

    def __getattr__(self,name):return getattr(self.backend,name)

    def conv_quantized(self,index,x,*args):
        if isinstance(x,ReaderInput):return self.backend.conv_quantized_reader(index,x,*args)
        return self.backend.conv_quantized(index,x,*args)

    def conv_quantized_pool(self,index,x,*args):
        if isinstance(x,ReaderInput):return self.backend.conv_quantized_pool_reader(index,x,*args)
        return self.backend.conv_quantized_pool(index,x,*args)


class ReaderGraph(PoolGraph):
    def __init__(self,folder,backend,library=None):
        if not getattr(backend,'pl_tensor_reader',False) or not all(callable(getattr(backend,n,None)) for n in
            ('conv_quantized_reader','conv_quantized_pool_reader')):
            raise RuntimeError('Qualified PL reader backend required; PS transform fallback is disabled')
        super().__init__(folder,ReaderDispatch(backend),library)
        consumers={}
        for node in self.nodes:
            for n in self.dependencies(node):consumers.setdefault(n,[]).append(node)
        migrated=[]
        for node in self.nodes:
            if node['op']!='QuantizeLinear':continue
            output=node['outputs'][0];uses=consumers.get(output,[])
            if len(uses)!=1 or uses[0]['op'] not in ('Conv','ConvPool') or uses[0]['integer']['input']!=output:
                raise ValueError('Reader transforms require one direct convolution consumer')
            migrated.append(dict(quantize=node['name'] if 'name' in node else output,
                output=output,conv_id=uses[0]['integer']['id']))
        self.reader_quantizations=migrated

    @staticmethod
    def source(value):
        if not isinstance(value,Quantized) or value.data.dtype!=np.int8 or value.zero.dtype!=np.int8:
            raise ValueError('Reader transform requires signed INT8 source quantization')
        if value.scale.dtype!=np.float32 or value.scale.size!=value.zero.size or value.scale.size!=1:
            raise ValueError('Reader transform requires scalar FP32 quantization')
        if not np.isfinite(value.scale.item()) or value.scale.item()<=0:raise ValueError('Invalid source scale')
        return ReaderSource(value.data,getattr(value,'factor',1))

    def quantize(self,value,scale,zero,axis=1):
        if axis!=1 or scale.dtype!=np.float32 or scale.size!=1 or zero.dtype!=np.int8 or zero.size!=1:
            raise ValueError('Reader transform requires scalar FP32/INT8 quantization on channels')
        if not np.isfinite(scale.item()) or scale.item()<=0:raise ValueError('Invalid target scale')
        if isinstance(value,Concatenated):
            if value.axis!=1 or len(value.values)!=2:raise ValueError('Reader requires exactly two channel branches')
            sources=tuple(self.source(v) for v in value.values)
            tables=np.stack([self.table(v,scale,zero)[1] for v in value.values])
            return ReaderInput(sources,tables)
        source=self.source(value);key,table=self.table(value,scale,zero)
        if key in self.identity_tables and source.factor==1:return value.data
        return ReaderInput((source,),table[None])
