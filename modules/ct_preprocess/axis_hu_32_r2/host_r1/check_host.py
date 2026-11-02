"""Real scheduler tests and ARM XRT bridge compilation without PL access."""
from pathlib import Path
import argparse
import ctypes as C
import hashlib
import json
import os
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--revision',default='r1');a=p.parse_args()
    assert a.revision.isalnum()
    host='Windows' if os.name=='nt' else 'ARM'
    out=HERE/('native_'+host+'_'+a.revision);assert not out.exists()
    assert not (HERE.parent/'dfx_r1/release_r1/native_guard.txt').exists(),'Pre-release negative test must run before firmware is sealed'
    source=[x for x in HERE.iterdir() if x.is_file() and x.suffix in ['.cpp','.hpp','.py','.map','.json']]
    binding={x.relative_to(ROOT).as_posix():sha(x) for x in source}
    if os.name=='nt':
        subprocess.run([r'C:/Python314/python.exe','-B','-X','utf8',str(ROOT/'tools/project_storage.py'),
            'check','--reserve-bytes','50000000'],cwd=ROOT.parent,check=True,stdout=subprocess.DEVNULL)
        vswhere=r'C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe'
        install=Path(subprocess.check_output([vswhere,'-latest','-products','*','-requires',
            'Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath'],text=True).strip())
        vcvars=install/'VC/Auxiliary/Build/vcvars64.bat';assert vcvars.is_file()
    else:
        assert os.uname().machine=='aarch64' and os.geteuid()==0
        os.nice(10);os.sched_setaffinity(0,{2,3})
        sys.path.insert(0,str(ROOT))
        from modules.mask_evaluation.ui.actual_pl_r3.check_ARM import review_identity
        state=json.loads((ROOT/'tools/storage_runtime_identity.json').read_text());review_identity(state)
    out.mkdir();commands=[]
    def execute(name,argv):
        commands.append(dict(stage=name,argv=argv))
        with (out/(name+'.log')).open('xb') as f:subprocess.run(argv,cwd=HERE,stdout=f,stderr=subprocess.STDOUT,check=True)
        return (out/(name+'.log')).read_text(errors='replace')
    tests={}
    for name in ['test_original_queue','test_pipeline']:
        binary=out/(name+('.exe' if host=='Windows' else ''))
        if host=='Windows':
            batch=out/(name+'.bat')
            batch.write_text('@echo off\ncall "'+str(vcvars)+'"\nif errorlevel 1 exit /b 1\n'
                'cl.exe /nologo /std:c++17 /O2 /EHsc /MT /W4 /Fe:"'+str(binary)+'" /Fo:"'+str(out/(name+'.obj'))
                +'" "'+str(HERE/(name+'.cpp'))+'" /link /INCREMENTAL:NO\n')
            argv=['cmd.exe','/d','/c',str(batch)]
        else:argv=['g++','-std=c++17','-O3','-mcpu=cortex-a53','-Wall','-Wextra','-pthread',str(HERE/(name+'.cpp')),'-o',str(binary)]
        execute('compile_'+name,argv);text=execute('run_'+name,[str(binary)])
        if name=='test_original_queue':
            value=json.loads(text);assert value['complete_requests']==32000 and value['actual_worker_completions']==32001 and value['negative_cases']==17
            assert value['PL_accessed'] is False;tests[name]=value
        else:
            assert text.strip()=='PASS HU_NONBLOCKING_PIPELINE_86 actual waits only during collect/drain; both submits return before any completion'
            tests[name]=dict(cases=86,second_submit_has_no_completion_wait=True,both_collection_orders=True,
                prepare_build_post_and_validation_failures_drained=True,LUT_alias_and_overflow_rejected=True)
    preflight=None
    if host=='ARM':
        libpath=out/'libhu_dfx.so'
        execute('bridge',['g++','-std=c++17','-O3','-mcpu=cortex-a53','-fPIC','-shared','-Wall','-Wextra','-pthread',
            '-MMD','-MF',str(out/'bridge.d'),'-I/usr/include/xrt',str(HERE/'bridge.cpp'),
            '-Wl,--version-script='+str(HERE/'exports.map'),'-lxrt_coreutil','-o',str(libpath)])
        text=execute('ELF',['readelf','-h',str(libpath)]);assert 'AArch64' in text
        text=execute('ldd',['ldd',str(libpath)]);assert 'not found' not in text
        text=execute('exports',['nm','-D','--defined-only',str(libpath)])
        exports={line.split()[-1] for line in text.splitlines() if line.split()}
        assert exports=={'hu_error','hu_open_root','hu_submit','hu_collect','hu_close'}
        L=C.CDLL(str(libpath));L.hu_error.restype=C.c_char_p
        L.hu_open_root.argtypes=[C.c_char_p];L.hu_open_root.restype=C.c_void_p
        roots=[]
        for root in [None,b'',b'.',b'/tmp',b'/nonexistent-HU-D6',os.fsencode(ROOT/'fixtures'),os.fsencode(ROOT/'modules'),os.fsencode(ROOT)]:
            assert not L.hu_open_root(root),root
            message=L.hu_error().decode();assert 'before hardware access' in message or message.startswith('Explicit seed'),message
            roots.append(dict(root=None if root is None else os.fsdecode(root),error=message))
        L.hu_submit.argtypes=[C.c_void_p,C.c_void_p,C.c_uint32,*([C.c_void_p]*4)];L.hu_submit.restype=C.c_uint64
        L.hu_collect.argtypes=[C.c_void_p,C.c_uint64];L.hu_close.argtypes=[C.POINTER(C.c_void_p)]
        samples=(C.c_int16*64)();table=(C.c_int8*1401)();output=(C.c_int8*64)();report=(C.c_uint32*8)();phases=(C.c_double*12)()
        for count in [0,1,64,1<<23,(1<<23)+1,0xffffffff]:assert L.hu_submit(None,samples,count,table,output,report,phases)==0
        assert L.hu_collect(None,1)==1 and L.hu_close(None)==1
        empty=C.c_void_p();assert L.hu_close(C.byref(empty))==1
        assert not any(output) and not any(report) and not any(phases)
        review_identity(state)
        preflight=dict(library_SHA256=sha(libpath),root_refusals=roots,invalid_native_calls=9,
            no_FileLock_MMIO_XRT_or_PL_entered=True,exports=sorted(exports),actual_AArch64_compilation=True)
    for n,h in binding.items():assert sha(ROOT/n)==h,n
    artifacts={x.relative_to(ROOT).as_posix():sha(x) for x in out.iterdir() if x.is_file()}
    result=dict(status='HU_two_slot_nonblocking_scheduler_and_pre_release_host_qualified',host=host,
        tests=tests,native=preflight,source_SHA256=binding,artifacts_SHA256=artifacts,commands=commands,
        PL_accessed=False,production_promoted=False,actual_board_speed_compared=False)
    (out/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],host=host,tests=tests,native=preflight),indent=2),flush=True)


if __name__=='__main__':main()
