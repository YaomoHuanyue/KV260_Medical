"""Check checkout integrity, LFS materialization and declared build inputs."""
from pathlib import Path
import argparse,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
 with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def check(name,expected=None):
 p=(ROOT/name).resolve(strict=True);assert p.is_relative_to(ROOT),name
 if expected:assert sha(p)==expected,'SHA mismatch (run git lfs pull if needed): '+name
 return p
def main():
 p=argparse.ArgumentParser();p.add_argument('--source-only',action='store_true');a=p.parse_args()
 m=json.loads(check('ui/v3/manifest.json').read_bytes())
 for n,h in {**m['files_sha256'],**m['backend_files_sha256'],**m.get('installed_backend_files_sha256',{})}.items():check(n,h)
 if not a.source_only:check(m['binary'],m['binary_sha256'])
 check('hardware/frozen/static_routed.dcp','285f3d4a50af45cbea7f503f1f32789b0d84b55214163750a301267e2e72fcb9')
 hls=json.loads(check('hardware/hls_targets.json').read_bytes())
 for key,t in hls.items():
  check(t['source']);assert t['clock_ns']==10 and t['part']=='xck26-sfvc784-2LV-c',key
  if t.get('testbench'):check(t['testbench'])
 rms=json.loads(check('hardware/rm_targets.json').read_bytes())
 for key,t in rms.items():
  check(t['create']);assert all(n in hls for n in t['hls']),key
  for n in t.get('auxiliary_inputs',[]):check(n)
 native=json.loads(check('hardware/native_targets.json').read_bytes())
 for t in native.values():
  for n in t['sources']:check(n)
 lock=ROOT/'source.lock.json'
 if lock.is_file():
  for row in json.loads(lock.read_bytes())['files']:check(row['path'],row['SHA256'])
 print(json.dumps(dict(passed=True,source_only=a.source_only,UI_source_files=len(m['files_sha256']),HLS_targets=len(hls),RM_targets=len(rms),native_targets=len(native),PL_access=False)))
if __name__=='__main__':main()
