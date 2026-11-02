import sys,json,ctypes
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
lib=ctypes.CDLL(str(root/'ct_pl/build/ct_native.dll'));fn=lib.ct_native_quant
fn.argtypes=[ctypes.c_void_p]*3+[ctypes.c_uint]*4;fn.restype=ctypes.c_int
rows=[];head=['// Generated real-model writer vectors for C/RTL verification.','#include <cstdint>']
for folder in [root/'ct_pl/model',root/'outputs/ct_accuracy_v2/pl_model']:
 plan=json.loads((folder/'graph.json').read_text());arr=dict(np.load(folder/'tensors.npz'));vec=dict(np.load(folder/'layer_vectors.npz'))
 for idx,node in enumerate(plan['nodes']):
  if node['op']!='Conv':continue
  c=node['integer'];id=c['id'];q=plan['nodes'][idx+1]
  if q['op']!='QuantizeLinear':continue
  qs,qz=[arr[n] for n in q['inputs'][1:]];bias=arr[c['bias']];scale=arr[c['input_scale']]*arr[c['weight_scale']]
  raw=vec[f'y_{id}'];_,co,h,w=raw.shape;padded=(co+7)//8*8
  acc=np.zeros((h,w,padded),np.int32);acc[:,:,:co]=raw[0].transpose(1,2,0)
  params=np.zeros((padded,2),np.uint32);params[:co,0]=bias.view(np.uint32);params[:co,1]=scale.view(np.uint32)
  count=h*w*padded//8;out=np.zeros(((count+3)//4*32,),np.int8)
  assert fn(acc.ctypes.data,out.ctypes.data,params.ctypes.data,count,co,int(qs.view(np.uint32).item()),int(qz.item())&0xffffffff)==0
  bp=np.zeros(padded,np.int32);sp=np.zeros(padded,np.float32);bp[:co]=bias;sp[:co]=scale
  expected=np.clip(np.rint((acc+bp).astype(np.float32)*sp/qs)+qz,-128,127).astype(np.int8)
  np.testing.assert_array_equal(out[:count*8],expected.ravel())
  # Diverse pixel subset; whole layer remains checked above in native simulation.
  indices=np.linspace(0,h*w-1,8,dtype=int);sample=acc.reshape(-1,padded)[indices].ravel();exp=expected.reshape(-1,padded)[indices].ravel();n=len(sample)//8
  tag=len(rows)
  for name,data,typ in [('params',params.ravel(),'uint32_t'),('acc',sample.view(np.uint32),'uint32_t'),('expected',exp,'int')]:head.append(f'static const {typ} {name}_{tag}[]={{'+','.join(str(int(v)) for v in data)+'};')
  rows.append(dict(model=folder.relative_to(root).as_posix(),layer=id,elements=int(acc.size),exact=True,count=n,channels=co,qscale=int(qs.view(np.uint32).item()),zero=int(qz.item())))
head.append('static void real_vectors(){')
for i,r in enumerate(rows):head.append(f'check_real(params_{i},acc_{i},expected_{i},{r["count"]},{r["channels"]},{r["qscale"]}u,{r["zero"]});')
head.append('}')
(root/'ct_pl/build/writer_real_vectors.hpp').write_text('\n'.join(head)+'\n')
(root/'ct_pl/build/writer_real_validation.json').write_text(json.dumps(dict(status='passed',rows=rows),indent=2)+'\n')
print('PASS',len(rows),'real convolution quantization layers')
