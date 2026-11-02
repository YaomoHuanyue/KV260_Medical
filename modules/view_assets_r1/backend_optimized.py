"""Exact preparation extension of the frozen medical backend, no kernel changes."""
from pathlib import Path
import hashlib,json,sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE=ROOT/'ui/releases/feature_completion_r6/backend_core_r6.py'


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def namespace(target=None):
    sys.path[:0]=[str(ROOT),str(ROOT/'ui'),str(BASE.parent)]
    from modules.view_assets_r1.exact import cluster_inverse,is_binary
    released=json.loads((ROOT/'ui/active_release.json').read_text())
    assert sha(BASE)==released['files_sha256'][BASE.relative_to(ROOT).as_posix()]
    source=BASE.read_text()
    changes={
        '            _,inv=np.unique(np.floor(points/cell).astype(np.int32),axis=0,return_inverse=True)':
            '            inv=_cluster_inverse(np.floor(points/cell).astype(np.int32))',
        '                if not np.isin(values, [0, 1]).all():':
            '                if not _is_binary(values):',
        '    key = hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()[:24]':
            '    sources.update(_optimizer_bindings)\n    key = hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()[:24]',
    }
    if target is not None:
        target=Path(target).resolve();assert target.is_relative_to(HERE/'results')
        changes["    target = UI/'cache'/key"]='    target = Path(__verification_target)'
    for before,after in changes.items():
        assert source.count(before)==1,'Frozen preparation changed: '+before
        source=source.replace(before,after)
    bindings={p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),HERE/'exact.py']}
    state={'__file__':str(BASE),'__name__':'exact_view_asset_backend',
        '_cluster_inverse':cluster_inverse,'_is_binary':is_binary,'_optimizer_bindings':bindings,
        '__verification_target':str(target) if target is not None else None}
    exec(compile(source,str(BASE),'exec'),state)
    state['_exact_derivation']=changes
    return state


def main():
    state=namespace()
    import backend_core_r6 as backend
    import backend_selected_r1 as accepted
    # All original import, algorithm, DFX transport and export actions remain
    # in the accepted dispatcher. Only its view-preparation function is extended.
    from modules.view_assets_r1.nav_reuse_r1.reuse_r2 import Reuse
    backend.prepare=Reuse(state).prepare
    return accepted.main()


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps(dict(event='error',text=str(error)),ensure_ascii=False),flush=True);sys.exit(1)
