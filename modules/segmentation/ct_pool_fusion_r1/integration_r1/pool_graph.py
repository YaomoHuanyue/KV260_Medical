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
            elif op in ('Conv','ConvPool'):
                c=n['integer'];qx=env[c['input']];qw=self.arrays[c['weights']]
                scale=self.arrays[c['input_scale']]*self.arrays[c['weight_scale']]
                if 'fused_quant' in n:
                    if callback:raise ValueError('Integer accumulator callback requires the unfused scheduler')
                    qs,qz=[self.arrays[name] for name in n['fused_quant']]
                    if op=='ConvPool':
                        y=self.backend.conv_quantized_pool(c['id'],qx,qw,self.arrays[c['bias']],scale,qs,qz)
                    else:
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
            if op=='ConvPool':
                if len(n['outputs'])!=2 or not isinstance(y,tuple) or len(y)!=2:raise RuntimeError('Dual-output backend contract violated')
                for name,value in zip(n['outputs'],y):env[name]=value
            else:
                assert len(n['outputs'])==1
                env[n['outputs'][0]]=y
            for i in self.dependencies(n):
                uses[i]-=1
                if uses[i]==0 and i not in self.arrays and i!=self.plan['output']:env.pop(i,None)
        output=env[self.plan['output']]
        if getattr(self,'return_quantized',False) and isinstance(output,Quantized):return output
        return self.floating(output)
