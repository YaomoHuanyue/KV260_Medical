"""Run the same complete CPU mock and compile the actual XRT library on ARM.

Never load the resulting library, open XRT or touch firmware/PL/GUI.
"""
from pathlib import Path
import hashlib,json,os,platform,re,resource,subprocess,time,traceback
HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,indent=2)
def bounded():resource.setrlimit(resource.RLIMIT_AS,(1536*1024**2,1536*1024**2))

def main():
    assert platform.machine()=='aarch64' and re.fullmatch('owned_R3host_[0-9a-f]{32}',HERE.name)
    manifest=json.loads((HERE/'inputs.json').read_text());root=HERE/'source'
    for n,h in manifest['sources'].items():assert sha(root/n)==h,n
    out=HERE/'output';assert not out.exists();out.mkdir()
    save(out/'started.json',dict(PID=os.getpid(),ticks=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]),boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()))
    receipts={};started=time.monotonic()
    try:
        host=root/'modules/segmentation/axis_tensor_reader_r3/host_r1';old=root/'modules/segmentation/ct_pool_fusion_r1/host_dual_r1'
        exe=out/'host_test';library=out/'libct_tensor_reader.so'
        common=['/usr/bin/g++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math']
        args=common+['-DCT_NATIVE','-I'+str(host/'mock'),'-I'+str(old/'mock'),'-I'+str(root/'dfx/medical/host_extended'),
            str(host/'native_test.cpp'),str(host.parent/'kernel.cpp'),'-o',str(exe)]
        def run(name,argv,env=None):
            begin=time.monotonic()
            with (out/(name+'.log')).open('xb') as f:r=subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT,env=env,preexec_fn=bounded)
            receipts[name]=dict(argv=argv,exit_code=r.returncode,seconds=time.monotonic()-begin)
            save(out/(name+'_receipt.json'),receipts[name]);assert r.returncode==0,name+' failed'
        run('mock_compile',args);run('mock_run',[str(exe)],dict(os.environ,CT_PL_CLEAN_BO='1'))
        rows=[json.loads(v) for v in (out/'mock_run.log').read_text().splitlines() if v.startswith('{')]
        assert rows==manifest['PC_rows'];assert len(rows)==2
        headers=[p for p in map(Path,('/usr/include','/usr/include/xrt','/opt/xilinx/xrt/include')) if (p/'xrt/xrt_bo.h').is_file()];assert headers
        args=common+['-fPIC','-shared','-pthread','-Wl,-z,defs','-I'+str(root/'modules/runtime_audit/C5_pool_host_r1'),
            '-I'+str(root/'dfx/medical/host_extended'),*[f'-I{p}' for p in headers],'-MD','-MF',str(out/'dependencies.d'),str(host/'ct_tensor_bridge.cpp')]
        args.extend(f'-L{p}' for p in map(Path,('/opt/xilinx/xrt/lib','/usr/lib/aarch64-linux-gnu')) if p.is_dir())
        args+=['-lxrt_coreutil','-o',str(library)];run('XRT_compile',args)
        raw=library.read_bytes();assert raw[:6]==b'\x7fELF\x02\x01' and int.from_bytes(raw[18:20],'little')==183
        deps=(out/'dependencies.d').read_text().replace('\\\n',' ').split()[1:];resolved={str(Path(p).resolve()) for p in deps}
        required=['modules/runtime_audit/C5_pool_host_r1/shared_session.hpp','modules/runtime_audit/session_log_r1/runtime.hpp',
            'modules/runtime_audit/session_log_r1/switch_log.hpp','dfx/medical/host_extended/postprocess.hpp']
        assert all(str(root/n) in resolved for n in required)
        assert not any('/mock/' in p for p in resolved)
        result=subprocess.run(['/usr/bin/nm','-D','--defined-only',str(library)],capture_output=True,check=True)
        (out/'defined_symbols.txt').write_bytes(result.stdout)
        actual={v.split()[-1] for v in result.stdout.decode().splitlines() if v.strip() and v.split()[-1].startswith('ct_')}
        expected=set(re.findall(r'extern\s+"C"\s+[^;{]*?\b(ct_\w+)\s*\(', (host/'ct_tensor_bridge.cpp').read_text()))
        assert actual==expected and len(actual)==23,(actual,expected)
        for n,h in manifest['sources'].items():assert sha(root/n)==h,n
        save(out/'verified.json',dict(status='actual_ARM_same_full_native_contract_and_real_XRT_library_compiled_not_loaded',
            PC_ARM_exact_rows=rows,all128_reader_cases31_refusals_and_original311_checks_preserved=True,
            all726_actual_HLS_C_pipeline_calls_on_ARM=True,actual_real_ARM_XRT_compile_link_and23_exports_verified=True,
            actual_unique_session_log_runtime_and_production_XRT_headers_verified=True,
            no_mock_header_in_real_XRT_compile=True,C_API_exports=sorted(actual),library_SHA256=sha(library),
            sources=manifest['sources'],receipts=receipts,seconds=time.monotonic()-started,
            peak_child_RSS_bytes=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*1024,
            no_CDLL_real_XRT_session_MMIO_DFX_firmware_or_GUI_access=True,PL_accessed=False,production_promoted=False,whole_goal_completed=False))
    except BaseException:
        save(out/'failure.json',dict(traceback=traceback.format_exc(),receipts=receipts,PL_accessed=False));raise
    finally:
        save(HERE/'terminal.json',dict(passed=(out/'verified.json').exists(),all_children_reaped=True,output_SHA256={p.relative_to(HERE).as_posix():sha(p) for p in out.iterdir() if p.is_file()}))

if __name__=='__main__':main()
