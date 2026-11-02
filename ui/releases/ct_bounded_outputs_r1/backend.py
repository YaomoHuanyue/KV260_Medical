"""Preserve the accepted dispatcher; select the qualified bounded full-output CT entry."""
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def install():
    from modules.ct_preprocess.axis_hu_32_r2.bounded_volume_r3.entry_r1 import verify_qualification
    verify_qualification()
    from ui.releases.pl_reconstruction_r2.backend import install as parent_install
    backend=parent_install()
    proof=json.loads((HERE/'derivation.json').read_text())['dispatcher']
    parent=ROOT/proof['parent'];assert sha(parent)==proof['parent_SHA256']
    source=parent.read_text()
    for edit in proof['literal_edits']:
        assert source.count(edit['before'])==1;source=source.replace(edit['before'],edit['after'])
    assert source==(HERE/'dispatch.py').read_text() and sha(HERE/'dispatch.py')==proof['candidate_SHA256']
    exec(compile(source,str(HERE/'dispatch.py'),'exec'),backend.__dict__)
    return backend


def main():
    install()
    import backend_selected_r1 as accepted
    return accepted.main()


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps(dict(event='error',text=str(error)),ensure_ascii=False),flush=True);sys.exit(1)
