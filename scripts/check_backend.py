"""Read-only dispatch/admission probe: no XRT Session, PL operation or clinical claim."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
def main():
 sys.path[:0]=[str(ROOT),str(ROOT/'modules/segmentation')]
 from modules.segmentation.speedup_r1.backend import install
 path=ROOT/'modules/segmentation/reader_burst/candidate_ui_selection.json'
 value=install(path,hashlib.sha256(path.read_bytes()).hexdigest(),ROOT/'build/runtime_probe',1)
 from modules.reconstruction.smooth_pipeline_r2.axis_tile1024_r1.host_D9_r1.hardware_r1.seal_release import verify
 verify(installed=False)
 imported=[]
 for name,module in tuple(sys.modules.items()):
  f=getattr(module,'__file__',None)
  if not f:continue
  p=Path(f).resolve()
  if p.is_relative_to(ROOT):imported.append(str(p.relative_to(ROOT)))
  elif 'KV260_System'in str(p)and 'site-packages'not in str(p):raise RuntimeError('Imported original project code: '+str(p))
 result=dict(passed=True,source_root=str(ROOT),dispatch_built=True,D9_release_verified=True,project_modules=sorted(set(imported)),PL_access=False)
 out=ROOT/'build/runtime_probe';out.mkdir(parents=True,exist_ok=True);(out/'verified.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
