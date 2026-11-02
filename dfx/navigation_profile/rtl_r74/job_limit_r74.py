"""Own-process Windows Job memory limit, assigned before the first thread runs."""
from pathlib import Path
import ctypes as C
from ctypes import wintypes as W
import json,os,subprocess,time
assert os.name=='nt'
K=C.WinDLL('kernel32',use_last_error=True)
SIZE=C.c_size_t;U64=C.c_uint64

class Basic(C.Structure):
    _fields_=[('process_time',C.c_int64),('job_time',C.c_int64),('flags',W.DWORD),('min_ws',SIZE),('max_ws',SIZE),('active_limit',W.DWORD),('affinity',SIZE),('priority',W.DWORD),('scheduling',W.DWORD)]
class IO(C.Structure):_fields_=[(n,U64) for n in ['read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes']]
class Extended(C.Structure):_fields_=[('basic',Basic),('io',IO),('process_limit',SIZE),('job_limit',SIZE),('peak_process',SIZE),('peak_job',SIZE)]
class Accounting(C.Structure):_fields_=[(n,C.c_int64) for n in ['total_user','total_kernel','period_user','period_kernel']]+[(n,W.DWORD) for n in ['faults','total_processes','active_processes','terminated_processes']]
class Thread(C.Structure):_fields_=[(n,W.DWORD) for n in ['size','usage','thread_id','owner']]+[('priority',W.LONG),('delta',W.LONG),('flags',W.DWORD)]
K.CreateJobObjectW.argtypes=[C.c_void_p,W.LPCWSTR];K.CreateJobObjectW.restype=W.HANDLE
K.SetInformationJobObject.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD];K.SetInformationJobObject.restype=W.BOOL
K.QueryInformationJobObject.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.c_void_p];K.QueryInformationJobObject.restype=W.BOOL
K.AssignProcessToJobObject.argtypes=[W.HANDLE,W.HANDLE];K.AssignProcessToJobObject.restype=W.BOOL
K.GetProcessId.argtypes=[W.HANDLE];K.GetProcessId.restype=W.DWORD
K.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD];K.CreateToolhelp32Snapshot.restype=W.HANDLE
K.Thread32First.argtypes=[W.HANDLE,C.POINTER(Thread)];K.Thread32First.restype=W.BOOL
K.Thread32Next.argtypes=[W.HANDLE,C.POINTER(Thread)];K.Thread32Next.restype=W.BOOL
K.OpenThread.argtypes=[W.DWORD,W.BOOL,W.DWORD];K.OpenThread.restype=W.HANDLE
K.ResumeThread.argtypes=[W.HANDLE];K.ResumeThread.restype=W.DWORD
K.CloseHandle.argtypes=[W.HANDLE];K.CloseHandle.restype=W.BOOL

class Completion(C.Structure):_fields_=[('key',C.c_void_p),('port',W.HANDLE)]
K.CreateIoCompletionPort.argtypes=[W.HANDLE,W.HANDLE,SIZE,W.DWORD];K.CreateIoCompletionPort.restype=W.HANDLE
K.GetQueuedCompletionStatus.argtypes=[W.HANDLE,C.POINTER(W.DWORD),C.POINTER(SIZE),C.POINTER(C.c_void_p),W.DWORD];K.GetQueuedCompletionStatus.restype=W.BOOL

def checked(value):
    if not value:raise C.WinError(C.get_last_error())
    return value

class Performance(C.Structure):
    _fields_=[('cb',W.DWORD)]+[(n,SIZE) for n in ['commit_total','commit_limit','commit_peak','physical_total','physical_available','system_cache','kernel_total','kernel_paged','kernel_nonpaged','page_size']]+[(n,W.DWORD) for n in ['handle_count','process_count','thread_count']]
K.K32GetPerformanceInfo.argtypes=[C.POINTER(Performance),W.DWORD];K.K32GetPerformanceInfo.restype=W.BOOL
K.TerminateJobObject.argtypes=[W.HANDLE,W.UINT];K.TerminateJobObject.restype=W.BOOL

def system_memory():
    assert C.sizeof(Performance)==104
    p=Performance();p.cb=C.sizeof(p);checked(K.K32GetPerformanceInfo(C.byref(p),p.cb))
    assert p.page_size>=4096 and p.commit_limit>=p.commit_total
    return dict(free_commit_bytes=(p.commit_limit-p.commit_total)*p.page_size,
        physical_available_bytes=p.physical_available*p.page_size,
        commit_limit_bytes=p.commit_limit*p.page_size,commit_total_bytes=p.commit_total*p.page_size)

memory=system_memory

