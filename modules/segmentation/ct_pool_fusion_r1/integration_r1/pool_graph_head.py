"""Candidate graph with real dual-output writer calls; formal entry is unchanged."""
from collections import Counter
from pathlib import Path
import hashlib,json
import numpy as np
from ct_pl.fused_graph import FusedGraph
from ct_pl.stream_graph import Deferred
from ct_pl.quantized_runtime import Quantized,Concatenated
from ct_pl.runtime import scaled


class PoolGraph(FusedGraph):
    def __init__(self,folder,backend,library=None):
        if not getattr(backend,'pl_pool_fusion',False) or not callable(getattr(backend,'conv_quantized_pool',None)):
            raise RuntimeError('Dual-output PL pool capability is required; PS pool fallback is disabled')
        core=Path(__file__).resolve().parent.parent
        metadata=json.loads((core/'model_tables.json').read_text())
        folder=Path(folder)
        for leaf in ('graph.json','tensors.npz'):
            source=next((n,h) for n,h in metadata['source_and_evidence_SHA256'].items() if n.endswith('/'+leaf))
            with (folder/leaf).open('rb') as f:
                if hashlib.file_digest(f,'sha256').hexdigest()!=source[1]:raise ValueError('Pool graph requires the frozen current model: '+leaf)
        super().__init__(folder,backend,library)
        producers={name:node for node in self.nodes for name in node['outputs']}
        expected={row['conv_id']:row for row in metadata['exact_model_pool_chains']}
        replacements={};remove=set();migrated=[]
        for pool in self.nodes:
            if pool['op']!='PoolQuantize':continue
            relu=producers.get(pool['inputs'][0],{})
            dq=producers.get(relu.get('inputs',[''])[0],{})
            conv=producers.get(dq.get('inputs',[''])[0],{})
            if relu.get('op')!='Relu' or dq.get('op')!='DequantizeLinear' or conv.get('op')!='Conv' or 'fused_quant' not in conv:
                raise ValueError('Unsupported producer chain for PL pool')
            layer=conv['integer']['id']
            if layer not in expected or layer in replacements or conv.get('fused_activation'):
                raise ValueError('Ambiguous pool producer or LUT-before-pool transform')
            if dq['inputs'][1:]!=conv['fused_quant']:
                raise ValueError('Producer and pool quantization disagree')
            source_scale,source_zero=[self.arrays[name] for name in conv['fused_quant']]
            scale,zero=[self.arrays[name] for name in pool['inputs'][1:]]
            if not (source_scale.size==source_zero.size==scale.size==zero.size==1 and source_zero.dtype==zero.dtype==np.int8):
                raise ValueError('Pool graph requires scalar INT8 quantization')
            raw=np.arange(256,dtype=np.uint8).view(np.int8)
            table=self.table(Deferred(raw,source_scale,source_zero,True,1),scale,zero)[1].copy()
            if hashlib.sha256(table.tobytes()).hexdigest()!=expected[layer]['table_SHA256']:
                raise ValueError('Pool LUT differs from independently frozen model')
            channels=self.arrays[conv['integer']['weights']].shape[0]
            if channels!=expected[layer]['channels']:raise ValueError('Pool channel count differs')
            if len(conv['outputs'])!=1 or len(pool['outputs'])!=1:raise ValueError('Unexpected original outputs')
            replacement={**conv,'op':'ConvPool','outputs':[conv['outputs'][0],pool['outputs'][0]],
                'pool_quant':pool['inputs'][1:]}
            replacements[layer]=replacement;remove.add(pool['outputs'][0])
            migrated.append(dict(conv_id=layer,channels=channels,full_skip=conv['outputs'][0],
                pooled=pool['outputs'][0],pool_LUT_SHA256=expected[layer]['table_SHA256']))
            backend.configure_pool(layer,table)
        if set(replacements)!=set(expected):raise RuntimeError('All three original pools must use the PL writer')
        nodes=[]
        for node in self.nodes:
            if node['op']=='PoolQuantize' and node['outputs'][0] in remove:continue
            if node.get('integer',{}).get('id') in replacements and node['op']=='Conv':
                node=replacements[node['integer']['id']]
            nodes.append(node)
        # Remove only nodes made dead by producer-side pool fusion. Preserve
        # original full-resolution consumers, including all U-Net skip branches.
        needed={self.plan['output']};kept=[]
        for node in reversed(nodes):
            if any(name in needed for name in node['outputs']):
                kept.append(node);needed.update(self.dependencies(node))
        self.nodes=list(reversed(kept));self.uses=Counter()
        for node in self.nodes:self.uses.update(self.dependencies(node))
        if any(node['op'] in ('MaxPool','PoolQuantize') for node in self.nodes):
            raise RuntimeError('A PS pool operator survived PL pool compilation')
        self.pl_fused_pools=sorted(migrated,key=lambda row:row['conv_id']);self.fused_pools=[]

    def pool(self,*args):
        raise RuntimeError('PS pool fallback is forbidden in the dual-output graph')

    def pool_quantize(self,*args):
        raise RuntimeError('PS pool fallback is forbidden in the dual-output graph')

