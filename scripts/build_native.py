"""Rebuild a native library candidate without overwriting its accepted release."""
from pathlib import Path
import argparse,json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1]
def main():
 targets=json.loads((ROOT/'hardware/native_targets.json').read_bytes());p=argparse.ArgumentParser();p.add_argument('target',nargs='?',choices=sorted(targets));p.add_argument('--list',action='store_true');a=p.parse_args()
 if a.list:
  for k,v in targets.items():print(k+' -> '+v['output_reference'])
  return
 assert a.target,'Select a target or --list';assert os.name=='posix'and os.uname().machine=='aarch64','Use the KV260/aarch64 XRT SDK environment'
 t=targets[a.target];out=ROOT/'build/native'/a.target;out.mkdir(parents=True,exist_ok=True);binary=out/Path(t['output_reference']).name
 for n in t['sources']:assert(ROOT/n).is_file(),n
 cmd=['g++',*[s.replace('{ROOT}',str(ROOT))for s in t['arguments']],'-o',str(binary)];start=time.monotonic()
 with(out/'compile.log').open('wb')as f:code=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT).returncode
 receipt=dict(passed=code==0,exit_code=code,command=cmd,seconds=time.monotonic()-start,released_library_overwritten=False,PL_access=False)
 (out/'compiled.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt));sys.exit(code)
if __name__=='__main__':main()
