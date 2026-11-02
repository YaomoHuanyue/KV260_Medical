"""Reuse complete validation only within one action and one unchanged snapshot.

No process-global monkeypatch or persistent certificate is used. The first
bundle read runs the sealed R9 verifier in full. Later reads check file and
directory identity before returning isolated metadata. A change aborts the
action, including a same-size write whose mtime was restored (POSIX ctime;
Windows additionally hashes contents because its ctime is creation time).
"""
from contextvars import ContextVar
from pathlib import Path
from time import perf_counter
import copy
import os
import stat

from modules.surface_route.bundle_r8 import sha as original_sha
from modules.surface_route.bundle_reader_r9 import verify_bundle as original_verify_bundle

_current = ContextVar('surface_verification_session_r15', default=None)


def _path(value):
    return Path(os.path.abspath(value))


def _identity(info):
    return info.st_dev, info.st_ino, info.st_mode


def _stamp(path):
    """Do not resolve away a changed symlink or parent replacement."""
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
        raise ValueError('Regular file/directory snapshot required: '+str(path))
    parents = []
    for parent in path.parents:
        ancestor = parent.lstat()
        if not stat.S_ISDIR(ancestor.st_mode) or stat.S_ISLNK(ancestor.st_mode):
            raise ValueError('Changed/unsafe snapshot parent: '+str(parent))
        parents.append((str(parent), _identity(ancestor)))
    digest = original_sha(path) if os.name == 'nt' and stat.S_ISREG(info.st_mode) else None
    return (_identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            getattr(info, 'st_nlink', None), tuple(parents), digest)


def _tree(folder):
    result = [(str(folder), _stamp(folder))]
    for path in sorted(folder.rglob('*')):
        result.append((str(path.relative_to(folder)), _stamp(path)))
    return tuple(result)


class VerificationSession:
    def __init__(self):
        self.files = {}
        self.bundles = {}
        self.counts = dict(full_bundle_validations=0, reused_bundle_validations=0,
                           full_file_hashes=0, reused_file_hashes=0)
        self.started = None
        self.token = None

    def __enter__(self):
        if self.token is not None or _current.get() is not None:
            raise RuntimeError('One non-nested verification session per action required')
        self.started = perf_counter()
        self.token = _current.set(self)
        return self

    def __exit__(self, *error):
        try:
            if error[0] is None:
                self.assert_unchanged()
        finally:
            _current.reset(self.token)
            self.token = None

    def assert_unchanged(self):
        for path, (stamp, _) in self.files.items():
            if _stamp(path) != stamp:
                raise ValueError('Validated file changed during action: '+str(path))
        for folder, (stamp, _) in self.bundles.items():
            if _tree(folder) != stamp:
                raise ValueError('Validated bundle changed during action: '+str(folder))

    def metrics(self):
        return dict(self.counts, action_scoped_only=True,
                    first_bundle_validation_is_complete_sealed_R9=True,
                    changed_validated_input_aborts_action=True,
                    Windows_rehashes_content_for_change_guard=os.name == 'nt',
                    elapsed_seconds=perf_counter()-self.started)

    def sha(self, value):
        path = _path(value)
        before = _stamp(path)
        if not path.is_file():
            raise ValueError('File hash requires a regular file')
        if path in self.files:
            old, result = self.files[path]
            if before != old:
                raise ValueError('Validated file changed during action: '+str(path))
            self.counts['reused_file_hashes'] += 1
            return result
        result = original_sha(path)
        if _stamp(path) != before:
            raise ValueError('File changed during initial hash: '+str(path))
        self.files[path] = before, result
        self.counts['full_file_hashes'] += 1
        return result

    def verify_bundle(self, value, expected_revision=None):
        folder = _path(value)
        before = _tree(folder)
        if folder in self.bundles:
            old, result = self.bundles[folder]
            if before != old:
                raise ValueError('Validated bundle changed during action: '+str(folder))
            if expected_revision is not None and result['revision'] != expected_revision:
                raise ValueError('Incomplete or mixed scene revision')
            self.counts['reused_bundle_validations'] += 1
            return copy.deepcopy(result)
        result = original_verify_bundle(folder, expected_revision)
        if _tree(folder) != before:
            raise ValueError('Bundle changed during initial validation: '+str(folder))
        self.bundles[folder] = before, copy.deepcopy(result)
        self.counts['full_bundle_validations'] += 1
        return result


def sha(value):
    session = _current.get()
    # Builders hash their private dot-prefixed staging files before atomic
    # rename. These outputs are deliberately never retained as input snapshots.
    if any(part.startswith('.') for part in _path(value).parts):
        return original_sha(value)
    return original_sha(value) if session is None else session.sha(value)


def verify_bundle(folder, expected_revision=None):
    session = _current.get()
    return (original_verify_bundle(folder, expected_revision) if session is None
            else session.verify_bundle(folder, expected_revision))
