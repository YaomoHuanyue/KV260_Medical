"""Create the ignored per-board startup profile from an explicit local CT."""
from pathlib import Path
import argparse,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--ct',type=Path,required=True);p.add_argument('--result',type=Path);a=p.parse_args()
 ct=a.ct.resolve(strict=True);assert ct.is_relative_to(ROOT),'Place input CT inside this checkout, e.g. data/CT.nrrd'
 result=a.result.resolve(strict=True)if a.result else None
 if result:assert result.is_relative_to(ROOT)and(result/'pipeline.json').is_file()
 with ct.open('rb')as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
 profile=dict(schema='kv260.medical_autostart.v1',ui='v3',input=ct.relative_to(ROOT).as_posix(),input_SHA256=digest,result=result.relative_to(ROOT).as_posix()if result else None,missing_result='open_CT_only',compute_on_boot=False,synthetic_demo=False)
 path=ROOT/'system/autostart/profile.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(profile,indent=2)+'\n');print('Configured local case profile; CT/result data remain ignored by Git')
 runs=ROOT/'ui/runs';runs.mkdir(parents=True,exist_ok=True)
 with(runs/'.runner.lock').open('ab'):pass
if __name__=='__main__':main()
