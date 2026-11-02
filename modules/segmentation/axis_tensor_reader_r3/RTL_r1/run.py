"""Actual generated RTL, all159 full cases, two schedules and reset recovery."""
from pathlib import Path
import hashlib,json,os,shutil,sys,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path[:0]=[str(ROOT/'dfx/navigation_profile/rtl_r74'),str(HERE)]
from job_limit_r74 import run,system_memory
import generate

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def save(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,indent=2)

def check_log(text,native):
    import re
    rows=re.findall(r'READER_RTL_FRAME case=(\d+) invalid=(\d+) packets=(\d+) cycles=(\d+)',text)
    assert len(rows)==165,len(rows)
    wanted=list(range(159))+[1,74,64,65,66,67]
    for row,index in zip(rows,wanted):
        n,invalid,packets,cycles=map(int,row);gold=native['cases'][index]
        assert n==index and invalid==gold['status'] and packets==gold['packets'] and cycles>0,(row,index)
    assert re.findall(r'READER_ACTUAL_RESET stage=(\d+)',text)==['0','1','2','3']
    assert 'READER_TWO_TRAILING_CALLS_NO_RESET_EXACT' in text
    final=re.findall(r'PASS READER_FULL159_TRAILING2_RESET4_RECOVERY4 frames=(\d+) resets=(\d+) reads=(\d+) beats=(\d+) axis_stalls=(\d+) ar_stalls=(\d+) r_stalls=(\d+)',text)
    assert len(final)==1 and final[0][:2]==('165','4')
    assert not any(token in text for token in ('ERROR:','FATAL:','Fatal:','cannot be opened for reading','WARNING: File'))
    return dict(full_frames=165,reset_recoveries=4,actual_counter_names=['frames','resets','reads','beats','axis_stalls','ar_stalls','r_stalls'],actual_counters=list(map(int,final[0])))

def main():
    assert os.name=='nt' and not (HERE/'run').exists()
    admission=json.loads((HERE/'admission.json').read_text());bindings=admission['source_SHA256']
    def verify():
        for n,h in bindings.items():assert sha(ROOT/n)==h,n
        for n,h in admission['generated_RTL_SHA256'].items():assert sha(HERE/'source_RTL'/n)==h,n
    verify();owned=ROOT.parent;assert owned.name.startswith('k26-r2450-')
    memory=system_memory();assert memory['free_commit_bytes']>=16*1024**3 and memory['physical_available_bytes']>=8*1024**3
    tmp=owned/'tmp';assert tmp.is_dir() and Path(os.environ['TEMP']).resolve()==tmp.resolve()
    system=Path(os.environ['SystemRoot']);tool=Path('D:/AMDDesignTools/2025.2.1/Vivado/bin')
    env=dict(os.environ,PROCESSOR_ARCHITECTURE='AMD64',PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',
        PATH=';'.join(map(str,[tool,system/'System32',system])),READER_OWNED_ROOT=owned.as_posix())
    native=json.loads((HERE.parent/'native_verified.json').read_text())
    rtl=(HERE/'source_RTL/ct_tensor_reader.v').read_text();stages=[];modes={};simdirs={}
    try:
        def stage(mode,name,argv,cwd):
            out=HERE/'run'/mode
            receipt=run(argv,cwd=cwd,env=dict(env,READER_RTL_MODE=mode),log=out/(name+'.log'),
                started=out/(name+'_started.json'),limit=8*1024**3)
            save(out/(name+'_receipt.json'),receipt);stages.append(dict(mode=mode,stage=name,receipt=receipt))
            assert receipt['exit_code']==0 and receipt['all_owned_processes_terminal'] and receipt['configured_limit_verified'],(mode,name)
            assert not receipt['resource_failure'] and not receipt['elapsed_time_abort'];verify()
        for mode in ('ordinary','random'):
            out=HERE/'run'/mode;generate.generate(out,rtl,native,mode)
            shutil.copyfile(ROOT/admission['hold_source'],out/'hold.sv')
            stage(mode,'setup',[str(tool/'vivado.bat'),'-mode','batch','-notrace','-source',str(HERE/'build_sim.tcl'),
                '-log',str(out/'vivado.log'),'-journal',str(out/'vivado.jou')],HERE)
            sim=owned/'s'/mode/'p/reader_sim.sim/sim_1/behav/xsim';assert sim.is_dir();simdirs[mode]=sim
            shutil.copyfile(out/'model_lut.hex',sim/'model_lut.hex')
            assert sha(sim/'model_lut.hex')==sha(out/'model_lut.hex')
            initializers={}
            for p in (HERE/'source_RTL').iterdir():
                if p.suffix in ('.dat','.mem','.hex'):
                    dest=sim/p.name;assert not dest.exists();shutil.copyfile(p,dest);assert sha(dest)==sha(p);initializers[p.name]=sha(dest)
            save(out/'initializers_staged.json',dict(actual_CWD=str(sim),files=initializers,model_lut_SHA256=sha(sim/'model_lut.hex')))
            for name in ('compile','elaborate'):stage(mode,name,[str(sim/(name+'.bat'))],sim)
        for mode in ('ordinary','random'):
            out=HERE/'run'/mode;sim=simdirs[mode]
            stage(mode,'simulate',[str(sim/'simulate.bat')],sim)
            modes[mode]=check_log((out/'simulate.log').read_text(errors='replace'),native)
            assert sha(sim/'model_lut.hex')==sha(out/'model_lut.hex')
            if mode=='random':assert modes[mode]['actual_counters'][4]>0 and modes[mode]['actual_counters'][5]>0
        save(HERE/'complete.json',dict(status='actual_R3_reader_full159_two_schedules_trailing_and_reset_recovery_RTL',
            original142_valid17_invalid_full_domains_in_both_schedules=True,
            all330_complete_frames_and8_actual_global_resets=True,
            full_packet_data_keep_strb_last_padding_and_no_trailing_contamination_checked=True,
            AXI_read_bounds_lowDDR_4K_ID_response_and_no_writes_checked=True,
            AXI_AXIL_AXIS_holds_checked=True,actual_modes=modes,actual_stages=stages,
            generated_RTL_SHA256=admission['generated_RTL_SHA256'],source_SHA256=bindings,
            source_HLS_archive_SHA256=admission['source_HLS_archive_SHA256'],
            original_model_three_join_dimensions_and_LUTs_preserved=True,
            actual_hardware_RM100MHz_5PR_ARM139_and_system_integration_pending=True,
            PL_accessed=False,production_promoted=False,whole_goal_completed=False))
        print('PASS actual R3 330 complete frames and8 global resets; physical/board integration remains',flush=True)
    except BaseException:
        save(HERE/'failure.json',dict(traceback=traceback.format_exc(),actual_stages=stages,source_SHA256=bindings,
            original_full159_scope_not_reduced=True,whole_goal_completed=False));raise

if __name__=='__main__':main()
