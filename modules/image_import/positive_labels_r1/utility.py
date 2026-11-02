"""Preserve original utility actions while enforcing qualified positive-label contracts."""
from pathlib import Path
import json,runpy,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
def main():
    if len(sys.argv)<4 or sys.argv[1]!='--adapter':raise ValueError('Explicit medical utility adapter required')
    adapter=Path(sys.argv[2]).resolve(strict=True)
    allowed=[ROOT/'modules/image_import/positive_labels_r1/entry.py',ROOT/'modules/surface_route/export_backend_r21.py',ROOT/'modules/report_export/backend.py']
    if adapter not in [p.resolve(strict=True)for p in allowed]:raise ValueError('Unexpected medical utility adapter')
    from modules.image_import.positive_labels_r1.backend import install_contracts
    install_contracts()
    sys.argv=[str(adapter),*sys.argv[3:]]
    runpy.run_path(str(adapter),run_name='__main__')
if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps(dict(event='error',text=str(error)),ensure_ascii=False),flush=True);raise SystemExit(1)
