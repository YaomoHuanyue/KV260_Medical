"""Compile and inspect the real ARM/XRT host; never instantiate a device/session."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,platform,resource,subprocess,time,traceback
HERE=Path(__file__).resolve().parent;CORE=HERE.parent;ROOT=CORE.parents[2]

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def save(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,indent=2)

def main():
    assert platform.machine()=='aarch64'
    out=HERE/'ARM';assert not out.exists();out.mkdir()
    started=time.monotonic();derivation=json.loads((HERE/'derivation.json').read_text())
    inputs=json.loads((HERE/'ARM_inputs.json').read_text())['source_and_evidence_SHA256']
    assert all(inputs.get(n)==h for n,h in derivation['source_and_evidence_SHA256'].items())
    for n,h in inputs.items():assert sha(ROOT/n)==h,n
    started_record=dict(PID=os.getpid(),boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        start_ticks=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]),UTC=datetime.now(timezone.utc).isoformat())
    save(out/'started.json',started_record)
    stage=None
    try:
        headers=[p for p in map(Path,('/usr/include','/usr/include/xrt','/opt/xilinx/xrt/include')) if (p/'xrt/xrt_bo.h').is_file()]
        assert headers,'XRT development headers are missing'
        root=ROOT/'dfx/medical/host_extended';library=out/'libct_pool_candidate.so'
        argv=['/usr/bin/g++','-std=c++17','-O2','-fPIC','-shared','-ffp-contract=off','-fno-fast-math','-pthread',
            '-Wl,-z,defs','-I',str(root),*[f'-I{p}' for p in headers],str(HERE/'ct_pool_bridge.cpp')]
        argv.extend(f'-L{p}' for p in (Path('/opt/xilinx/xrt/lib'),Path('/usr/lib/aarch64-linux-gnu')) if p.is_dir())
        argv+=['-lxrt_coreutil','-o',str(library)]
        def bounded():resource.setrlimit(resource.RLIMIT_AS,(1536*1024**2,1536*1024**2))
        with (out/'compile.log').open('xb') as log:
            result=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,preexec_fn=bounded)
        stage=dict(argv=argv,exit_code=result.returncode,seconds=time.monotonic()-started,
            peak_child_RSS_bytes=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*1024,
            child_address_space_limit_bytes=1536*1024**2)
        save(out/'compile_receipt.json',stage);assert result.returncode==0,'Real ARM compiler rejected candidate'
        raw=library.read_bytes();assert raw[:4]==b'\x7fELF' and raw[4:6]==b'\x02\x01' and int.from_bytes(raw[18:20],'little')==183
        symbols=subprocess.run(['/usr/bin/nm','-D','--defined-only',str(library)],capture_output=True,check=True).stdout.decode()
        required=('ct_pool_abi','ct_set_pool_lut','ct_execute_pool_mapped','ct_output_acquire','ct_output_map',
            'ct_output_release','ct_output_mark_ps_written','ct_execute_mapped','ct_open','ct_close')
        names={line.split()[-1] for line in symbols.splitlines() if line.strip()}
        assert set(required)<=names
        (out/'defined_symbols.txt').write_text(symbols)
        for n,h in inputs.items():assert sha(ROOT/n)==h,n
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==started_record['boot']
        save(out/'verified.json',dict(status='real_ARM_XRT_dual_output_host_compiled_ELF_exports_verified_not_executed',
            architecture='aarch64',all_required_typed_C_symbols_present=True,required_symbols=list(required),
            library_SHA256=sha(library),library_bytes=library.stat().st_size,stage=stage,
            no_CDLL_or_ct_open_or_XRT_device_MMIO_or_PL_lock_or_bitstream_access=True,
            native_lifecycle_RTL_route_DFX_board_numerics_and_PS_comparison_still_required=True,
            source_and_evidence_SHA256={**inputs,Path(__file__).relative_to(ROOT).as_posix():sha(Path(__file__))},
            PL_accessed=False,production_promoted=False,whole_goal_completed=False))
        print('PASS real ARM/XRT dual-output bridge compiled; ELF exports verified; hardware unopened',flush=True)
    except BaseException:
        save(out/'failure.json',dict(traceback=traceback.format_exc(),stage=stage,PL_accessed=False,production_promoted=False,whole_goal_completed=False));raise

if __name__=='__main__':main()
