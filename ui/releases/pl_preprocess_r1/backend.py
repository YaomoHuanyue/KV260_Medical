"""Keep all accepted UI actions, select qualified D6->C5 for segmentation."""
from pathlib import Path
import ast
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = ROOT/'ui/releases/feature_completion_r6/backend_core_r6.py'
sys.path.insert(0, str(ROOT))


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def install():
    inputs = json.loads((HERE/'inputs.json').read_text())
    for name, digest in inputs['files_SHA256'].items():
        path = ROOT/name
        assert path.resolve().is_relative_to(ROOT) and sha(path) == digest, name
    proofs = [json.loads((ROOT/inputs['integration_proof_'+host]).read_text())
              for host in ['Windows', 'ARM']]
    assert proofs[0] == proofs[1] and proofs[0]['actual_D6_C5_full_pipeline_passed']
    from modules.ct_preprocess.axis_hu_32_r2.host_r1.runtime import verify_release
    verify_release()  # Validates actual board qualification; never opens XRT.
    from modules.view_assets_r1.backend_optimized import namespace
    state = namespace()
    import backend_core_r6 as backend
    assert Path(backend.__file__).resolve() == BASE
    proof = json.loads((HERE/'derivation.json').read_text())['dispatcher']
    assert sha(BASE) == proof['parent_SHA256']
    text = BASE.read_text()
    node = next(n for n in ast.parse(text).body
                if isinstance(n, ast.FunctionDef) and n.name == proof['function'])
    function = ast.get_source_segment(text, node)
    for before, after in proof['literal_edits']:
        assert function.count(before) == 1
        function = function.replace(before, after)
    source = (HERE/'dispatch.py').read_text()
    assert function+'\n' == source and sha(HERE/'dispatch.py') == proof['output_SHA256']
    # Retain the accepted dispatcher's globals and __file__, including its
    # reconstruction/navigation helpers, stage locks, errors and stop handling.
    exec(compile(source, str(HERE/'dispatch.py'), 'exec'), backend.__dict__)
    from modules.view_assets_r1.nav_reuse_r1.reuse_r2 import Reuse
    backend.prepare = Reuse(state).prepare
    return backend


def main():
    install()
    import backend_selected_r1 as accepted
    return accepted.main()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps(dict(event='error', text=str(error)), ensure_ascii=False), flush=True)
        sys.exit(1)
