"""Record independent legacy/physical-grid contracts on Windows or ARM."""
from pathlib import Path
import argparse
import ast
import hashlib
import io
import json
import platform
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    target=a.output.resolve();assert target.is_relative_to(ROOT/'modules/lesion_catalogue') and not target.exists()
    here=Path(__file__).resolve().parent;origin=json.loads((here/'reference_origin.json').read_text(encoding='utf-8'))
    oracle=here/'oracle.py';assert sha(oracle)==origin['oracle_sha256']
    s=oracle.read_text(encoding='utf-8');node=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef) and n.name=='component_report')
    assert hashlib.sha256(ast.get_source_segment(s,node).encode()).hexdigest()==origin['function_sha256']
    suite=unittest.defaultTestLoader.loadTestsFromName('modules.lesion_catalogue.test_catalogue')
    assert suite.countTestCases()==6
    log=io.StringIO();start=time.perf_counter();result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    record=dict(status='catalogue_original_Python_and_physical_export_contracts_passed' if result.wasSuccessful() else 'catalogue_contracts_failed',
        tests_run=result.testsRun,seconds=time.perf_counter()-start,platform=platform.platform(),
        test_log=log.getvalue(),source_sha256={f.relative_to(ROOT).as_posix():sha(f) for f in sorted(here.glob('*.py'))},
        reference_origin_sha256=sha(here/'reference_origin.json'),PL_accessed=False,
        original_masks_or_default_UI_changed=False,clinical_accuracy_validated=False)
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(log.getvalue(),flush=True);print(record['status'],flush=True)
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':main()
