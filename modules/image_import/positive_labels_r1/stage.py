"""Fresh partial-stage process: install qualified contracts before original imports."""
from pathlib import Path
import json,runpy,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
STAGES=('modules/reconstruction/streaming_functional_r2/run_partial.py',
        'modules/navigation_comparison/current_release_r1/task.py',
        'modules/airway_detail/run_recovery.py')

def selected_stage(value):
    path=Path(value).resolve(strict=True)
    if not path.is_relative_to(ROOT) or path not in [(ROOT/n).resolve(strict=True) for n in STAGES]:
        raise ValueError('Unexpected medical partial stage')
    return path

def main():
    if len(sys.argv)<4 or sys.argv[1]!='--stage':raise ValueError('Explicit medical partial stage required')
    path=selected_stage(sys.argv[2])
    from modules.image_import.positive_labels_r1.backend import install_contracts
    install_contracts()
    sys.argv=[str(path),*sys.argv[3:]]
    return runpy.run_path(str(path),run_name='__main__')

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps(dict(event='error',text=str(error)),ensure_ascii=False),flush=True);raise SystemExit(1)
