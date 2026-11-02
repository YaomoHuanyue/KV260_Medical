"""Accepted full UI dispatcher, with formal qualified D7 and FMA2 entries."""
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def install():
    inputs=json.loads((HERE/'inputs.json').read_text())
    for name,digest in inputs['files_SHA256'].items():
        path=(ROOT/name).resolve();assert path.is_relative_to(ROOT) and sha(path)==digest,name
    proof=json.loads((ROOT/inputs['combined_board_proof']).read_text())
    assert proof['actual_D7_FMA2_same_context_passed'] and proof['actual_full_and_partial_entries_passed']
    from modules.reconstruction.axis_mc_r1.host_integrated_r2.runtime import verify_release
    verify_release() # Check qualified files/firmware only; no PL access.
    from ui.releases.pl_preprocess_r1.backend import install as parent_install
    backend=parent_install()
    derivation=json.loads((HERE/'derivation.json').read_text())['dispatcher']
    parent=ROOT/derivation['parent'];assert sha(parent)==derivation['parent_SHA256']
    source=parent.read_text()
    for before,after in derivation['literal_edits']:
        assert source.count(before)==1;source=source.replace(before,after)
    assert source==(HERE/'dispatch.py').read_text() and sha(HERE/'dispatch.py')==derivation['output_SHA256']
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
