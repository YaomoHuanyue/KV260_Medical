"""Current complete medical dispatch with explicitly qualified positive-label contracts."""
from pathlib import Path
import ast,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
def install_contracts():
    here=Path(__file__).resolve().parent
    proof=json.loads((here/'policy_qualification.json').read_bytes())
    if not proof.get('actual_ARM_policy_and_contracts_passed'):
        raise ValueError('Complete positive-label policy and derived-result contracts are not qualified')
    for relative,digest in proof['source_SHA256'].items():
        path=(ROOT/relative).resolve(strict=True)
        if not path.is_relative_to(ROOT):raise ValueError('Import contract source escapes this project')
        with path.open('rb')as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=digest:raise ValueError('Changed qualified positive-label source: '+relative)
    from modules.image_import.partial_r1 import contracts as accepted
    from modules.image_import.positive_labels_r1 import contracts as candidate
    for name in ('validate_source','validate_selected_masks','require_navigation'):
        setattr(accepted,name,getattr(candidate,name))
def derive_dispatch():
    """Keep R3 admission and drain logic; bind contracts in each partial child."""
    parent=json.loads((ROOT/'ui/releases/streaming_reader_r1/inputs.json').read_text())
    current=json.loads((ROOT/'ui/releases/streaming_reader_r2/inputs.json').read_text())
    source=(ROOT/parent['dispatcher']).read_text()
    for before,after in parent['dispatcher_literal_edits']:
        if source.count(before)!=1:raise ValueError('Changed parent dispatcher')
        source=source.replace(before,after)
    before="str(ROOT/'modules/segmentation/axis_tensor_reader_r3/streaming_r1/entry.py')"
    after="str(ROOT/'modules/segmentation/axis_tensor_reader_r3/reporting_r2/entry.py')"
    if source.count(before)!=1:raise ValueError('Changed reporting dispatcher')
    source=source.replace(before,after)
    if hashlib.sha256(source.encode()).hexdigest()!=current['dispatcher_SHA256']:
        raise ValueError('Unqualified parent dispatcher')
    before='                argv=[sys.executable,str(MEDICAL/command[stage][0]),*command[stage][1:]]'
    after=before+"\n                if partial:argv=[sys.executable,str(ROOT/'modules/image_import/positive_labels_r1/stage.py'),'--stage',str(MEDICAL/command[stage][0]),*command[stage][1:]]"
    if source.count(before)!=1:raise ValueError('Changed partial-stage process boundary')
    candidate=source.replace(before,after)
    if candidate.replace(after,before)!=source:raise ValueError('Dispatch inverse mismatch')
    ast.parse(candidate)
    return candidate,dict(parent_SHA256=hashlib.sha256(source.encode()).hexdigest(),
        candidate_SHA256=hashlib.sha256(candidate.encode()).hexdigest(),literal_edit=[before,after],
        inverse_exact=True,job_lock_and_pass_fds_and_normal_DFX_drain_unchanged=True)

def install_backend():
    install_contracts()
    from ui.releases.streaming_reader_r2.backend import install
    backend=install();source,derivation=derive_dispatch()
    exec(compile(source,str(Path(__file__))+':qualified_positive_partial_dispatch','exec'),backend.__dict__)
    return backend

def main():
    install_backend()
    import backend_selected_r1 as accepted
    return accepted.main()
if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps(dict(event='error',text=str(error)),ensure_ascii=False),flush=True);raise SystemExit(1)
