"""Unified, explicit module test entry. Firmware is never switched implicitly."""
import argparse,json
from pathlib import Path
from system.contracts import create_case,load_case,read_json,validate_artifact
from system.runner import ROOT,STAGES,run,import_masks,firmware,release_digest

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    q=sub.add_parser('import-ct');q.add_argument('case_id');q.add_argument('input',type=Path);q.add_argument('--series-uid')
    q=sub.add_parser('import-masks');q.add_argument('case_id');q.add_argument('source',type=Path)
    q=sub.add_parser('run');q.add_argument('case_id');q.add_argument('--stages',default=','.join(STAGES));q.add_argument('--from-masks',action='store_true')
    q.add_argument('--quality',choices=['full','preview'],default='full');q.add_argument('--surface',choices=['smooth','raw'],default='smooth')
    q.add_argument('--lesion-index',type=int,default=0);q.add_argument('--target-lps',nargs=3,type=float)
    q.add_argument('--scope-diameter-mm',type=float,default=1.);q.add_argument('--safety-margin-mm',type=float,default=.2);q.add_argument('--sample-mm',type=float,default=.5)
    sub.add_parser('doctor');q=sub.add_parser('status');q.add_argument('case_id')
    a=p.parse_args()
    if a.action=='import-ct':print(create_case(ROOT,a.case_id,a.input,a.series_uid));return
    if a.action=='doctor':print(json.dumps(dict(root=str(ROOT),release_sha256=release_digest(),loaded_firmware=firmware(),dfx_implemented=False),indent=2));return
    # A case ID must never be interpreted as an arbitrary filesystem path.
    import re
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',a.case_id):raise ValueError('Invalid case ID')
    case=ROOT/'cases'/a.case_id
    if a.action=='import-masks':print(import_masks(case,a.source));return
    if a.action=='status':
        load_case(case);print(json.dumps([read_json(f) for f in (case/'runs').glob('*/state.json')],ensure_ascii=False,indent=2));return
    options={k:getattr(a,k) for k in ['quality','surface','lesion_index','target_lps','scope_diameter_mm','safety_margin_mm','sample_mm']}
    import math
    nums=[options[k] for k in ('scope_diameter_mm','safety_margin_mm','sample_mm')]+(a.target_lps or [])
    if not all(math.isfinite(x) for x in nums) or a.scope_diameter_mm<0 or a.safety_margin_mm<0 or a.sample_mm<=0 or a.lesion_index<0:raise ValueError('Invalid navigation parameters')
    result=run(case,a.stages.split(','),options,a.from_masks);print(json.dumps(result,ensure_ascii=False,indent=2))
    if result['status']=='needs_firmware':raise SystemExit(20)

if __name__=='__main__':main()
