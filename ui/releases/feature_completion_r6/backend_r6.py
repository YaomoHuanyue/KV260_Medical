"""Independent partial-import UI integration; formal algorithms stay intact."""
from pathlib import Path
import argparse, os, sys, time, uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'ui'))
sys.path.insert(0, str(ROOT))
import backend_core_r6 as backend
import complete_import_r6 as complete_import
from modules.image_import.partial_r1 import importer
from modules.image_import.partial_r1.contracts import validate_source


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('action')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--result', type=Path)
    parser.add_argument('--manifest', type=Path)
    args, _ = parser.parse_known_args()
    if args.action == 'import-external':
        if args.input is None or args.manifest is None:
            raise ValueError('External import requires CT and producer manifest')
        if hasattr(os, 'nice'):
            os.nice(10)
        spec = importer.read(args.manifest)
        if spec.get('schema') == importer.SCHEMA:
            destination = backend.RUNS / ('external_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
            report = importer.import_bundle(args.input, args.manifest, destination)
            backend.emit('external_imported', result=str(destination), input_sha256=report['input_sha256'],
                         available_structures=report['declared_structures'], seconds=report['import_seconds'],
                         text='已校验提供的结构；缺失结构未生成替代掩膜')
            return
        complete_import.backend = backend
        return complete_import.main()
    if args.action in ('prepare', 'run', 'export') and args.input:
        result = args.result
        if args.action == 'prepare' and result is None:
            _, rows = backend.catalogue(args.input)
            if rows:
                result = Path(rows[0]['path'])
        if result:
            partial = validate_source(args.input, result)
            if partial is None:
                complete_import.validate_external_source(args.input, result)
    if args.action in ('dicom-series', 'import-dicom', 'export'):
        import complete_features_r6 as module
        module.accepted.backend = backend
        return module.main()
    return backend.main()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        backend.emit('error', text=str(error))
        sys.exit(1)
