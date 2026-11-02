import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,ctypes,json
import numpy as np
from ct_pl.runtime import pack_weights
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--model-dir',type=Path,default=ROOT/'model');p.add_argument('--library',type=Path,default=ROOT/'build/ct_native.dll');p.add_argument('--output',type=Path);a=p.parse_args()
lib=ctypes.CDLL(str(a.library.resolve()))
lib.ct_native.argtypes=[ctypes.c_void_p]*3+[ctypes.c_uint]*5
vectors=np.load(a.model_dir/'layer_vectors.npz',allow_pickle=False);reports=[]
for id in range(18):
    x,w,expected=[vectors[f'{n}_{id}'] for n in ['x','w','y']]
    ci,h,width=x.shape[1:];co=w.shape[0];k=w.shape[2]
    inp=np.zeros((h,width,(ci+7)//8*8),np.int8);inp[:,:,:ci]=x[0].transpose(1,2,0)
    weight=pack_weights(w);out=np.zeros((h,width,(co+7)//8*8),np.int32)
    assert lib.ct_native(inp.ctypes.data,weight.ctypes.data,out.ctypes.data,h,width,ci,co,k)==0
    got=out[:,:,:co].transpose(2,0,1)[None];np.testing.assert_array_equal(got,expected)
    reports.append({'layer':id,'shape':list(x.shape),'max_integer_error':0})
(a.output or a.model_dir/'native_validation.json').write_text(json.dumps({'status':'passed','layers':reports},indent=2))
print('All 18 real-model layer vectors match HLS C++ exactly')
