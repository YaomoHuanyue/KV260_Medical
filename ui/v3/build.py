"""Build the V3 candidate (Qt Widgets + QML shell) on KV260. Never touches ui/v2 or the accepted binary."""
from pathlib import Path
import argparse,hashlib,json,os,shlex,subprocess,time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
UNITS=['src/main.cpp','src/pl_composite.cpp','src/views.cpp','src/pl_scope.cpp']
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def inputs():
    files=[p for p in sorted(HERE.rglob('*')) if p.is_file() and p.parts[len(HERE.parts)] in ('src','qml','assets') ]+[HERE/'qml.qrc',HERE/'build.py']
    files+=sorted((ROOT/'modules/gamepad/include').glob('*'))+[ROOT/'modules/gamepad/config.json']
    return {str(p.relative_to(ROOT)):sha(p) for p in files}
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=HERE/'build');a=p.parse_args()
    assert os.name=='posix' and os.uname().machine=='aarch64','Run this build on KV260'
    out=a.output.resolve();assert out.is_relative_to(ROOT);out.mkdir(parents=True,exist_ok=True)
    binary=out/'medical_ui';gen=out/'generated';gen.mkdir(exist_ok=True)
    log=(out/'compile.log').open('wb');start=time.monotonic()
    def run(cmd):
        log.write(('$ '+' '.join(map(str,cmd))+'\n').encode());log.flush()
        return subprocess.run(cmd,cwd=HERE,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT).returncode
    rc=run(['moc','src/include/ui_bridge.hpp','-o',str(gen/'moc_ui_bridge.cpp')])
    rc=rc or run(['rcc','-name','v3','qml.qrc','-o',str(gen/'qrc_v3.cpp')])
    flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt5Widgets','Qt5OpenGL','Qt5Test','Qt5Quick','Qt5QuickWidgets','Qt5Qml'],text=True))
    if binary.exists():binary.unlink()
    cmd=['g++','-std=c++17','-O1','-fPIC','-pthread','-mcpu=cortex-a53','-I','src/include','-I',str(ROOT/'modules/gamepad/include'),*UNITS,str(gen/'moc_ui_bridge.cpp'),str(gen/'qrc_v3.cpp'),*flags,'-o',str(binary)]
    rc=rc or run(cmd)
    log.close()
    result={'passed':rc==0,'exit_code':rc,'seconds':time.monotonic()-start,'argv':cmd,'inputs_SHA256':inputs(),
            'compiler':subprocess.check_output(['g++','--version'],text=True).splitlines()[0],
            'ELF_SHA256':sha(binary) if binary.is_file() else None,'new_FPGA_build':False,'accepted_release_changed':False}
    (out/'compiled.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:result[k] for k in ('passed','seconds','ELF_SHA256')}),flush=True)
    raise SystemExit(0 if rc==0 else 1)
if __name__=='__main__':main()
