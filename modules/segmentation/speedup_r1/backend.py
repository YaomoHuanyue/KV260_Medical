"""加速候选调度器：在 reader_burst 完整混合调度之上，只把气道清理命令换成外包框版本（结果逐体素一致）。

原 mixed_r30 准入、reader_burst 证书、B7/源码检查全部照常执行；不改分割、重建、导航命令，不改固件。
与 reader_burst/backend.py 的 install/main 一一对应，差别仅为 CLEANUP → SPEEDUP_CLEANUP 一处可逆字面替换。"""
from pathlib import Path
import argparse
import ast
import hashlib
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from modules.segmentation.reader_burst import backend as reader  # noqa: E402

SPEEDUP_CLEANUP = "str(_speedup_here/'cleanup_bbox.py'),'--admission',str(_mixed_admission),'--admission-sha256',_mixed_admission_sha"
RECON = "str(ROOT/'modules/reconstruction/streaming_functional_r1/run_reconstruction.py'),'--ct',str(input_path)"
SPEEDUP_RECON = "str(_speedup_here/'recon_tmpfs.py'),'--ct',str(input_path)"


def derive(source):
    edits = [[reader.CLEANUP, SPEEDUP_CLEANUP], [RECON, SPEEDUP_RECON]]
    selected = source
    for before, after in edits:
        if selected.count(before) != 1 or after in selected:
            raise ValueError('Changed original command: ' + before[:40])
        selected = selected.replace(before, after)
    restored = selected
    for before, after in reversed(edits):
        restored = restored.replace(after, before)
    if restored != source:
        raise ValueError('Speedup edits are not reversible')
    ast.parse(selected)
    return selected, dict(literal_edits=edits, reverse_exact=True,
                          parent_source_SHA256=hashlib.sha256(source.encode()).hexdigest(),
                          selected_source_SHA256=hashlib.sha256(selected.encode()).hexdigest())


def install(admission, digest, run_parent, repeats):
    started = time.perf_counter()
    certificate = reader._load_certificate(admission, digest)
    if (Path(certificate.root).resolve(strict=True) != ROOT.resolve(strict=True)
            or Path(certificate.path).resolve(strict=True) != Path(admission).resolve(strict=True)
            or certificate.digest != digest):
        raise ValueError('Certificate root/path/digest binding differs')
    legacy = certificate.record.get('legacy_hybrid')
    if legacy != dict(path=reader.LEGACY_PATH, SHA256=reader.LEGACY_SHA256):
        raise ValueError('Exact original mixed_r30 admission required for cleanup')
    legacy_path = (ROOT / reader.LEGACY_PATH).resolve(strict=True)
    if not legacy_path.is_relative_to(ROOT.resolve(strict=True)) or reader.sha(legacy_path) != reader.LEGACY_SHA256:
        raise ValueError('Original mixed_r30 admission changed')
    mixed = reader._mixed_backend()
    backend = mixed.install(legacy_path, reader.LEGACY_SHA256, run_parent, repeats)
    source, record = reader.derive(reader._dispatch_source(mixed))
    source, speedup = derive(source)
    backend.__dict__.update(
        _reader_here=reader.HERE, _reader_admission=Path(certificate.path),
        _reader_admission_sha=certificate.digest, _speedup_here=HERE)
    exec(compile(source, str(HERE / 'backend.py') + ':speedup_complete_dispatch', 'exec'), backend.__dict__)
    record.update(admission_SHA256=certificate.digest, legacy_admission_SHA256=reader.LEGACY_SHA256,
                  original_mixed_install_executed=True, production_promoted=False,
                  speedup_cleanup=speedup, install_seconds=time.perf_counter() - started)
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
        import json
        print(json.dumps(dict(event='error', text=str(error)), ensure_ascii=False), flush=True)
        raise
