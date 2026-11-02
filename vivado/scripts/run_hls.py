"""Ross hls-run-flow commands with repository-relative inputs and ignored output."""
from pathlib import Path
import argparse,json,os,shutil,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1]
def main():
 targets=json.loads((ROOT/'hardware/hls_targets.json').read_bytes());p=argparse.ArgumentParser();p.add_argument('target',choices=sorted(targets));p.add_argument('stage',choices=['csim','csynth','cosim','package']);p.add_argument('--tools',type=Path,help='Vitis directory containing bin; otherwise AMD_VITIS_ROOT or PATH');a=p.parse_args();t=targets[a.target]
 out=ROOT/'build/hls'/a.target;out.mkdir(parents=True,exist_ok=True);cfg=out/'design.cfg'
 for n in [t['source']]+([t['testbench']]if t.get('testbench')else[]):assert(ROOT/n).is_file(),n
 lines=['part='+t['part'],'[hls]','flow_target=vivado','syn.top='+t['top'],'syn.file='+(ROOT/t['source']).as_posix(),'syn.cflags=-std=c++14','clock=10ns','syn.compile.pipeline_loops=0','csim.code_analyzer=0','csim.O=true','package.output.format=ip_catalog','package.output.syn=false']
 extra_cflags=os.environ.get('KV260_HLS_CFLAGS','');extra_ldflags=os.environ.get('KV260_HLS_LDFLAGS','')
 assert '\n'not in extra_cflags+extra_ldflags,'Compiler flags must be a single line'
 lines[5]='syn.cflags=-std=c++14'+(' '+extra_cflags if extra_cflags else '')
 if t.get('testbench'):lines+=['tb.file='+(ROOT/t['testbench']).as_posix(),'tb.cflags=-std=c++14'+(' '+extra_cflags if extra_cflags else '')]
 if extra_ldflags:lines+=['csim.ldflags='+extra_ldflags]
 if a.stage in('csim','cosim')and not t.get('testbench'):raise RuntimeError('No self-contained testbench registered for this kernel')
 if a.stage=='cosim':assert(out/'hls/syn').is_dir(),'Run csynth first'
 cfg.write_text('\n'.join(lines)+'\n',encoding='utf8')
 base=a.tools or(Path(os.environ['AMD_VITIS_ROOT'])if os.environ.get('AMD_VITIS_ROOT')else None)
 name='v++'if a.stage=='csynth'else'vitis-run';exe=(base/'bin'/(name+('.bat'if os.name=='nt'else'')))if base else shutil.which(name)
 assert exe and Path(exe).is_file(),'Set --tools or AMD_VITIS_ROOT to Vitis 2025.2.1'
 cmd=[str(exe),*(['--compile','--mode','hls']if a.stage=='csynth'else['--mode','hls','--'+a.stage]),'--config',str(cfg),'--work_dir',str(out)]
 env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PROCESSOR_ARCHITECTURE='AMD64')
 if a.target=='hu32':
  lut=out/'synthetic_lut.bin';lut.write_bytes(bytes((i*37+19)&255 for i in range(1401)));env['HU_AXIS_LUT_FILE']=str(lut)
 start=time.monotonic()
 with(out/(a.stage+'.log')).open('wb')as f:rc=subprocess.run(cmd,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
 record=dict(stage=a.stage,target=a.target,passed=rc==0,exit_code=rc,argv=cmd,seconds=time.monotonic()-start,official_skill='hls-run-flow 1.0.0',extra_cflags=extra_cflags,extra_ldflags=extra_ldflags,bitstream_or_board_verified=False)
 (out/(a.stage+'.json')).write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record));sys.exit(rc)
if __name__=='__main__':main()
