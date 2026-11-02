"""Validate both deployed model layer vectors with the actual HLS C++ convolution."""
import ctypes,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from ct_pl.runtime import pack_weights,pack_input
ROOT=Path(__file__).resolve().parents[1]
def main():
    lib=ctypes.CDLL(str(ROOT/'ct_pl/build/wide_input/ct_native.dll'))
    lib.ct_native.argtypes=[ctypes.c_void_p]*3+[ctypes.c_uint]*5
    lib.ct_native.restype=ctypes.c_int
    rows=[]
    for model in ['ct_pl/model','outputs/ct_accuracy_v2/pl_model']:
        vectors=np.load(ROOT/model/'layer_vectors.npz',allow_pickle=False)
        for id in range(18):
            x,w,expected=[vectors[f'{n}_{id}'] for n in ['x','w','y']]
            ci,h,width=x.shape[1:];co=w.shape[0];k=w.shape[2]
            inp=pack_input(x);weights=pack_weights(w);out=np.zeros((h,width,(co+7)//8*8),np.int32)
            assert lib.ct_native(inp.ctypes.data,weights.ctypes.data,out.ctypes.data,h,width,ci,co,k)==0
            np.testing.assert_array_equal(out[:,:,:co].transpose(2,0,1)[None],expected)
            assert np.count_nonzero(out[:,:,co:])==0
            rows.append(dict(model=model,layer=id,shape=list(x.shape),weights=list(w.shape),exact=True))
    result=dict(status='passed',source_sha256=hashlib.sha256((ROOT/'ct_pl/conv.cpp').read_bytes()).hexdigest(),layers=rows)
    (ROOT/'ct_pl/build/wide_input/model_validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: 36 model convolutions including padded output channels')
if __name__=='__main__':main()
