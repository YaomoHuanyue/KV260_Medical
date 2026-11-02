"""Python buffer ownership and rejection tests; fake transport never accesses PL."""
from pathlib import Path
import ctypes as C
import gc
import hashlib
import json
import os
import threading
import weakref
import numpy as np
import runtime as hw


class Fake:
    def __init__(self):self.pending={};self.next=1;self.calls=0;self.fail_submit=False;self.fail_collect=False;self.repeat=False;self.fail_close=False
    def hu_error(self):return b'fake transport failure'
    def hu_submit(self,handle,src,n,table,dst,status,phases):
        self.calls+=1
        if self.fail_submit:return 0
        ticket=self.next
        if not self.repeat:self.next+=1
        self.pending[ticket]=(src,n,table,dst,status,phases);return ticket
    def hu_collect(self,handle,ticket):
        self.calls+=1
        if self.fail_collect:return 1
        src,n,table,dst,status,phases=self.pending.pop(ticket)
        if n:
            source=np.ctypeslib.as_array((C.c_int16*n).from_address(src))
            lut=np.ctypeslib.as_array((C.c_int8*1401).from_address(table))
            target=np.ctypeslib.as_array((C.c_int8*n).from_address(dst))
            target[:]=lut[np.clip(source.astype(np.int32)+1000,0,1400)]
        values=[0x31554851,1,0,n,(n+31)//32,(n+63)//64,n,0]
        target=(C.c_uint32*8).from_address(status)
        for i,v in enumerate(values):target[i]=v
        for i in range(12):phases[i]=i*.001
        return 0
    def hu_close(self,pointer):
        self.calls+=1
        if self.fail_close:return 1
        self.fail_collect=False
        for ticket in list(self.pending):self.hu_collect(123,ticket)
        pointer._obj.value=None;return 0


def main():
    negatives=0;positive=0
    def refuses(fn):
        nonlocal negatives
        try:fn()
        except (RuntimeError,ValueError,TypeError):negatives+=1;return
        raise AssertionError('Invalid runtime call accepted')
    def session():
        s=hw.Session(experimental=True);s.lib=Fake();s.handle=123;return s
    table=np.arange(1401,dtype=np.int16).astype(np.int8)
    image=np.arange(64,dtype=np.int16)
    for value in [1,0,None,'yes',np.bool_(True)]:refuses(lambda:hw.Session(experimental=value))
    s=session()
    for bad in [None,[],image.astype(np.int32),image.astype(np.float32),image.astype(np.int8),image[::2],
                np.empty(hw.MAX_REQUEST+1,np.int16)]:refuses(lambda:s.submit(bad,table))
    for bad in [None,[],table.astype(np.int16),table[:1400],table.reshape(1,-1),table[::-1]]:refuses(lambda:s.submit(image,bad))
    readonly=np.zeros(64,np.int8);readonly.flags.writeable=False
    for bad in [np.zeros(63,np.int8),np.zeros(64,np.int16),np.zeros((8,8),np.int8),readonly,
                image.view(np.int8)[:64],table[:64]]:refuses(lambda:s.submit(image,table,bad))
    assert s.lib.calls==0
    for shape in [(0,),(1,),(2,3),(64,),(65,),(2,3,4)]:
        data=np.arange(np.prod(shape),dtype=np.int16).reshape(shape)
        ticket=s.submit(data,table);result,phases=s.collect(ticket)
        np.testing.assert_array_equal(result,table[np.clip(data.astype(np.int32)+1000,0,1400)])
        assert result.shape==shape and set(phases)==set(hw.PHASES);positive+=1
    a=s.submit(image,table);b=s.submit(image,table)
    for bad in [True,np.bool_(True),0,-1,2**64,'1',1.0,None,999]:refuses(lambda:s.collect(bad))
    refuses(lambda:s.submit(image,table));before=s.lib.calls
    errors=[]
    def foreign():
        try:s.collect(a)
        except RuntimeError:errors.append(True)
    t=threading.Thread(target=foreign);t.start();t.join();assert errors and s.lib.calls==before
    s.collect(b);s.collect(a);positive+=2
    # Every array referenced by native work survives collection even if its
    # caller drops all references and Python runs garbage collection.
    data=np.arange(65,dtype=np.int16);lut=table.copy();data_ref=weakref.ref(data);lut_ref=weakref.ref(lut)
    ticket=s.submit(data,lut);del data,lut;gc.collect();assert data_ref() is not None and lut_ref() is not None
    s.collect(ticket);gc.collect();assert data_ref() is None and lut_ref() is None;positive+=1
    s.lib.fail_submit=True;before=len(s.pending);refuses(lambda:s.submit(image,table));assert len(s.pending)==before;s.lib.fail_submit=False
    ticket=s.submit(image,table);s.lib.fail_collect=True;refuses(lambda:s.collect(ticket));assert ticket in s.pending
    before=s.lib.calls;refuses(lambda:s.submit(image,table));assert before==s.lib.calls
    s.lib.fail_close=True;refuses(s.close);assert s.handle and s.pending
    s.lib.fail_close=False;s.close();assert not s.handle and not s.pending
    s=session();s.lib.repeat=True;ticket=s.submit(image,table);refuses(lambda:s.submit(image,table));assert s.orphans and s.failed
    s.close();assert not s.orphans and not s.pending;positive+=1
    # Full output assembly uses preallocated output views, with at most two
    # requests outstanding and no per-chunk bit selection in the transport.
    for count,chunk in [(97,1),(97,31),(97,32),(97,33),(97,64),(97,65),(65536,1024),(65536,16384)]:
        s=session();data=np.arange(count,dtype=np.uint16).view(np.int16)
        result,metrics=hw.quantize_volume(s,data,table,chunk_voxels=chunk)
        np.testing.assert_array_equal(result,table[np.clip(data.astype(np.int32)+1000,0,1400)])
        assert not s.pending and metrics['chunks']==(count+chunk-1)//chunk and metrics['PS_quantization_used'] is False
        s.close();positive+=1
    for chunk in [0,-1,True,np.int64(1),hw.MAX_REQUEST+1,'64']:
        s=session();refuses(lambda:hw.quantize_volume(s,image,table,chunk_voxels=chunk));s.close()
    if not (hw.RELEASE/'manifest.json').exists():
        refuses(lambda:hw.Session(experimental=True).__enter__())
        refuses(lambda:hw.Session().__enter__())
    report=dict(status='Python_HU_API_ownership_alias_and_two_slot_volume_tests_passed',
        host='Windows' if os.name=='nt' else 'ARM',positive_cases=positive,rejected_calls=negatives,
        foreign_thread_refused_before_native_call=True,native_failure_retains_arrays_until_confirmed_close=True,
        both_collection_orders_and_full_signed_HU_volume_tested=True,PL_accessed=False,
        source_SHA256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(hw.__file__)]})
    path=Path(__file__).parent/('runtime_verified_'+report['host']+'.json')
    with path.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
