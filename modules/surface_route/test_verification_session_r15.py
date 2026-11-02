"""Invalidation, isolation and fail-closed guards for scoped validation reuse."""
from pathlib import Path
from unittest.mock import patch
import argparse
import copy
import json
import os
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from modules.surface_route import verification_session_r15 as v
from modules.surface_route.bundle_r8 import sha,write_json


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='kv260-verification-r15-')
        self.root=Path(self.temp.name)
        self.folder=self.root/'bundle';self.folder.mkdir()
        self.file=self.folder/'payload';self.file.write_bytes(b'good')
        self.calls=0
        self.meta=dict(revision='revision-A',nested=dict(value=7))

    def tearDown(self):self.temp.cleanup()

    def validator(self,folder,expected_revision=None):
        self.calls+=1
        self.assertEqual(Path(folder),self.folder)
        if self.file.read_bytes()!=b'good':raise ValueError('Corrupt initial payload')
        if expected_revision is not None and expected_revision!=self.meta['revision']:
            raise ValueError('Wrong revision')
        return copy.deepcopy(self.meta)

    def test_first_full_then_isolated_reuse(self):
        with patch.object(v,'original_verify_bundle',self.validator),v.VerificationSession() as session:
            first=v.verify_bundle(self.folder);first['nested']['value']=99
            second=v.verify_bundle(self.folder);self.assertEqual(second['nested']['value'],7)
            second['nested']['value']=42
            self.assertEqual(v.verify_bundle(self.folder)['nested']['value'],7)
            self.assertEqual(self.calls,1)
            self.assertEqual(session.metrics()['reused_bundle_validations'],2)

    def test_expected_revision_checked_on_hit(self):
        with patch.object(v,'original_verify_bundle',self.validator),v.VerificationSession():
            v.verify_bundle(self.folder,'revision-A')
            with self.assertRaises(ValueError):v.verify_bundle(self.folder,'revision-B')

    def test_same_size_write_restored_mtime_aborts(self):
        with patch.object(v,'original_verify_bundle',self.validator):
            with self.assertRaises(ValueError),v.VerificationSession():
                v.verify_bundle(self.folder);before=self.file.stat()
                self.file.write_bytes(b'evil');os.utime(self.file,ns=(before.st_atime_ns,before.st_mtime_ns))
                v.verify_bundle(self.folder)

    def test_file_hash_same_size_write_restored_mtime_aborts(self):
        with self.assertRaises(ValueError),v.VerificationSession():
            v.sha(self.file);before=self.file.stat()
            self.file.write_bytes(b'evil');os.utime(self.file,ns=(before.st_atime_ns,before.st_mtime_ns))
            v.sha(self.file)

    def test_atomic_payload_replacement_aborts(self):
        with patch.object(v,'original_verify_bundle',self.validator):
            with self.assertRaises(ValueError),v.VerificationSession():
                v.verify_bundle(self.folder)
                replacement=self.root/'replacement';replacement.write_bytes(b'good')
                os.replace(replacement,self.file);v.verify_bundle(self.folder)

    def test_addition_aborts(self):
        with patch.object(v,'original_verify_bundle',self.validator):
            with self.assertRaises(ValueError),v.VerificationSession():
                v.verify_bundle(self.folder);(self.folder/'extra').write_bytes(b'new');v.verify_bundle(self.folder)

    def test_deletion_aborts(self):
        with patch.object(v,'original_verify_bundle',self.validator):
            with self.assertRaises((ValueError,FileNotFoundError)),v.VerificationSession():
                v.verify_bundle(self.folder);self.file.unlink();v.verify_bundle(self.folder)

    def test_replaced_parent_aborts(self):
        with patch.object(v,'original_verify_bundle',self.validator):
            with self.assertRaises(ValueError),v.VerificationSession():
                v.verify_bundle(self.folder);self.folder.rename(self.root/'old')
                self.folder.mkdir();self.file.write_bytes(b'good');v.verify_bundle(self.folder)

    def test_symlink_payload_aborts(self):
        if os.name=='nt':self.skipTest('Windows symlink creation may require administrator; ARM covers this guard')
        with patch.object(v,'original_verify_bundle',self.validator):
            with self.assertRaises(ValueError),v.VerificationSession():
                v.verify_bundle(self.folder);self.file.unlink();other=self.root/'other';other.write_bytes(b'good')
                self.file.symlink_to(other);v.verify_bundle(self.folder)

    def test_change_during_initial_full_validation_aborts(self):
        def moving(folder,revision=None):
            result=self.validator(folder,revision);self.file.write_bytes(b'evil');return result
        with patch.object(v,'original_verify_bundle',moving):
            with self.assertRaises(ValueError),v.VerificationSession():v.verify_bundle(self.folder)

    def test_change_during_initial_hash_aborts(self):
        original=v.original_sha
        def moving(path):
            result=original(path);self.file.write_bytes(b'evil');return result
        with patch.object(v,'original_sha',moving):
            with self.assertRaises(ValueError),v.VerificationSession():v.sha(self.file)

    def test_final_guard_without_subsequent_read(self):
        with self.assertRaises(ValueError),v.VerificationSession():
            v.sha(self.file);self.file.write_bytes(b'evil')

    def test_new_action_revalidates_and_rejects_corruption(self):
        with patch.object(v,'original_verify_bundle',self.validator):
            with v.VerificationSession():v.verify_bundle(self.folder)
            with v.VerificationSession():v.verify_bundle(self.folder)
            self.assertEqual(self.calls,2);self.file.write_bytes(b'evil')
            with self.assertRaises(ValueError),v.VerificationSession():v.verify_bundle(self.folder)

    def test_outside_action_delegates_without_cache(self):
        with patch.object(v,'original_verify_bundle',self.validator):
            v.verify_bundle(self.folder);v.verify_bundle(self.folder);self.assertEqual(self.calls,2)

    def test_nested_session_rejected(self):
        with v.VerificationSession():
            with self.assertRaises(RuntimeError),v.VerificationSession():pass

    def test_exception_resets_context(self):
        try:
            with v.VerificationSession():raise RuntimeError('simulation')
        except RuntimeError:pass
        with v.VerificationSession():self.assertEqual(v.sha(self.file),sha(self.file))

    def test_private_staging_hash_survives_rename(self):
        stage=self.root/'.private-stage';stage.mkdir();file=stage/'file';file.write_bytes(b'new')
        with v.VerificationSession():
            self.assertEqual(v.sha(file),sha(file));stage.rename(self.root/'published')

    def test_derivations_match_sealed_parent_functions(self):
        manifest=json.loads((ROOT/'modules/surface_route/derivations_r15.json').read_text())
        for entry in manifest['derivations']:
            self.assertEqual(sha(ROOT/entry['parent']),entry['parent_sha256'])
            self.assertEqual(sha(ROOT/entry['derived']),entry['derived_sha256'])
            if 'replacements' in entry:
                source=(ROOT/entry['parent']).read_text(encoding='utf-8')
                for item in entry['replacements']:source=source.replace(item['old'],item['new'])
                self.assertEqual(source,(ROOT/entry['derived']).read_text(encoding='utf-8'))
            else:
                source=(ROOT/entry['parent']).read_text(encoding='utf-8')
                function=source[source.index('def verify_prepared('):source.index('\n\ndef main():')]
                derived=(ROOT/entry['derived']).read_text(encoding='utf-8')
                self.assertIn(function,derived)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise ValueError('Fresh test evidence required')
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(GuardTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    proof=dict(status='passed' if result.wasSuccessful() else 'failed',tests_run=result.testsRun,
        skipped=[dict(test=str(t),reason=reason) for t,reason in result.skipped],
        failures=[str(t) for t,_ in result.failures],errors=[str(t) for t,_ in result.errors],
        platform='Windows' if os.name=='nt' else 'ARM',PL_access=False,
        source_sha256={n:sha(ROOT/n) for n in ('modules/surface_route/verification_session_r15.py',
            'modules/surface_route/test_verification_session_r15.py','modules/surface_route/derivations_r15.json')})
    write_json(args.output,proof)
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':main()
