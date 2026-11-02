"""Promote duplicate payloads by content hash, including every backlink."""
from pathlib import Path
import hashlib


def validate(selected, metadata, original):
    aliases = metadata['logical_aliases']
    assert not set(selected) & set(aliases), 'Payload is both retained and aliased'
    for name in selected:
        assert name in original, name
    for name, alias in aliases.items():
        assert name in original and alias['SHA256'] == original[name], ('Alias SHA differs from original', name)
        kind = alias['kind']
        if kind == 'retained_member':
            target = alias['member']
            assert target in selected, ('Dangling retained member', name, target)
            assert original[target] == alias['SHA256'], ('Retained backlink SHA mismatch', name)
        else:
            assert kind in ('canonical_file', 'canonical_archive'), ('Unknown alias kind', kind)
    return True


def promote_files(selected, metadata, original, files_by_SHA256, root):
    selected = set(selected)
    aliases = metadata['logical_aliases']
    logical_before = set(selected) | set(aliases)
    canonical = {}
    root = Path(root).resolve()
    for expected, raw_path in files_by_SHA256.items():
        path = Path(raw_path).resolve()
        assert path.is_relative_to(root) and path.is_file(), 'Canonical file must remain in workspace'
        with path.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected, 'Changed canonical file'
        canonical[expected] = dict(kind='canonical_file', path=path.relative_to(root).as_posix(), SHA256=expected)
    promoted = []
    for name in sorted(logical_before):
        expected = original[name]
        if expected in canonical:
            selected.discard(name)
            aliases[name] = dict(canonical[expected])
            promoted.append(name)
    assert set(selected) | set(aliases) == logical_before, 'A required logical input was lost'
    validate(selected, metadata, original)
    metadata['canonical_file_promotions_preserve_all_logical_bindings'] = promoted
    return selected
