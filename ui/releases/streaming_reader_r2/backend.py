"""Keep the complete R3 medical backend; use its corrected report adapter."""
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
        if not p.is_relative_to(ROOT) or not p.is_file() or sha(p)!=h:raise RuntimeError('Changed report-corrected native backend: '+n)
    from ui.releases.streaming_reader_r1.backend import install as parent
    backend=parent()
    original=json.loads((ROOT/'ui/releases/streaming_reader_r1/inputs.json').read_text())
    source=(ROOT/original['dispatcher']).read_text()
    for a,b in original['dispatcher_literal_edits']:
        if source.count(a)!=1:raise RuntimeError('Changed complete R3 dispatch')
        source=source.replace(a,b)
    a="str(ROOT/'modules/segmentation/axis_tensor_reader_r3/streaming_r1/entry.py')"
    b="str(ROOT/'modules/segmentation/axis_tensor_reader_r3/reporting_r2/entry.py')"
    if source.count(a)!=1:raise RuntimeError('Changed R3 stage route')
    source=source.replace(a,b)
    if hashlib.sha256(source.encode()).hexdigest()!=inputs['dispatcher_SHA256']:raise RuntimeError('Unqualified report-corrected dispatch')
    exec(compile(source,str(HERE/'backend.py')+':complete_report_corrected_dispatch','exec'),backend.__dict__)
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