def run(command,*,cwd,env,log,started,limit):
    assert C.sizeof(Extended)==144 and C.sizeof(Accounting)==48
    log=Path(log);started=Path(started);assert not log.exists() and not started.exists()
    assert 64*1024**2<=limit<=32768*1024**2
    reserve=1536*1024**2;initial=memory()
    assert min(initial["free_commit_bytes"],initial["physical_available_bytes"])>=max(512*1024**2,min(limit,512*1024**2))+reserve,"Insufficient actual system reserve; no child started"
    default_observer=memory is system_memory;minimum=initial["free_commit_bytes"];samples=0;resource_failure=None
    job=checked(K.CreateJobObjectW(None,None));proc=None;assigned=False;resumed=False;port=None
    limits=Extended();limits.basic.flags=0x200|0x2000;limits.job_limit=limit
    try:
        checked(K.SetInformationJobObject(job,9,C.byref(limits),C.sizeof(limits)))
        port=checked(K.CreateIoCompletionPort(W.HANDLE(-1),None,0,1));completion=Completion(C.c_void_p(0x65),port)
        checked(K.SetInformationJobObject(job,7,C.byref(completion),C.sizeof(completion)))
        begin=time.monotonic()
        with log.open('xb') as f:
            proc=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW|0x4|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
            handle=W.HANDLE(int(proc._handle));assert K.GetProcessId(handle)==proc.pid
            checked(K.AssignProcessToJobObject(job,handle));assigned=True
            snapshot=checked(K.CreateToolhelp32Snapshot(4,0));threads=[]
            try:
                entry=Thread();entry.size=C.sizeof(entry);ok=K.Thread32First(snapshot,C.byref(entry))
                while ok:
                    if entry.owner==proc.pid:threads.append(entry.thread_id)
                    ok=K.Thread32Next(snapshot,C.byref(entry))
            finally:K.CloseHandle(snapshot)
            assert len(threads)==1,threads
            state=dict(PID=proc.pid,parent_PID=os.getpid(),command=command,job_memory_limit_bytes=limit,
                exact_created_process_handle_verified=True,assigned_before_execution=True,
                inherited_descendants_limited=True,original_processes_assigned=False,elapsed_time_abort=False,
                minimum_system_free_commit_bytes=reserve,preflight_memory=initial,actual_default_memory_API=default_observer)
            with started.open('x',encoding='utf-8',newline='\n') as s:json.dump(state,s,indent=2);s.write('\n')
            thread=checked(K.OpenThread(2,False,threads[0]))
            try:assert K.ResumeThread(thread)==1
            finally:K.CloseHandle(thread)
            resumed=True;events=[]
            def drain():
                while True:
                    message=W.DWORD();key=SIZE();pid=C.c_void_p()
                    ok=K.GetQueuedCompletionStatus(port,C.byref(message),C.byref(key),C.byref(pid),0)
                    if not ok:
                        assert C.get_last_error()==258;break
                    assert key.value==0x65;events.append(dict(message=message.value,PID=pid.value))
            while True:
                accounting=Accounting();checked(K.QueryInformationJobObject(job,1,C.byref(accounting),C.sizeof(accounting),None))
                drain()
                if any(e['message']==10 for e in events) and resource_failure is None:
                    resource_failure=dict(reason='actual_kernel_JOB_OBJECT_MSG_JOB_MEMORY_LIMIT',
                        only_exact_created_job_handle_terminated=True,root_already_exited=proc.poll() is not None,
                        active_owned_processes=accounting.active_processes,elapsed_time_abort=False)
                    if accounting.active_processes:checked(K.TerminateJobObject(job,0xE0000067))
                if proc.poll() is not None and not accounting.active_processes:break
                observed=memory();samples+=1;minimum=min(minimum,observed['free_commit_bytes'])
                if observed['free_commit_bytes']<reserve and resource_failure is None:
                    resource_failure=dict(reason='actual_system_commit_reserve_exhausted',observed_memory=observed,only_exact_created_job_handle_terminated=True,
                        root_already_exited=proc.poll() is not None,active_owned_processes=accounting.active_processes,
                        elapsed_time_abort=False)
                    checked(K.TerminateJobObject(job,0xE0000067))
                time.sleep(.05)
            code=proc.wait()
        peaks=Extended();checked(K.QueryInformationJobObject(job,9,C.byref(peaks),C.sizeof(peaks),None))
        drain()
        return dict(state,exit_code=code,elapsed_s=time.monotonic()-begin,job_events=events,job_memory_limit_rejection_observed=any(e['message']==10 for e in events),reported_peak_job_bytes=peaks.peak_job,
            reported_peak_process_bytes=peaks.peak_process,job_total_processes=accounting.total_processes,
            all_owned_processes_terminal=True,resource_failure=resource_failure,minimum_observed_free_commit_bytes=minimum,
            native_memory_observations=samples,configured_job_memory_limit_bytes=peaks.job_limit,configured_limit_flags=peaks.basic.flags,
            configured_limit_verified=peaks.job_limit==limit and peaks.basic.flags&0x200!=0)
    finally:
        # This handle contains only the newly created suspended process and its
        # descendants. Closing it cannot target pre-existing simulation jobs.
        K.CloseHandle(job)
        if port:K.CloseHandle(port)
        if proc is not None and not resumed:
            if not assigned:proc.terminate()
            proc.wait()
