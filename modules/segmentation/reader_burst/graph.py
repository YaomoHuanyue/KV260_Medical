"""Exact Q15-only PL tensor reader policy; no admission or benchmark imports."""
Q_INPUT='/up0/Concat_output_0_QuantizeLinear_Output'
Q_SCALE='/up0/Concat_output_0_scale'
Q_ZERO='/up0/Concat_output_0_zero_point'


def require(ok,message):
    if not ok:raise ValueError(message)


def make_graph(np,FusedGraph,Concatenated,ReaderInput,ReaderGraph):
    class Q15Dispatch:
        def __init__(self,backend):self.backend=backend
        def __getattr__(self,name):return getattr(self.backend,name)
        def conv_quantized(self,index,x,*args):
            if isinstance(x,ReaderInput):
                require(index==15 and x.mode==2 and x.shape==(1,32,512,512),'Only qualified Q15 may use PL reader')
                return self.backend.conv_quantized_reader(index,x,*args)
            require(index!=15,'Selected Q15 cannot silently use PS join')
            return self.backend.conv_quantized(index,x,*args)
    class Q15OnlyFusedGraph(FusedGraph):
        def __init__(self,folder,backend,library=None):
            require(getattr(backend,'pl_tensor_reader',False),'Qualified native reader required')
            super().__init__(folder,Q15Dispatch(backend),library)
            qs=[n for n in self.nodes if n['op']=='QuantizeLinear'and n['outputs']==[Q_INPUT]]
            uses=[n for n in self.nodes if Q_INPUT in self.dependencies(n)]
            require(len(qs)==len(uses)==1 and uses[0]['op']=='Conv'and uses[0]['integer']['id']==15
                    and uses[0]['integer']['input']==Q_INPUT and uses[0].get('fused_activation')is True,
                    'Unique original Q15 Conv15 boundary required')
            require(qs[0]['inputs'][1:]==[Q_SCALE,Q_ZERO]and len(self.fused_layers)==8 and len(self.fused_pools)==3
                    and sum(n['op']=='PoolQuantize'for n in self.nodes)==3 and not any(n['op']=='ConvPool'for n in self.nodes),
                    'Original eight-activation/three-PS-pool FusedGraph policy changed')
            require(tuple(self.arrays[uses[0]['integer']['weights']].shape)==(16,32,3,3),'Original Conv15 weights required')
            self.q15_scale,self.q15_zero=self.arrays[Q_SCALE],self.arrays[Q_ZERO]
        def quantize(self,value,scale,zero,axis=1):
            if scale is not self.q15_scale or zero is not self.q15_zero:return super().quantize(value,scale,zero,axis)
            require(axis==1 and isinstance(value,Concatenated)and value.axis==1 and len(value.values)==2,'Original dual channel join required')
            require(all(tuple(v.data.shape)==(1,16,512,512)and getattr(v,'factor',1)==1 for v in value.values)
                    and tuple(bool(getattr(v,'clamp',False))for v in value.values)==(False,True),'Q15 fastpath shape/factor/order changed')
            return ReaderInput(tuple(ReaderGraph.source(v)for v in value.values),np.stack([self.table(v,scale,zero)[1]for v in value.values]))
    return Q15OnlyFusedGraph


def get_graph_type():
    import numpy as np
    from ct_pl.fused_graph import FusedGraph
    from ct_pl.quantized_runtime import Concatenated
    from modules.segmentation.axis_tensor_reader_r3.graph_r1.reader_graph import ReaderGraph,ReaderInput
    return make_graph(np,FusedGraph,Concatenated,ReaderInput,ReaderGraph)
