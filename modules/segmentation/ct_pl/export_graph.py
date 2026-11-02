"""Freeze supported ONNX QDQ graph into a small auditable execution plan."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import onnx
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=ROOT/'outputs/ct_student_refined/int8/experimental_student_int8.onnx')
    p.add_argument('--output',type=Path,default=ROOT/'ct_pl/model')
    p.add_argument('--physical-context',action='store_true')
    a=p.parse_args();src=a.source;out=a.output;out.mkdir(parents=True,exist_ok=True)
    m=onnx.load(src);onnx.checker.check_model(m)
    arrays={t.name:onnx.numpy_helper.to_array(t) for t in m.graph.initializer}
    producer={o:n for n in m.graph.node for o in n.output}
    nodes=[];conv_count=0
    for n in m.graph.node:
        attrs={}
        for attribute in n.attribute:
            v=onnx.helper.get_attribute_value(attribute)
            if isinstance(v,onnx.TensorProto):
                key=n.name+'/'+attribute.name;arrays[key]=onnx.numpy_helper.to_array(v);v={'tensor':key}
            elif isinstance(v,bytes):v=v.decode()
            attrs[attribute.name]=v
        node={'name':n.name,'op':n.op_type,'inputs':list(n.input),'outputs':list(n.output),'attrs':attrs}
        assert n.op_type in ['Constant','QuantizeLinear','DequantizeLinear','Conv','Relu','MaxPool','Resize','Concat']
        if n.op_type=='Conv':
            assert attrs['group']==1 and attrs['strides']==[1,1] and attrs['dilations']==[1,1]
            k=attrs['kernel_shape'][0];assert attrs['kernel_shape']==[k,k] and k in [1,3] and attrs['pads']==[k//2]*4
            qx,qw,qb=[producer[i] for i in n.input]
            assert all(q.op_type=='DequantizeLinear' for q in [qx,qw,qb])
            assert all(np.all(arrays[q.input[2]]==0) for q in [qx,qw,qb])
            assert arrays[qw.input[0]].dtype==np.int8 and arrays[qb.input[0]].dtype==np.int32
            assert arrays[qx.input[1]].size==1
            np.testing.assert_allclose(arrays[qb.input[1]],arrays[qx.input[1]]*arrays[qw.input[1]],rtol=1e-6)
            w=arrays[qw.input[0]];assert max(w.shape[:2])<=64
            assert int(np.max(np.abs(arrays[qb.input[0]].astype(np.int64))))+w.shape[1]*k*k*16384<2**31
            node['integer']={'id':conv_count,'input':qx.input[0],'weights':qw.input[0],'bias':qb.input[0],
                'input_scale':qx.input[1],'weight_scale':qw.input[1],'kernel':k}
            conv_count+=1
        if n.op_type=='MaxPool':assert attrs['kernel_shape']==[2,2] and attrs['strides']==[2,2] and attrs['pads']==[0]*4 and not attrs['ceil_mode']
        if n.op_type=='Resize':assert attrs['mode']=='nearest' and attrs['coordinate_transformation_mode']=='asymmetric' and attrs['nearest_mode']=='floor'
        nodes.append(node)
    assert conv_count==18
    np.savez(out/'tensors.npz',**arrays)
    plan={'version':1,'input':m.graph.input[0].name,'output':m.graph.output[0].name,'nodes':nodes,'conv_count':conv_count,
        'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'arithmetic':'symmetric signed INT8, exact INT32 MAC; PS bias/scale/round-even/clamp and non-convolution ops'}
    if a.physical_context:
        plan['preprocessing']={'orientation':'LPS','xy_spacing_mm':.7617189884185791,'preserve_native_z':True,'context_offsets_mm':[-5,-2.5,0,2.5,5]}
        plan['airway_postprocess']='largest_26_connected'
    (out/'graph.json').write_text(json.dumps(plan,indent=2),encoding='utf8');print('exported',conv_count,'convolutions')

if __name__=='__main__':main()
