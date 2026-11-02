"""Cold real-release refusal and explicit fake-ABI owner lifecycle checks.

The actual ARM XRT library was compiled and malformed roots tested by R2147.
These fixtures do not open it, change firmware or claim hardware performance.
"""
from pathlib import Path
import ctypes as C
import gc
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from threading import Event,get_ident
from unittest.mock import patch
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
HOST='Windows' if os.name=='nt' else 'ARM'
OUT=ROOT/f'results/FMA2_smoothing_runtime_r1/{HOST}.json'


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


backend=module('compact_smoothing_backend_r2151',ROOT/'dfx/smooth_speed/runtime_FMA2_r1.py')
flow=module('compact_smoothing_client_r2140',ROOT/'dfx/smooth_speed/host_streaming_r2140/client.py')


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):
            h.update(b)
    return h.hexdigest()


def refused(fn,error,message=None):
    try:
        fn()
    except error as exc:
        if message is not None:
            assert message in str(exc)
        return
    raise AssertionError('Expected refusal')


class Function:
    def __init__(self,fn):
        self.fn=fn

    def __call__(self,*args):
        return self.fn(*args)


class FakeLibrary:
    def __init__(self,profile):
        self.profile=profile
        self.calls=[]
        self.started,self.release=Event(),Event()
        self.restoring,self.release_restore=Event(),Event()
        self.fail_run=False
        self.hold_restore=False
        self.error=b'Fixture terminal native failure'
        for name in ('error','open_root','profile_snapshot','close','restore','run'):
            setattr(self,'speed_'+name,Function(getattr(self,'_'+name)))

    def record(self,name,args):
        self.calls.append((name,get_ident(),args))

    def _error(self):
        return self.error

    def _open_root(self,root,measure):
        assert root==os.fsencode(ROOT) and measure==self.profile
        self.record('open',(root,measure))
        self.owner=get_ident()
        return 123

    def _run(self,*args):
        assert get_ident()==self.owner and len(args)==14 and args[0]==123
        self.record('run',args[:13])
        if not self.started.is_set():
            self.started.set()
            assert self.release.wait(30)
        if self.fail_run:
            return -1
        nv=args[8]
        output=np.ctypeslib.as_array((C.c_float*(nv*4)).from_address(args[6]))
        output[:]=np.arange(nv*4,dtype=np.float32)
        report=np.ctypeslib.as_array((C.c_uint32*16).from_address(args[7]))
        report[:]=np.arange(16,dtype=np.uint32)
        for i in range(12):
            args[13][i]=i+1
        return 0

    def _profile_snapshot(self,handle,values):
        assert self.profile and get_ident()==self.owner and handle==123
        self.record('profile',())
        for i in range(16):
            values[i]=i+1
        values[13]=0
        return 0

    def _restore(self,handle):
        assert get_ident()==self.owner and handle==123
        self.record('restore',())
        if self.hold_restore:
            self.restoring.set()
            assert self.release_restore.wait(30)
        return 0

    def _close(self,handle):
        assert get_ident()==self.owner and handle==123
        self.record('close',())


def inputs():
    edge=np.dtype([('index','<u4'),('weight','<f4')])
    return [np.zeros((4,4),'<f4'),np.array([0,1,2,2,2],'<u4'),np.array([(1,1.),(2,1.)],edge),np.zeros(4,'<u4'),np.empty((0,4),'<u4')]


def fixture(profile):
    library=FakeLibrary(profile)
    sessions=[]
    def factory():
        value=backend.Session(profile=profile)
        sessions.append(value)
        return value
    client=flow.SmoothClient(factory)
    client.ready.result(30)
    session=sessions[0]
    data=inputs()
    output=np.empty((4,4),np.float32)
    report=np.empty(16,np.uint32)
    future=client.submit(data,output,report,4,0,2,.31,1)
    # Factory and work are held by a fake CDLL supplied by the outer wrapper.
    return client,session,data,output,report,future


