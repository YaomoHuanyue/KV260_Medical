"""Native ARM build from this checkout only; keep generated files under build/."""
from pathlib import Path
import argparse,concurrent.futures,hashlib,json,os,shlex,subprocess,time
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
 with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--jobs',type=int,choices=(1,2),default=1);a=p.parse_args()
 assert os.name=='posix'and os.uname().machine=='aarch64','Build on KV260 / aarch64 Linux with Qt5 development packages'
 runs=ROOT/'ui/runs';runs.mkdir(parents=True,exist_ok=True)
 with(runs/'.runner.lock').open('ab'):pass
 src=ROOT/'ui/v3/src';out=ROOT/'build/software';out.mkdir(parents=True,exist_ok=True)
 packages=['Qt5Widgets','Qt5OpenGL','Qt5Test','Qt5Quick','Qt5QuickWidgets','Qt5Qml']
 flags=shlex.split(subprocess.check_output(['pkg-config','--cflags',*packages],text=True));libs=shlex.split(subprocess.check_output(['pkg-config','--libs',*packages],text=True))
 commands=[];start=time.monotonic()
 for cmd in [['moc',str(src/'include/ui_bridge.hpp'),'-o',str(out/'moc_ui_bridge.cpp')],['rcc','-name','v3',str(ROOT/'ui/v3/qml.qrc'),'-o',str(out/'qrc_v3.cpp')]]:subprocess.run(cmd,check=True);commands.append(cmd)
 includes=['-I',str(src/'include'),'-I',str(ROOT/'modules/gamepad/include')]
 def unit(path):
  obj=out/(path.stem+'.o');cmd=['g++','-std=c++17','-O0'if path.name=='main.cpp'else'-O1','-fPIC','-pthread','-mcpu=cortex-a53',*includes,*flags,'-c',str(path),'-o',str(obj)]
  with(out/(path.name+'.log')).open('wb')as f:subprocess.run(cmd,check=True,stdout=f,stderr=subprocess.STDOUT)
  return cmd,obj
 units=[src/n for n in ('main.cpp','views.cpp','pl_scope.cpp','pl_composite.cpp')]+[out/'moc_ui_bridge.cpp',out/'qrc_v3.cpp']
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs)as pool:built=list(pool.map(unit,units))
 commands.extend(x[0]for x in built);binary=ROOT/'ui/v3/bin/medical_ui';binary.parent.mkdir(exist_ok=True)
 cmd=['g++','-pthread',*[str(x[1])for x in built],*libs,'-o',str(binary)];subprocess.run(cmd,check=True);commands.append(cmd)
 env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software',PYTHONDONTWRITEBYTECODE='1');env.pop('LD_PRELOAD',None)
 subprocess.run([str(binary),'--root',str(ROOT),'--simplification-check','--evidence',str(out)],env=env,check=True,stdout=(out/'control.log').open('wb'),stderr=subprocess.STDOUT,timeout=60)
 test=out/'test_gamepad';cmd=['g++','-std=c++17','-O1','-fPIC','-pthread','-mcpu=cortex-a53',*includes,*flags,str(ROOT/'modules/gamepad/tests/test_gamepad.cpp'),str(out/'views.o'),*libs,'-o',str(test)];subprocess.run(cmd,check=True);commands.append(cmd)
 subprocess.run([str(test),str(ROOT/'modules/gamepad/config.json'),str(out/'gamepad.json')],env=env,check=True,stdout=(out/'gamepad.log').open('wb'),stderr=subprocess.STDOUT,timeout=60)
 assert json.loads((out/'simplification.json').read_bytes())['passed']and json.loads((out/'gamepad.json').read_bytes())['passed']
 manifest=ROOT/'ui/v3/manifest.json';m=json.loads(manifest.read_bytes());baseline=sha(manifest);m['binary_sha256']=sha(binary)
 for n in m['files_sha256']:m['files_sha256'][n]=sha(ROOT/n)
 m['build_from_checkout']=dict(passed=True,baseline_manifest_SHA256=baseline,PL_or_clinical_requalification=False)
 manifest.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');(ROOT/'ui/active_release.json').write_bytes(manifest.read_bytes())
 result=dict(passed=True,seconds=time.monotonic()-start,ELF_SHA256=sha(binary),compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0],commands=commands,source_root=str(ROOT),checks=json.loads((out/'gamepad.json').read_bytes())['checks'],PL_access=False)
 (out/'verified.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='commands'}))
if __name__=='__main__':main()
