"""Repair captured preparation catalogues; keep all qualified streaming algorithms."""
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def install():
    inputs=json.loads((HERE/'inputs.json').read_text())
    for n,h in inputs['source_SHA256'].items():
        p=(ROOT/n).resolve()
        if not p.is_relative_to(ROOT) or sha(p)!=h:raise RuntimeError('Changed qualified scene-repair input: '+n)
    from ui.releases.streaming_functional_r1.backend import install as parent
    from modules.view_assets_r1.nav_reuse_r1.reuse_r2 import Reuse
    backend=parent();reuse=backend.prepare.__self__
    if type(reuse) is not Reuse or reuse.original.__globals__ is not reuse.state:
        raise RuntimeError('The accepted optimized scene preparation contract changed')
    # Reuse copies the complete globals when compiling its manifest prefix.
    # Updating only backend_core_r6.catalogue leaves both scene functions stale.
    for namespace in (reuse.state,reuse.manifest.__globals__):namespace['catalogue']=backend.catalogue
    if reuse.original.__globals__['catalogue'] is not backend.catalogue or reuse.manifest.__globals__['catalogue'] is not backend.catalogue:
        raise RuntimeError('Incomplete candidate scene catalogue binding')
    return backend
def main():
    install()
    import backend_selected_r1 as accepted
    return accepted.main()
if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps(dict(event='error',text=str(error)),ensure_ascii=False),flush=True);sys.exit(1)
