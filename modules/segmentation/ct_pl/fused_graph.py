"""Compile single-consumer Conv/Q/DQ/ReLU/Q chains into the PL writer LUT.

Both original quantization steps remain exact. Fan-out tensors, pool, resize
and concat stay on the existing scheduler, so skip connections are unchanged.
"""
from collections import Counter
import numpy as np
from .stream_graph import MappedGraph,Deferred


class FusedGraph(MappedGraph):
    def __init__(self,folder,backend,library=None):
        super().__init__(folder,backend,library)
        if not getattr(backend,'pl_activation_lut',False):
            raise RuntimeError('Activation fusion requires a verified LUT-capable writer')
        self.fused_layers=[];nodes=[];i=0
        while i<len(self.nodes):
            chain=self.nodes[i:i+4]
            if len(chain)==4 and [n['op'] for n in chain]==['Conv','DequantizeLinear','Relu','QuantizeLinear']:
                conv,dq,relu,q=chain
                linked=all(b['inputs'][0]==a['outputs'][0] and self.uses[a['outputs'][0]]==1 for a,b in zip(chain,chain[1:]))
                if linked and 'fused_quant' in conv and conv['fused_quant']==dq['inputs'][1:]:
                    source_scale,source_zero=[self.arrays[n] for n in conv['fused_quant']]
                    scale,zero=[self.arrays[n] for n in q['inputs'][1:]]
                    if source_scale.size==source_zero.size==scale.size==zero.size==1 and source_zero.dtype==zero.dtype==np.int8 and source_scale.item()>0 and scale.item()>0:
                        raw=np.arange(256,dtype=np.uint8).view(np.int8)
                        source=Deferred(raw,source_scale,source_zero,True,1)
                        table=self.table(source,scale,zero)[1]
                        backend.configure_activation(conv['integer']['id'],table)
                        nodes.append({**conv,'outputs':q['outputs'],'fused_activation':True})
                        self.fused_layers.append(conv['integer']['id']);i+=4;continue
            nodes.append(self.nodes[i]);i+=1
        self.nodes=nodes;self.uses=Counter()
        for n in nodes:self.uses.update(self.dependencies(n))
