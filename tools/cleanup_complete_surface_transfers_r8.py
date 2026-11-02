"""Remove explicit SHA-bound staging ZIPs after every payload is preserved."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SHA = lambda b: hashlib.sha256(b).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--label', choices=['Windows', 'ARM'], required=True)
    args = parser.parse_args()
    plan = args.plan.resolve()
    assert plan.parent == ROOT/'tools' and SHA(plan.read_bytes()) == args.sha256
    receipt = ROOT/f'results/complete_surface_transfer_cleanup_{args.label}_r8.json'
    assert not receipt.exists()
    records, targets = [], []
    for relative, digest in json.loads(plan.read_text())['archives_sha256'].items():
        rel = PurePosixPath(relative)
        assert not rel.is_absolute() and '..' not in rel.parts and ':' not in relative
        named = ROOT/relative
        assert not named.is_symlink()
        archive = named.resolve()
        assert archive.parent == ROOT/'tools' and archive.suffix == '.zip'
        assert archive.is_file() and SHA(archive.read_bytes()) == digest
        with zipfile.ZipFile(archive) as z:
            names = z.namelist()
            assert len(names) == len(set(names))
            if 'upload_manifest.json' in names:
                manifest_name = 'upload_manifest.json'
                expected = json.loads(z.read(manifest_name))
            else:
                manifest_name = 'progress_manifest.json'
                expected = {n:v['new_sha256'] for n,v in json.loads(z.read(manifest_name)).items()}
            assert set(names) == set(expected)|{manifest_name}
            for n, h in expected.items():
                member = PurePosixPath(n)
                assert not member.is_absolute() and '..' not in member.parts and ':' not in n
                target = (ROOT/n).resolve()
                assert target.is_relative_to(ROOT) and target.is_file()
                assert SHA(z.read(n)) == h and SHA(target.read_bytes()) == h, n
        records.append(dict(path=relative, sha256=digest, bytes=archive.stat().st_size,
                            all_payloads_preserved_with_exact_SHA=True))
        targets.append(archive)
    # All paths, hashes and preserved payloads pass before any deletion.
    for target in targets:
        target.unlink()
    for target, record in zip(targets, records):
        assert not target.exists()
        record['removed'] = True
    record = dict(status='explicit_complete_scene_staging_archives_removed_all_payloads_preserved',
        label=args.label, files=records, bytes_removed=sum(r['bytes'] for r in records),
        plan_sha256=args.sha256, source_sha256=SHA(Path(__file__).read_bytes()),
        recursive_delete=False, project_sources_or_results_removed=False)
    receipt.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(record['status'], len(records), 'archives', flush=True)


if __name__ == '__main__':
    main()
