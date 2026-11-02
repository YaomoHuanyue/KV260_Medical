"""Independent import adapter; accepted backend and medical cores stay intact."""
from pathlib import Path
import argparse
import json
import os
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from modules.image_import.import_external import import_bundle, validate_bundle, read, sha, header, same_geometry, inside
import backend_core_r6 as backend


def validate_external_source(ct, folder):
    folder = Path(folder).resolve()
    if (folder/'external_import.json').exists():
        return validate_bundle(ct, folder)
    report_path = folder/'segmentation/report.json'
    if not report_path.exists():
        return None
    report = read(report_path)
    if report.get('schema') != 'kv260.external.segmentation.v1':
        return None
    # Derived recon/navigation results copy the whole segmentation folder.
    # They keep all masks/probabilities locally and do not depend on older runs.
    if report.get('input_sha256') != sha(ct):
        raise ValueError('Imported segmentation belongs to another CT')
    _, g = header(ct)
    if not same_geometry(report['geometry'], g):
        raise ValueError('Imported segmentation CT geometry changed')
    if not {f'segmentation/{n}_mask.nii.gz' for n in ('lung','airway','nodule')}.issubset(report['files']):
        raise ValueError('Missing imported masks')
    for name, digest in report['files'].items():
        path = inside(folder, name)
        if sha(path) != digest or not same_geometry(g, header(path)[1]):
            raise ValueError('Copied external image changed: '+name)
    return report


def main():
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('action')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--result', type=Path)
    parser.add_argument('--manifest', type=Path)
    args, _ = parser.parse_known_args()
    if args.action == 'import-external':
        if args.input is None or args.manifest is None:
            raise ValueError('External import requires the current CT and producer manifest')
        if hasattr(os, 'nice'):
            os.nice(10)
        destination=backend.RUNS/('external_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
        report=import_bundle(args.input, args.manifest, destination)
        backend.emit('external_imported', result=str(destination), input_sha256=report['input_sha256'],
                     text='外部掩膜和概率图已校验；未运行分割推理、重建或导航', seconds=report['import_seconds'])
        return
    if args.input and args.action in ('prepare', 'run', 'export'):
        result=args.result
        if args.action == 'prepare' and result is None:
            _, rows=backend.catalogue(args.input)
            if rows:
                result=Path(rows[0]['path'])
        if result is not None:
            validate_external_source(args.input, result)
    # All existing stages and cooperative PL handoff keep their original code.
    backend.main()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        backend.emit('error', text=str(error))
        sys.exit(1)
