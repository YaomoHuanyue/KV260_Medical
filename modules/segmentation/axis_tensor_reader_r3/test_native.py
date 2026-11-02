"""Independent full-byte/sideband tests, including the frozen model's three joins."""
from pathlib import Path
import ctypes as C,hashlib,json,os,sys,time
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'tools'));import project_storage
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(a):return hashlib.sha256(a.tobytes()).hexdigest()
def pack(data):
    h,w,c=data.shape;channels=(c+7)//8*8
    output=np.zeros((h,w,channels),np.int8);output[:,:,:c]=data
    flat=output.view(np.uint8).ravel();value=np.zeros((len(flat)+31)//32*32,np.uint8);value[:len(flat)]=flat
    return value
def frame(data,kernel):
    h,w,c=data.shape;g=(c+7)//8
    groups=np.zeros((h,w,g*8),np.int8);groups[:,:,:c]=data
    if kernel==1:
        flat=groups.view(np.uint8).ravel();n=(len(flat)+31)//32
        result=np.zeros((n,32),np.uint8);result.ravel()[:len(flat)]=flat
        keep=np.full(n,0xffffffff,np.uint32)
        if len(flat)%32:keep[-1]=(1<<(len(flat)%32))-1
    else:
        result=np.zeros((h+2,w+2,g,32),np.uint8)
        result[1:-1,1:-1,:,:8]=groups.view(np.uint8).reshape(h,w,g,8)
        result=result.reshape(-1,32);keep=np.full(len(result),255,np.uint32)
    last=np.zeros(len(result),np.uint8);last[-1]=1
    return result,keep,last
def model_cases():
    folder=ROOT/'modules/segmentation/outputs/ct_accuracy_v2/pl_model';plan=json.loads((folder/'graph.json').read_text())
    with np.load(folder/'tensors.npz',allow_pickle=False) as z:arrays={n:z[n].copy() for n in z.files}
    nodes=plan['nodes'];producer={name:n for n in nodes for name in n['outputs']};shapes={plan['input']:(512,512,5)}
    for n in nodes:
        op=n['op'];source=shapes.get(n['inputs'][0]) if n['inputs'] else None
        if op=='Conv':shape=(*source[:2],arrays[n['integer']['weights']].shape[0])
        elif op=='MaxPool':shape=(source[0]//2,source[1]//2,source[2])
        elif op=='Resize':shape=(source[0]*2,source[1]*2,source[2])
        elif op=='Concat':shape=(*source[:2],sum(shapes[name][2] for name in n['inputs']))
        elif op in ('Relu','QuantizeLinear','DequantizeLinear'):shape=source
        else:continue
        for name in n['outputs']:shapes[name]=shape
    def branch(name,target_scale,target_zero):
        factor=1;clamp=False
        while True:
            n=producer[name]
            if n['op']=='Relu':clamp=True
            elif n['op']=='Resize':factor*=2
            elif n['op']=='DequantizeLinear':
                scale,zero=[arrays[s] for s in n['inputs'][1:]]
                raw=np.arange(256,dtype=np.uint8).view(np.int8);data=np.maximum(raw,zero) if clamp else raw
                lut=np.clip(np.rint((data.astype(np.float32)-zero)*scale/target_scale)+target_zero,-128,127).astype(np.int8)
                return factor,lut
            else:raise ValueError('Unexpected frozen model join producer: '+n['op'])
            name=n['inputs'][0]
    result=[]
    for n in nodes:
        if n['op']!='Concat':continue
        q=next(v for v in nodes if v['op']=='QuantizeLinear' and v['inputs'][0]==n['outputs'][0])
        scale,zero=[arrays[s] for s in q['inputs'][1:]]
        h,w,ca=shapes[n['inputs'][0]];cb=shapes[n['inputs'][1]][2]
        fa,ta=branch(n['inputs'][0],scale,zero);fb,tb=branch(n['inputs'][1],scale,zero)
        result.append(dict(name=n['name'],h=h,w=w,ca=ca,cb=cb,fa=fa,fb=fb,tables=np.stack([ta,tb])))
    assert len(result)==3
    return result
def main():
    project_storage.check(1_000_000);assert not (HERE/'native_verified.json').exists()
    compiled=json.loads((HERE/'build_native/compiled.json').read_text())
    for n,h in compiled['source_SHA256'].items():assert sha(ROOT/n)==h,n
    library=HERE/'build_native/candidate.dll';assert sha(library)==compiled['native_library_SHA256']
    dll_path=os.add_dll_directory(str(Path(compiled['compiler_argv'][0]).parent)) if os.name=='nt' else None
    lib=C.CDLL(str(library));fn=lib.tensor_reader_native;p=C.c_void_p;u=C.c_uint32
    fn.argtypes=[p]*7+[u,p,p]+[u]*9;fn.restype=C.c_int
    prior=ROOT/'modules/segmentation/ct_pool_fusion_r1/integration_r1/build_native/candidate.dll'
    prior_proof=json.loads(prior.with_name('compiled.json').read_text());assert sha(prior)==prior_proof['library_SHA256']
    original=C.CDLL(str(prior))
    join=original.ct_join_transform;join.argtypes=[p]*3+[u]*6+[p]*2;join.restype=None
    rng=np.random.default_rng(947923);rows=[];started=time.perf_counter()
    def run(h,w,ca,cb,fa,fb,kernel,mode,tables,label,negative=False,ci_override=None):
        ci=ca+cb if ci_override is None else ci_override
        if negative:a=np.arange(32,dtype=np.uint8);b=a.copy();inputs=None
        else:
            adata=rng.integers(-128,128,size=(h//fa,w//fa,ca),dtype=np.int8)
            bdata=rng.integers(-128,128,size=(h//fb,w//fb,cb),dtype=np.int8) if cb else np.zeros((1,1,1),np.int8)
            a,b=pack(adata),pack(bdata);inputs=(adata,bdata)
        snapshots=[digest(a),digest(b),digest(tables)]
        if not negative:
            if mode==0:expected=adata
            else:
                expected=tables[0][adata.view(np.uint8)].repeat(fa,axis=0).repeat(fa,axis=1)
                if cb:expected=np.concatenate([expected,tables[1][bdata.view(np.uint8)].repeat(fb,axis=0).repeat(fb,axis=1)],axis=2)
            gold,kgold,lgold=frame(expected,kernel);n=len(gold)
        else:n=1
        data=np.full((n+2,32),0xa7,np.uint8);keep=np.full(n+2,0xa7a7a7a7,np.uint32)
        strb=keep.copy();last=np.full(n+2,0xa7,np.uint8);count=u();status=u(0xabcdef)
        rc=fn(a.ctypes.data,b.ctypes.data,tables.ctypes.data,data.ctypes.data+32,
            keep.ctypes.data+4,strb.ctypes.data+4,last.ctypes.data+1,n,C.byref(count),C.byref(status),
            h,w,ci,kernel,mode,ca,cb,fa,fb)
        assert rc==0
        assert np.all(data[[0,-1]]==0xa7) and np.all(keep[[0,-1]]==0xa7a7a7a7) and np.all(strb[[0,-1]]==0xa7a7a7a7) and np.all(last[[0,-1]]==0xa7)
        assert [digest(a),digest(b),digest(tables)]==snapshots
        if negative:assert status.value==1 and count.value==0 and np.all(data==0xa7)
        else:
            assert status.value==0 and count.value==n
            np.testing.assert_array_equal(data[1:-1],gold)
            np.testing.assert_array_equal(keep[1:-1],kgold);np.testing.assert_array_equal(strb[1:-1],kgold)
            np.testing.assert_array_equal(last[1:-1],lgold)
            if label.startswith('model_'):
                before=np.empty((h,w,ci),np.int8)
                join(adata.ctypes.data,bdata.ctypes.data,before.ctypes.data,h,w,ca,cb,fa,fb,tables[0].ctypes.data,tables[1].ctypes.data)
                np.testing.assert_array_equal(expected,before)
        rows.append(dict(label=label,h=h,w=w,ca=ca,cb=cb,fa=fa,fb=fb,kernel=kernel,mode=mode,
            status=status.value,packets=count.value,complete_output_and_keep_strb_last_and_guards_checked=True,
            source_and_tables_immutable=True,output_SHA256=digest(data[1:-1]) if not negative else None))
    identity=np.arange(256,dtype=np.uint8).view(np.int8)
    for kernel in (1,3):
        for h,w in ((1,1),(1,7),(3,5),(8,16)):
            for ci in (1,5,8,9,31,32,63,64):run(h,w,ci,0,1,1,kernel,0,np.stack([identity,identity]),'legacy_passthrough')
    for kernel in (1,3):
        for ca,cb in ((1,0),(5,0),(16,0),(1,1),(7,9),(9,7),(31,33),(32,32),(63,1)):
            for fa,fb in ((1,1),(2,1),(1,2),(2,2)):
                tables=rng.integers(-128,128,size=(2,256),dtype=np.int8)
                run(8,12,ca,cb,fa,fb,kernel,1 if cb==0 else 2,tables,'arbitrary_LUT_tail_concat_scale')
    cases=model_cases()
    for case in cases:
        for kernel in (1,3):
            run(**{k:case[k] for k in ('h','w','ca','cb','fa','fb')},kernel=kernel,mode=2,tables=case['tables'],label='model_'+case['name'])
    options=dict(h=8,w=12,ca=5,cb=0,fa=1,fb=1,kernel=1,mode=1)
    negatives=[dict(h=0),dict(h=513),dict(w=0),dict(w=513),dict(kernel=2),dict(mode=3),dict(ca=0),dict(ca=65),
        dict(cb=1),dict(fa=0),dict(fa=3),dict(fb=0),dict(fb=4),dict(h=7,fa=2),dict(w=11,fa=2),dict(mode=2),dict(ci_override=6)]
    for change in negatives:run(**dict(options,**change),tables=np.stack([identity,identity]),label='invalid',negative=True)
    proof=dict(status='tensor_reader_native_full_bytes_original_frame_and_three_frozen_model_joins_exact',
        cases=rows,valid_cases=sum(r['status']==0 for r in rows),invalid_cases=len(negatives),
        full_model_join_cases=[{k:v.tolist() if isinstance(v,np.ndarray) else v for k,v in c.items()} for c in cases],
        every_packet_data_keep_strb_last_and_output_guards_checked=True,current_model_PS_join_outputs_exact=True,
        repeated_calls_and_mode_changes_exercised=True,seconds=time.perf_counter()-started,
        requested_transform_loop_II=1,actual_II_timing_resources_and_backpressure_not_yet_measured=True,
        source_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in [HERE/'test_native.py',HERE/'build_native/compiled.json',
            library,prior,ROOT/'modules/segmentation/outputs/ct_accuracy_v2/pl_model/graph.json',ROOT/'modules/segmentation/outputs/ct_accuracy_v2/pl_model/tensors.npz']},
        intended_integration='replace internal C5 reader inside the same DFX RM; preserve its external frozen RP and AXIS framing',
        requires_HLS_RTL_RM100MHz_all5PR_ARM_full139_and_system_tests=True,PL_accessed=False,production_promoted=False,whole_goal_completed=False)
    with (HERE/'native_verified.json').open('x',encoding='utf8') as f:json.dump(proof,f,indent=2)
    print('PASS',len(rows),'complete native cases; three actual model joins; not board performance')
if __name__=='__main__':main()
