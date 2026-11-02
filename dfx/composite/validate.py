"""Independent integer reference for stable 4-layer depth ordering and alpha."""
from pathlib import Path
import ctypes
import hashlib
import json
import numpy as np

ROOT=Path(__file__).resolve().parent


def reference(planes,background):
    colors,depth=planes[::2],planes[1::2]
    indices=np.arange(4,dtype=np.uint64)[:,None]
    # Stable layer 0 is nearest in a tie; invalid fragments blend with alpha 0.
    key=((depth&0xffffff).astype(np.uint64)<<2)+indices
    order=np.argsort(key,axis=0)[::-1]
    ordered=np.take_along_axis(colors,order,axis=0)
    valid=np.take_along_axis(depth>>24,order,axis=0)!=0
    result=np.tile(np.array([background&255,(background>>8)&255,(background>>16)&255],np.uint32),(planes.shape[1],1))
    for layer in range(4):
        alpha=np.where(valid[layer],ordered[layer]>>24,0)
        rgb=np.column_stack([(ordered[layer]>>(8*channel))&255 for channel in range(3)])
        result=(rgb*alpha[:,None]+result*(255-alpha[:,None])+127)//255
    return (result[:,0]|(result[:,1]<<8)|(result[:,2]<<16)|np.uint32(0xff000000)).astype(np.uint32)


def main():
    lib=ctypes.CDLL(str(ROOT/'build/composite_reference.dll'))
    lib.composite_reference.argtypes=[ctypes.c_void_p]*2+[ctypes.c_uint]*4
    lib.composite_blend.argtypes=[ctypes.c_uint]*3
    lib.composite_reference_layers.argtypes=[ctypes.c_void_p]*2+[ctypes.c_uint]*5
    # Check all 16,777,216 component combinations without relying on HLS's
    # optimized division or using the same bit arithmetic as the candidate.
    x=np.arange(256,dtype=np.uint32)
    blend_cases=0
    for alpha in range(256):
        expected=(x[:,None]*alpha+x[None,:]*(255-alpha)+127)//255
        actual=((x[:,None]*alpha+x[None,:]*(255-alpha)+128)*257)>>16
        np.testing.assert_array_equal(actual,expected)
        for source,destination in [(0,0),(0,255),(255,0),(255,255),(127,128)]:
            assert lib.composite_blend(source,destination,alpha)==expected[source,destination]
        blend_cases+=256*256
    rng=np.random.default_rng(2602026);cases=[]
    fixtures=ROOT/'fixtures';fixtures.mkdir(exist_ok=True)
    for n in [16,48,512,528,4096,384*218,640*363,640*512]:
        # The production width is a multiple of 16, including each row.
        stride=(n+1023)//1024*1024
        stride=min(stride,640*512)
        storage=np.full((8,stride),0x19283746,np.uint32)
        planes=storage[:,:n]
        planes[::2]=rng.integers(0,2**32,(4,n),dtype=np.uint32)
        depth=rng.integers(0,2**24,(4,n),dtype=np.uint32)
        # Exercise transparent, opaque, same-depth, empty and far-plane cases.
        valid=rng.integers(0,2,(4,n),dtype=np.uint32)*255
        planes[1::2]=depth|(valid<<24)
        planes[::2,::7]&=np.uint32(0xffffff)
        planes[::2,1::7]|=np.uint32(0xff000000)
        planes[1::2,::11]=np.uint32(0xff654321)
        planes[1::2,1::11]=0
        planes[1::2,2::11]=np.uint32(0xffffffff)
        guard=np.full(n+32,0xa9876543,np.uint32)
        before=storage.copy()
        background=0xff201007
        status=lib.composite_reference(storage.ctypes.data,guard[16:].ctypes.data,n,stride,background,1)
        assert status==0
        expected=reference(planes,background)
        np.testing.assert_array_equal(guard[16:16+n],expected)
        np.testing.assert_array_equal(guard[:16],np.full(16,0xa9876543,np.uint32))
        np.testing.assert_array_equal(guard[16+n:],np.full(16,0xa9876543,np.uint32))
        np.testing.assert_array_equal(storage,before)
        # Only representative cases go to RTL; full-sized vectors remain board trials.
        if n in (16,528,4096,640*363):
            storage.tofile(fixtures/f'pixels_{n}.input.bin')
            expected.tofile(fixtures/f'pixels_{n}.expected.bin')
            for active in (1,2,3,4):
                masked=planes.copy();masked[2*active:]=0
                active_expected=reference(masked,background)
                output=np.full(n+32,0xabcabcab,np.uint32)
                assert lib.composite_reference_layers(storage.ctypes.data,output[16:].ctypes.data,n,stride,background,1,active)==0
                np.testing.assert_array_equal(output[16:16+n],active_expected)
                np.testing.assert_array_equal(output[:16],np.full(16,0xabcabcab,np.uint32))
                np.testing.assert_array_equal(output[16+n:],np.full(16,0xabcabcab,np.uint32))
                active_expected.tofile(fixtures/f'active_{active}_pixels_{n}.expected.bin')
        cases.append(dict(pixels=n,stride_pixels=stride,status='passed',same_depth_and_empty=True))
    for n,stride in [(0,16),(15,16),(16,15),(640*512+16,640*512+16)]:
        output=np.full(32,0xabcabcab,np.uint32)
        assert lib.composite_reference(storage.ctypes.data,output.ctypes.data,n,stride,0,1)==2
        np.testing.assert_array_equal(output,np.full(32,0xabcabcab,np.uint32))
    report=dict(status='passed',kind='CPU native numerical model; not PL execution',blend_component_cases=blend_cases,cases=cases,
                color='RGBA8 straight alpha over opaque background',depth='24-bit unsigned, layer 0 nearest on ties',
                sources={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in
                         [ROOT/'hls/algorithm.hpp',ROOT/'host/reference.cpp',ROOT/'validate.py']})
    (ROOT/'docs').mkdir(exist_ok=True)
    (ROOT/'docs/native_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
