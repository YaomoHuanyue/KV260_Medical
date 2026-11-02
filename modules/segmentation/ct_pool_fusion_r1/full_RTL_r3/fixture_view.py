"""Read immutable original193 plus additive294 without materializing a merged ZIP."""
from pathlib import Path
from contextlib import ExitStack
import hashlib
import json
import zipfile

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
ROOT = CORE.parents[2]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Fixtures:
    def __init__(self, original):
        self.original = Path(original)
        self.delta = HERE/'fixtures_delta_r7.zip'
        if not self.delta.is_file():
            self.delta = ROOT.parent/'closed_delta_fixture_source.zip'
        self.stack = ExitStack()

    def __enter__(self):
        try:
            old_proof = json.loads((CORE/'full_RTL_r1/fixtures_verified_r1.json').read_text())
            new_proof = json.loads((HERE/'fixtures_verified_r7.json').read_text())
            assert sha(self.original) == old_proof['archive_SHA256'] == new_proof['original_fixture_archive_SHA256']
            assert sha(self.delta) == new_proof['archive_SHA256']
            assert new_proof['cases'] == 487 and new_proof['original193_all6_blobs_each_case_exact_original1158_digests']
            self.old = self.stack.enter_context(zipfile.ZipFile(self.original))
            self.new = self.stack.enter_context(zipfile.ZipFile(self.delta))
            for archive in (self.old, self.new):
                assert len(archive.namelist()) == len(set(archive.namelist()))
            self.old_manifest = json.loads(self.old.read('outputs_manifest.json'))
            self.new_manifest = json.loads(self.new.read('outputs_manifest.json'))
            assert set(self.new.namelist()) == set(self.new_manifest)|{'outputs_manifest.json'}
            for name in set(self.old_manifest)&set(self.new_manifest):
                assert name == 'cases.json', name
            for name in self.new_manifest:
                if name != 'cases.json':
                    assert name.startswith('case') and 193 <= int(name[4:7]) < 487
            self.manifest = {**self.old_manifest, **self.new_manifest}
            self.metadata = self.new.read('cases.json')
            assert hashlib.sha256(self.metadata).hexdigest() == self.new_manifest['cases.json']
            old_cases = json.loads(self.old.read('cases.json'))['cases']
            cases = json.loads(self.metadata)['cases']
            assert cases[:193] == old_cases and len(cases) == 487
            assert [row['index'] for row in cases] == list(range(487))
            return self
        except BaseException:
            self.stack.close()
            raise

    def __exit__(self, *args):
        return self.stack.__exit__(*args)

    def read(self, name):
        if name == 'outputs_manifest.json':
            return json.dumps(self.manifest, sort_keys=True).encode()
        archive = self.new if name in self.new_manifest else self.old
        return archive.read(name)

    def open(self, name):
        assert name in self.manifest
        archive = self.new if name in self.new_manifest else self.old
        return archive.open(name)
