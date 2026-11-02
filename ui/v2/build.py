"""Build V2 directly from its four C++ translation units on KV260."""
from pathlib import Path
import argparse,hashlib,json,os,shlex,subprocess,time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=HERE/'build/medical_ui');a=p.parse_args()
    assert os.name=='posix' and os.uname().machine=='aarch64','Run this build on KV260'
    output=a.output.resolve();assert output.is_relative_to(ROOT) and not output.exists()
    data=json.loads((HERE/'manifest.json').read_bytes())
    for name,h in data['files_sha256'].items():assert sha(ROOT/name)==h,name
    output.parent.mkdir(parents=True,exist_ok=True)
    flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt5Widgets','Qt5OpenGL','Qt5Test'],text=True))
    command=['g++','-std=c++17','-O1','-fPIC','-pthread','-mcpu=cortex-a53',
             '-I',str(HERE/'src/include'),*[str(HERE/n) for n in data['build_roots']],*flags,'-o',str(output)]
    start=time.monotonic()
    with (output.parent/'compile.log').open('xb') as log:
        code=subprocess.run(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT).returncode
    result={'passed':code==0,'exit_code':code,'seconds':time.monotonic()-start,
            'argv':command,'source_SHA256':data['files_sha256'],'reused_objects':[],
            'compiler':subprocess.check_output(['g++','--version'],text=True).splitlines()[0],
            'ELF_SHA256':sha(output) if output.is_file() else None,'new_FPGA_build':False}
    (output.parent/'compiled.json').write_text(json.dumps(result,indent=2)+'\n')
    assert code==0,'See compile.log; accepted binary remains unchanged'
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen')
    help_result=subprocess.run([str(output),'--help'],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    (output.parent/'help.log').write_bytes(help_result.stdout+help_result.stderr)
    assert help_result.returncode==0 and b'--root' in help_result.stdout
    (output.parent/'verified.json').write_text(json.dumps({'clean_four_unit_build':True,'help_passed':True,
        'old_frontend_directories_required':False,'ELF_SHA256':result['ELF_SHA256'],'accepted_release_changed':False},indent=2)+'\n')
    print(json.dumps({'passed':True,'seconds':result['seconds'],'ELF_SHA256':result['ELF_SHA256']}),flush=True)

if __name__=='__main__':main()
