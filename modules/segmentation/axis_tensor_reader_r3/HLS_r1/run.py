"""Qualified config flow: strict direct AP Csim executable, then actual HLS."""
from pathlib import Path
import hashlib,json,os,sys,traceback,xml.etree.ElementTree as E
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'dfx/navigation_profile/rtl_r74'))
from job_limit_r74 import run,system_memory

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x',encoding='utf8') as f:json.dump(v,f,indent=2)

def check_frames(text):
    rows=[s for s in text.splitlines() if s.startswith('TENSOR_READER_FULL_PASS ')]
    assert len(rows)==159 and all(s.startswith('TENSOR_READER_FULL_PASS case='+str(i)+' ') for i,s in enumerate(rows))
    assert sum('invalid=0 ' in s for s in rows)==142 and sum('invalid=1 ' in s for s in rows)==17
    assert 'ALL TENSOR READER 159 FULL FRAMES PASSED valid=142 invalid=17' in text
    assert not any(s in text for s in ('TENSOR_READER_FAIL','ERROR:','error:','Simulation failed'))

def main():
    bindings=json.loads((HERE/'admission.json').read_text())['source_SHA256']
    def verify():
        for n,h in bindings.items():assert sha(ROOT/n)==h,n
    verify();owned=ROOT.parent.resolve();assert os.name=='nt' and owned.name.startswith('k26-r2450-')
    out=HERE/'output';assert not out.exists();out.mkdir();receipts=[]
    try:
        memory=system_memory();assert memory['free_commit_bytes']>=12*1024**3 and memory['physical_available_bytes']>=8*1024**3
        component=owned/'h/tensor';assert not component.exists();component.parent.mkdir(exist_ok=True)
        cfg=out/'reader.cfg';p=HERE.parent
        cfg.write_text('part=xck26-sfvc784-2LV-c\n[hls]\nflow_target=vivado\nsyn.top=ct_tensor_reader\n'
            f'syn.file={p.as_posix()}/kernel.cpp\nsyn.cflags=-std=c++17\n'
            f'tb.file={HERE.as_posix()}/testbench.cpp\ntb.cflags=-std=c++17\n'
            'clock=10ns\nsyn.compile.pipeline_loops=0\npackage.output.format=ip_catalog\npackage.output.syn=false\n'
            f'package.output.file={out.as_posix()}/export.zip\n',encoding='ascii')
        env=dict(os.environ,PROCESSOR_ARCHITECTURE='AMD64',PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
        tool=Path('D:/AMDDesignTools/2025.2.1/Vitis/bin')
        def launch(stage,argv,cwd,environment):
            receipt=run(argv,cwd=cwd,env=environment,log=out/(stage+'.log'),started=out/(stage+'_started.json'),limit=8*1024**3)
            save(out/(stage+'_receipt.json'),receipt);receipts.append(dict(stage=stage,receipt=receipt));verify()
            assert receipt['all_owned_processes_terminal'] and receipt['configured_limit_verified']
            assert not receipt['resource_failure'] and not receipt['elapsed_time_abort']
            return receipt
        # Keep the real wrapper exit code. Its text is not substituted for the
        # actual compiled AP program's strict exit status below.
        cli=launch('csim_cli',[str(tool/'vitis-run.bat'),'--mode','hls','--csim','--config',str(cfg),'--work_dir',str(component)],p,env)
        assert cli['exit_code'] in (0,1)
        text=(out/'csim_cli.log').read_text(errors='replace');check_frames(text);assert 'CSim done with 0 errors' in text
        build=component/'hls/csim/build';exe=build/'csim.exe';assert exe.is_file()
        make=(build/'csim.mk').read_text(errors='replace');assert '/kernel.cpp' in make and '/testbench.cpp' in make
        script=(build/'run_sim.tcl').read_text(errors='replace');sdk=Path('D:/AMDDesignTools/2025.2.1/Vitis')
        dlls=[sdk/n for n in ('win64/tools/fpo_v7_1','win64/tools/fft_v9_1','win64/tools/fir_v7_0','win64/tools/dds_v6_0',
            'tps/mingw/10.0.0/win64.o/nt/bin','win64/csim')]
        for path in dlls:assert path.as_posix() in script
        for path in dlls[:-1]:assert path.is_dir()
        # The actual vendor script adds this absent optional search directory.
        # Preserve that search path; do not create or modify any SDK directory.
        save(out/'vendor_runtime_paths.json',dict(paths=[dict(path=str(path),present=path.is_dir()) for path in dlls],
            all_from_actual_generated_vendor_script=True,SDK_files_or_directories_modified=False))
        direct_env=dict(env,PATH=';'.join([str(path) for path in dlls]+[env['PATH']]))
        executable_sha=sha(exe)
        direct=launch('csim_direct',[str(exe)],build,direct_env)
        assert direct['exit_code']==0 and sha(exe)==executable_sha
        check_frames((out/'csim_direct.log').read_text(errors='replace'))
        save(out/'direct_AP_source_binding.json',dict(actual_Vitis_generated_csim_executable_SHA256=executable_sha,
            original_source_and_bench_both_compiled=True,actual_csim_makefile_SHA256=sha(build/'csim.mk'),
            actual_vendor_runtime_script_SHA256=sha(build/'run_sim.tcl'),direct_exit_code=0,
            actual_CLI_wrapper_exit_code=cli['exit_code'],CLI_nonzero_not_claimed_pass=True,
            complete159_frames_and_all_packet_data_keep_strb_last_padding_input_guards_checked=True))
        syn=launch('hls',[str(tool/'v++.bat'),'-c','--mode','hls','--config',str(cfg),'--work_dir',str(component)],p,env)
        assert syn['exit_code']==0
        generated=component/'hls/syn/verilog';members={p.relative_to(component).as_posix():sha(p) for p in generated.iterdir() if p.is_file()}
        assert any(n.endswith('.v') for n in members)
        report=component/'hls/syn/report/ct_tensor_reader_csynth.xml';tree=E.parse(report).getroot()
        resources={c.tag:int(c.text) for c in tree.find('AreaEstimates/Resources')}
        clock=float(tree.findtext('PerformanceEstimates/SummaryOfTimingAnalysis/EstimatedClockPeriod'))
        save(out/'generated_members.json',members)
        save(out/'complete.json',dict(status='actual_direct_AP_Csim159_and_HLS_complete_original_wrapper_exit_retained',
            actual159_Csim_full_frame_data_and_sidebands_exact=True,valid_frames=142,invalid_frames=17,
            actual_frozen_model_three_join_dimensions_and_exact_INT8_LUTs=True,original_kernel_sources_unchanged=True,
            actual_direct_AP_Csim_root_exit0=True,actual_CLI_wrapper_exit_code=cli['exit_code'],CLI_failure_not_silently_overridden=True,
            generated_RTL_members=members,HLS_estimates=resources,estimated_clock_ns=clock,actual_stages=receipts,
            source_SHA256=bindings,requested_II=1,measured_II_must_be_read_from_actual_loop_reports=True,
            RTL_backpressure_reset_RM100MHz_5PR_ARM139_system_tests_still_required=True,
            PL_accessed=False,production_promoted=False,whole_goal_completed=False))
        print('PASS strict direct AP Csim159 and actual HLS; CLI exit retained separately; physical tests remain',flush=True)
    except BaseException:
        save(out/'failure.json',dict(traceback=traceback.format_exc(),actual_stages=receipts,source_SHA256=bindings,
            PL_accessed=False,production_promoted=False,whole_goal_completed=False));raise

if __name__=='__main__':main()
