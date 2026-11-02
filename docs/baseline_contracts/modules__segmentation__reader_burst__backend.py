"""Explicit reader-burst selection in the original complete hybrid dispatcher.

The original mixed admission/install remains mandatory. Only the segmentation
command receives the new certificate; cleanup retains its original admission.
"""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
LEGACY_PATH = 'modules/segmentation/mixed_r30/candidate_r2.json'
LEGACY_SHA256 = '5c0cb67ea0254ce382e80049cdda402b52ff63725d1c0b8b03928c199caa28fc'
SEGMENTATION = "str(_mixed_here/'segmentation.py'),'--admission',str(_mixed_admission),'--admission-sha256',_mixed_admission_sha"
SELECTED = "str(_reader_here/'segmentation.py'),'--admission',str(_reader_admission),'--admission-sha256',_reader_admission_sha"
CLEANUP = "str(_mixed_here/'cleanup.py'),'--admission',str(_mixed_admission),'--admission-sha256',_mixed_admission_sha"


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _load_certificate(path, digest):
    from modules.segmentation.reader_burst.admission import load
    return load(path, digest)


def _mixed_backend():
    from modules.segmentation.mixed_r30 import backend_r2
    return backend_r2


def _dispatch_source(mixed):
    from modules.segmentation.standalone_B7_r1 import backend as parent
    original, _ = parent.derive(parent.parent_module().derived_dispatch()[0])
    return mixed.derive(original)[0]


def derive(source):
    """One exact reversible command edit; preserve the cleanup command verbatim."""
    if source.count(SEGMENTATION) != 1 or source.count(CLEANUP) != 1 or SELECTED in source:
        raise ValueError('Changed original hybrid segmentation/cleanup boundary')
    selected = source.replace(SEGMENTATION, SELECTED)
    if selected.count(SELECTED) != 1 or selected.count(CLEANUP) != 1:
        raise ValueError('Ambiguous reader-burst command selection')
    if selected.replace(SELECTED, SEGMENTATION) != source:
        raise ValueError('Reader-burst dispatcher edit is not reversible')
    ast.parse(selected)
    return selected, dict(
        literal_edits=[[SEGMENTATION, SELECTED]], counts=[1], reverse_exact=True,
        parent_source_SHA256=hashlib.sha256(source.encode()).hexdigest(),
        selected_source_SHA256=hashlib.sha256(selected.encode()).hexdigest(),
        original_cleanup_command_preserved=True)


def install(admission, digest, run_parent, repeats):
    started = time.perf_counter()
    certificate = _load_certificate(admission, digest)
    if (Path(certificate.root).resolve(strict=True) != ROOT.resolve(strict=True)
            or Path(certificate.path).resolve(strict=True) != Path(admission).resolve(strict=True)
            or certificate.digest != digest):
        raise ValueError('Certificate root/path/digest binding differs')
    legacy = certificate.record.get('legacy_hybrid')
    if legacy != dict(path=LEGACY_PATH, SHA256=LEGACY_SHA256):
        raise ValueError('Exact original mixed_r30 admission required for cleanup')
    legacy_path = (ROOT / LEGACY_PATH).resolve(strict=True)
    if not legacy_path.is_relative_to(ROOT.resolve(strict=True)) or sha(legacy_path) != LEGACY_SHA256:
        raise ValueError('Original mixed_r30 admission changed')
    verified = time.perf_counter()
    mixed = _mixed_backend()
    # This performs the original binding/B7/source checks. Do not skip or replace
    # them with the new certificate or an older timing/qualification receipt.
    backend = mixed.install(legacy_path, LEGACY_SHA256, run_parent, repeats)
    installed = time.perf_counter()
    source, record = derive(_dispatch_source(mixed))
    backend.__dict__.update(
        _reader_here=HERE, _reader_admission=Path(certificate.path),
        _reader_admission_sha=certificate.digest)
    exec(compile(source, str(HERE / 'backend.py') + ':reader_burst_complete_dispatch', 'exec'), backend.__dict__)
    record.update(
        admission_SHA256=certificate.digest, legacy_admission_SHA256=LEGACY_SHA256,
        original_mixed_install_executed=True, production_promoted=False,
        certificate_seconds=verified-started, original_install_seconds=installed-verified,
        source_derivation_and_install_seconds=time.perf_counter()-installed)
    backend.reader_burst_dispatch_derivation = record
    return backend


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--admission', type=Path, required=True)
    parser.add_argument('--admission-sha256', required=True)
    parser.add_argument('--run-parent', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=1)
    args, rest = parser.parse_known_args()
    backend = install(args.admission, args.admission_sha256, args.run_parent, args.repeats)
    head = argparse.ArgumentParser(add_help=False)
    head.add_argument('--mode')
    known, _ = head.parse_known_args(rest)
    if known.mode == 'segmentation':
        command = argparse.ArgumentParser()
        command.add_argument('action', choices=['run'])
        command.add_argument('--mode')
        command.add_argument('--input', type=Path, required=True)
        command.add_argument('--stop-file', type=Path)
        value = command.parse_args(rest)
        return backend.run(value.input, 'segmentation', None, 0, 1., .2, value.stop_file, 0.)
    sys.argv = [sys.argv[0], *rest]
    import backend_selected_r1 as accepted
    return accepted.main()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps(dict(event='error', text=str(error)), ensure_ascii=False), flush=True)
        raise
