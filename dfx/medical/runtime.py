"""Task-scoped DFX reconstruction session. No daemon, whole-bit load, or PS fallback."""
from pathlib import Path
import json,subprocess,time

ROOT=Path(__file__).resolve().parent
class Session:
    def __init__(self):
        self.process=None
    def __enter__(self):
        verify_release()
        self.process=subprocess.Popen([str(ROOT/'host/medical_worker')],cwd=ROOT,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
        if self.process.stdout.readline().strip()!='READY':
            self.process.stdin.close();self.process.wait();self.process.stdout.close()
            raise RuntimeError('DFX worker did not start; see diagnostic')
        return self
    def run(self,op,folder,output,report):
        paths=[op,str(Path(folder).resolve()),str(Path(output).resolve()),str(Path(report).resolve())]
        if any(any(c in p for c in '\t\r\n') for p in paths):raise ValueError('Invalid worker field')
        self.process.stdin.write('\t'.join(paths)+'\n');self.process.stdin.flush()
        if self.process.stdout.readline().strip()!='DONE':raise RuntimeError('DFX worker failed; see diagnostic')
        return json.loads(Path(report).read_text())
    def __exit__(self,*error):
        if self.process:
            try:self.process.stdin.close()
            except BrokenPipeError:pass
            # A timed-out accelerator retains BOs; NEVER kill it during cleanup.
            code=self.process.wait();self.process.stdout.close()
            if code and error[0] is None:raise RuntimeError(f'DFX worker exited {code}')
def verify_release():
    import hashlib
    release=ROOT/'release';m=json.loads((release/'manifest.json').read_text())
    if m['offline_verified'] is not True:raise RuntimeError('Unverified DFX package')
    for name,sha in m['files'].items():
        if hashlib.sha256((release/name).read_bytes()).hexdigest()!=sha:raise RuntimeError(f'Changed release file: {name}')
    if Path('/run/kv260-dfx-medical-loaded.sha256').read_text().strip()!=m['bit_bin_sha256']:
        raise RuntimeError('Medical static shell is not loaded; explicit manual load required')
    for name in ('mc','smooth'):
        key=f'medical_{name}_partial.bin'
        if hashlib.sha256((Path('/lib/firmware')/key).read_bytes()).hexdigest()!=m['files'][key]:raise RuntimeError('Installed partial differs')
