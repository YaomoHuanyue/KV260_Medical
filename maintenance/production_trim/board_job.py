from pathlib import Path
import concurrent.futures,hashlib,json,os,shlex,subprocess,sys,time,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def save(n,v):(HERE/n).write_text(json.dumps(v,indent=2)+'\n')
def main():
 mode=sys.argv[1];save('status.json',dict(stage=mode,PID=os.getpid(),passed=None));start=time.monotonic()
 manifest=json.loads((HERE/'candidate_manifest.json').read_bytes())
 flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','Qt5Widgets','Qt5OpenGL','Qt5Test'],text=True));libs=shlex.split(subprocess.check_output(['pkg-config','--libs','Qt5Widgets','Qt5OpenGL','Qt5Test'],text=True))
 def compile_one(name):
  src=HERE/'ui/v2'/name;obj=HERE/(src.stem+'.o');optimization='-O0'if src.name=='main.cpp'else'-O1';cmd=['g++','-std=c++17',optimization,'-fPIC','-pthread','-mcpu=cortex-a53','-I',str(HERE/'ui/v2/src/include'),*flags]
  cmd+=['-fsyntax-only',str(src)]if mode=='syntax'else['-c',str(src),'-o',str(obj)]
  dependencies={n:h for n,h in manifest['files_sha256'].items()if not n.endswith('.cpp')or n=='ui/v2/'+name}
  signature=hashlib.sha256(json.dumps(dict(dependencies=dependencies,command=cmd),sort_keys=True).encode()).hexdigest();receipt=HERE/(src.stem+'_unit.json')
  if mode=='build'and receipt.exists()and obj.exists():
   old=json.loads(receipt.read_bytes())
   with obj.open('rb')as f:object_sha=hashlib.file_digest(f,'sha256').hexdigest()
   if old['signature']==signature and old['object_SHA256']==object_sha:return cmd,str(obj)
  run=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
  (HERE/(src.stem+'.log')).write_text(run.stdout)
  if run.returncode:print(run.stdout[-9000:],flush=True);raise RuntimeError(src.name+' failed')
  if mode=='build':
   with obj.open('rb')as f:object_sha=hashlib.file_digest(f,'sha256').hexdigest()
   receipt.write_text(json.dumps(dict(signature=signature,object_SHA256=object_sha,command=cmd))+'\n')
  return cmd,str(obj)
 available=int(next(line.split()[1]for line in Path('/proc/meminfo').read_text().splitlines()if line.startswith('MemAvailable:')))*1024
 jobs=2 if mode=='build'and available>1_700_000_000 else 1
 with concurrent.futures.ThreadPoolExecutor(max_workers=jobs)as pool:records=list(pool.map(compile_one,manifest['build_roots']))
 commands=[r[0]for r in records];objects=[r[1]for r in records]
 if mode=='syntax':save('status.json',dict(passed=True,stage='syntax_passed',seconds=time.monotonic()-start));return
 cmd=['g++','-pthread',*objects,*libs,'-o',str(HERE/'medical_ui')];subprocess.run(cmd,check=True);commands.append(cmd)
 env=dict(os.environ,QT_QPA_PLATFORM='offscreen');env.pop('LD_PRELOAD',None)
 subprocess.run([str(HERE/'medical_ui'),'--root',str(ROOT),'--simplification-check','--evidence',str(HERE)],env=env,check=True,stdout=subprocess.DEVNULL,timeout=60)
 with(HERE/'medical_ui').open('rb')as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
 manifest['binary_sha256']=sha;save('candidate_manifest.json',manifest);save('compiled.json',dict(passed=True,ELF_SHA256=sha,commands=commands,source_SHA256=manifest['files_sha256'],seconds=time.monotonic()-start,new_bitstream=False));save('status.json',dict(passed=True,stage='compiled'))
if __name__=='__main__':
 try:main()
 except BaseException as e:save('status.json',dict(passed=False,stage='failed',error=str(e)));traceback.print_exc()