def main():
    assert not OUT.exists() and not (ROOT/'dfx/smooth_speed/release_FMA2_r1').exists()
    cwd=Path.cwd()
    with patch.object(backend.C,'CDLL',side_effect=AssertionError('Must refuse before library access')):
        refused(lambda:backend.Session().__enter__(),RuntimeError,'No complete compact C2')
    assert Path.cwd()==cwd
    records=[]
    with tempfile.TemporaryDirectory(prefix='kv260-runtime-contract-r2152-') as directory:
        os.chdir(directory)  # This isolated test process only, not the runtime.
        try:
            for profile in (False,True):
                library=FakeLibrary(profile)
                sessions=[]
                def factory():
                    session=backend.Session(profile)
                    sessions.append(session)
                    return session
                with patch.object(backend,'verify',return_value={'artificial_fixture':True}),patch.object(backend.C,'CDLL',return_value=library):
                    client=flow.SmoothClient(factory)
                    client.ready.result(30)
                    session=sessions[0]
                    data=inputs()
                    output=np.empty((4,4),np.float32)
                    report=np.empty(16,np.uint32)
                    request=client.submit(data,output,report,4,0,2,.31,1)
                    assert library.started.wait(30) and not request.done() and not request.cancel()
                    for fn in (lambda:session.run(data,output,report,4,0,2,.31,1),session.restore,session.profile_snapshot,lambda:session.__exit__(None,None,None)):
                        refused(fn,RuntimeError,'background owner')
                    library.release.set()
                    phases=request.result(30)
                    assert len(phases)==10 and phases['validation']==1 and phases['native_host_total']==10
                    np.testing.assert_array_equal(output.ravel(),np.arange(16,dtype=np.float32))
                    np.testing.assert_array_equal(report,np.arange(16,dtype=np.uint32))
                    first=[r for r in library.calls if r[0]=='run'][0][2]
                    assert first[1:6]==tuple(v.ctypes.data for v in data) and first[6:8]==(output.ctypes.data,report.ctypes.data)
                    malformed=[(data[:4],output,report)]
                    for index in range(5):
                        for kind in ('dtype','size','contiguous'):
                            changed=list(data)
                            old=data[index]
                            if kind=='dtype':
                                changed[index]=np.zeros(old.size,np.float64)
                            elif kind=='size':
                                changed[index]=np.zeros(old.size+1,old.dtype)
                            elif old.size:
                                changed[index]=np.zeros(old.size*2,old.dtype)[::2]
                            else:
                                continue
                            malformed.append((changed,output,report))
                    bad_outputs=[np.empty(16,np.float32),np.empty((4,4),np.float64),np.empty((4,8),np.float32)[:,::2],output.copy()]
                    bad_outputs[-1].setflags(write=False)
                    malformed.extend((data,v,report) for v in bad_outputs)
                    bad_reports=[np.empty(17,np.uint32),np.empty(16,np.float32),np.empty(32,np.uint32)[::2],report.copy()]
                    bad_reports[-1].setflags(write=False)
                    malformed.extend((data,output,v) for v in bad_reports)
                    before=len([r for r in library.calls if r[0]=='run'])
                    for a,b,c in malformed:
                        refused(lambda a=a,b=b,c=c:client.submit(a,b,c,4,0,2,.31,1).result(30),ValueError)
                    assert len(malformed)==23 and len([r for r in library.calls if r[0]=='run'])==before
                    if profile:
                        snapshot=client._owner.submit(lambda s:s.profile_snapshot()).result(30)
                        assert len(snapshot)==16 and snapshot['response_errors']==0
                    else:
                        refused(lambda:client._owner.submit(lambda s:s.profile_snapshot()).result(30),RuntimeError,'explicit profile')
                        assert not any(r[0]=='profile' for r in library.calls)
                    library.fail_run=True
                    refused(lambda:client.submit(data,output,report,4,0,2,.31,1).result(30),RuntimeError,'Fixture terminal native failure')
                    library.fail_run=False
                    library.hold_restore=True
                    closed=client.close()
                    assert library.restoring.wait(30) and not closed.done() and not any(r[0]=='close' for r in library.calls)
                    library.release_restore.set()
                    closed.result(30)
                    client._owner._thread.join(30)
                    assert library.calls[-2][0]=='restore' and library.calls[-1][0]=='close'
                    assert len(set(r[1] for r in library.calls))==1 and library.owner!=get_ident()
                    assert session.handle is None and Path.cwd()==Path(directory)
                    records.append(dict(profile=profile,all23_original_dtype_size_stride_and_output_writeability_refusals=True,
                                        exact14_native_arguments_and10_phase_fields_verified=True,
                                        default_profile_disabled_without_counter_access=not profile,
                                        all4_foreign_thread_operations_refused=True,
                                        terminal_native_error_reported_without_PS_fallback=True,
                                        close_returned_while_restore_held_then_closed_in_same_owner=True,
                                        process_cwd_unchanged_by_backend=True))
        finally:
            os.chdir(cwd)
    paths=[Path(__file__),ROOT/'dfx/smooth_speed/runtime_FMA2_r1.py',ROOT/'tools/seal_FMA2_smoothing_release_r1.py',ROOT/'dfx/smooth_speed/host_streaming_r2140/client.py',ROOT/'dfx/navigation_profile/host_streaming_r1180/async_session.py']
    result=dict(status='compact_C2_real_unsealed_release_refusal_and_full_owner_ABI_fixtures_passed',host=HOST,
                actual_unsealed_release_refused_before_CDLL_or_XRT=True,artificial_ABI_fixture_only=True,cases=records,
                original_full144_plus18_actual_native_math_evidence_remains_R2141=True,
                source_and_evidence_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in paths},
                XRT_session_created=False,PL_accessed=False,current_UI_or_firmware_changed=False,
                production_promoted=False,whole_goal_completed=False)
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open('x',encoding='utf8') as f:
        json.dump(result,f,indent=2);f.write('\n')
    print(result['status'],HOST,flush=True)


if __name__=='__main__':
    main()
