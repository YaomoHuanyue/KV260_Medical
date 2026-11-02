"""Default whole PL comparison; native surface actions use the separate qualified adapter."""
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def install():
    inputs=json.loads((HERE/'inputs.json').read_text())
    for n,h in inputs['source_SHA256'].items():
        p=(ROOT/n).resolve()
        if not p.is_relative_to(ROOT) or sha(p)!=h:raise RuntimeError('Changed PL-default input: '+n)
    from ui.releases.streaming_functional_r2.backend import install as parent
    backend=parent();source=(ROOT/inputs['dispatcher']).read_text()
    before="str(Path(__file__).parent/'navigation_task_r6.py')"
    after="str(ROOT/'modules/navigation_comparison/current_release_r1/task.py')"
    if source.count(before)!=1:raise RuntimeError('Changed candidate navigation dispatch')
    source=source.replace(before,after)
    if source.replace(after,before)!=(ROOT/inputs['dispatcher']).read_text():raise RuntimeError('Dispatcher reverse mismatch')
    exec(compile(source,str(HERE/'derived_dispatch.py'),'exec'),backend.__dict__)
    return backend
def main():
    install()
    import backend_selected_r1 as accepted
    return accepted.main()
if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps(dict(event='error',text=str(error)),ensure_ascii=False),flush=True);sys.exit(1)
