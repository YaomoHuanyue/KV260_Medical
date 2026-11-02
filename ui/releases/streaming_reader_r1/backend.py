"""Native backend with qualified R3 D6/C5 and the existing PL medical stages."""
from pathlib import Path
import ast,hashlib,inspect,json,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def install():
    inputs=json.loads((HERE/'inputs.json').read_text())
    for n,h in inputs['source_SHA256'].items():
        p=(ROOT/n).resolve()
        if not p.is_relative_to(ROOT) or not p.is_file() or sha(p)!=h:raise RuntimeError('Changed R3 native-backend input: '+n)
    from ui.releases.streaming_functional_r1 import backend as base
    original=inspect.getsource(base.install)
    before='from modules.segmentation.streaming_stage_r1.entry import recover_pending'
    after='from modules.segmentation.axis_tensor_reader_r3.streaming_r1.entry import recover_pending'
    if original.count(before)!=1:raise RuntimeError('Changed complete parent backend')
    source=original.replace(before,after)
    if source.replace(after,before)!=original:raise RuntimeError('R3 backend reverse mismatch')
    ast.parse(source)
    exec(compile(source,str(HERE/'backend.py')+':qualified_stage_recovery','exec'),base.__dict__)
    from ui.releases.streaming_functional_r5.backend import install as parent
    backend=parent()
    source=(ROOT/inputs['dispatcher']).read_text()
    for before,after in inputs['dispatcher_literal_edits']:
        if source.count(before)!=1:raise RuntimeError('Changed complete native dispatcher')
        source=source.replace(before,after)
    if hashlib.sha256(source.encode()).hexdigest()!=inputs['dispatcher_output_SHA256']:
        raise RuntimeError('Unqualified R3 dispatcher derivation')
    exec(compile(source,str(HERE/'backend.py')+':complete_native_dispatch','exec'),backend.__dict__)
    backend.CANDIDATE_RUNS=HERE/'runs'
    return backend

def main():
    install()
    import backend_selected_r1 as accepted
    return accepted.main()

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps(dict(event='error',text=str(error)),ensure_ascii=False),flush=True);sys.exit(1)
