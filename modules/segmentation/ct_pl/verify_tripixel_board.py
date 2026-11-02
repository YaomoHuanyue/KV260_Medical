"""Board validation of three-pixel tails, row boundaries and mapped input leases."""
import sys,os,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from ct_pl.run import ROOT,backend,write_json

def main():
 out=ROOT/'ct_pl/package/tripixel_board_validation.json'
 state=out.with_name('tripixel_hardware_status.json');os.environ['CT_PL_STATUS_PATH']=str(state)
 write_json(state,dict(status='running',pid=os.getpid()))
 b=backend(output_pool=True);rng=np.random.default_rng(901);rows=[]
 try:
  for h,w in [(1,1),(1,2),(1,3),(1,4),(1,5),(3,5),(3,7),(2,512)]:
   for ci in [1,16,33,64]:
    k,co=3,17;ident=len(rows)
    base=b.allocate_activation((h,w,ci));base[:]=rng.integers(-20,21,base.shape,dtype=np.int8)
    x=base.transpose(2,0,1)[None];weight=rng.integers(-10,11,(co,ci,k,k),dtype=np.int8)
    padded=np.pad(x.astype(np.int32),((0,0),(0,0),(k//2,k//2),(k//2,k//2)))
    reference=np.zeros((1,co,h,w),np.int32)
    for y in range(k):
     for z in range(k):reference+=np.einsum('bihw,oi->bohw',padded[:,:,y:y+h,z:z+w],weight[:,:,y,z].astype(np.int32))
    np.testing.assert_array_equal(b.conv(ident,x,weight),reference)
    bias=np.arange(co,dtype=np.int32)-6;scale=np.full(co,0.125,np.float32);qs=np.array(2,np.float32);qz=np.array(-1,np.int8)
    expected=np.clip(np.rint((reference+bias[None,:,None,None]).astype(np.float32)*scale[None,:,None,None]/qs)+qz,-128,127).astype(np.int8)
    got=b.conv_quantized(ident,x,weight,bias,scale,qs,qz)
    np.testing.assert_array_equal(got,expected)
    rows.append(dict(kernel=k,cin=ci,shape=list(x.shape),raw_exact=True,quantized_exact=True,mapped_input=ci%8==0))
  write_json(out,dict(status='completed',loaded_bit_bin_sha256=Path('/run/kv260-ct-loaded.sha256').read_text().strip(),cases=rows))
  write_json(state,dict(status='completed'));print('PASS: 32 three-pixel board cases, raw and mapped quantized')
 except Exception as exc:
  write_json(state,dict(status='failed',error=str(exc)));raise
 finally:b.close()
if __name__=='__main__':main()
