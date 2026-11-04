"""Exercise mixed-delivery checks without inventing release review receipts."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MixedModelDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.expected = self.root / 'release.json'
        self.bundle = {'schema': 'plebian-os.default-models-archive/v1',
                       'sha256': 'a' * 64, 'bytes': 100,
                       'url': 'https://example.invalid/bundle',
                       'assets': {'bundled': 'b' * 64}}
        self.expected.write_text(json.dumps(self.bundle))
        (self.root / 'DEFAULT-MODELS.json').write_text(json.dumps(self.bundle))
        self.carrier = {'models': {
            'bundled': {'artifact_id': 'bundled', 'manifest_digest': 'b' * 64,
                        'delivery': 'bundled-default-model'},
            'deferred': {'artifact_id': 'deferred', 'manifest_digest': 'c' * 64,
                         'delivery': 'first-use-upstream-download'}}}
        self.env = {f'm_{name}_delivery': entry['delivery']
                    for name, entry in self.carrier['models'].items()}

    def guard(self):
        (self.root / 'CARRIER.json').write_text(json.dumps(self.carrier))
        (self.root / 'CARRIER.env').write_text(''.join(f'{k}={v}\n' for k, v in self.env.items()))
        source = (ROOT / 'build/remaster-iso.sh').read_text()
        start = source.index('validate_model_delivery_inventory() {')
        end = source.index('\n}\n', start) + 3
        return subprocess.run(['bash', '-c', source[start:end] +
                               '\nvalidate_model_delivery_inventory "$1" "$2"',
                               'guard', str(self.root), str(self.expected)],
                              capture_output=True, text=True)

    def test_mixed_inventory_is_accepted(self):
        result = self.guard()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_relabelled_delivery_is_rejected_even_with_matching_projection(self):
        for name, mode in [('bundled', 'first-use-upstream-download'),
                           ('deferred', 'bundled-default-model')]:
            with self.subTest(model=name):
                original = self.carrier['models'][name]['delivery']
                self.carrier['models'][name]['delivery'] = mode
                self.env[f'm_{name}_delivery'] = mode
                result = self.guard()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('delivery differs', result.stderr)
                self.carrier['models'][name]['delivery'] = original
                self.env[f'm_{name}_delivery'] = original

    def test_changed_archive_or_inventory_is_rejected(self):
        for key, value in [('sha256', 'd' * 64), ('assets', {'deferred': 'c' * 64})]:
            with self.subTest(field=key):
                (self.root / 'DEFAULT-MODELS.json').write_text(json.dumps({**self.bundle, key: value}))
                result = self.guard()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('differs from the release inventory', result.stderr)

    def test_wrong_bundled_manifest_is_rejected(self):
        self.carrier['models']['bundled']['manifest_digest'] = 'e' * 64
        result = self.guard()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('bundled manifest digest differs', result.stderr)

    def test_shell_projection_cannot_disagree_with_delivery(self):
        self.env['m_bundled_delivery'] = 'first-use-upstream-download'
        self.assertNotEqual(self.guard().returncode, 0)

    def test_missing_bundle_record_is_rejected(self):
        (self.root / 'DEFAULT-MODELS.json').unlink()
        self.assertNotEqual(self.guard().returncode, 0)


class MandatoryDefaultModelAdmissionTests(unittest.TestCase):
    def admission(self, flag, release_mode='1', carrier_result=None):
        source = (ROOT / 'build/remaster-iso.sh').read_text()
        functions = source[source.index('is_hex_len() {'):
                           source.index('validate_waydroid_release_closure() {')]
        environment = {'PATH': '/usr/bin:/bin', 'HERE': str(ROOT),
                       'PLEBIAN_OS_VERSION': '0.2.3',
                       'PLEBIAN_OS_RELEASE_MODE': release_mode}
        if flag is not None:
            environment['PLEBIAN_OS_INSTALL_VOICE_MODEL'] = flag
        # Only delegation controls substitute a verdict. They do not create
        # or claim a real review receipt; refusal cases use the actual guard.
        if carrier_result is not None:
            functions += ('\nvalidate_voice_compliance_carrier() { '
                          'echo carrier-checked >&2; return '
                          + str(carrier_result) + '; }\n')
        return subprocess.run(['bash', '-c', 'set -eu\n' + functions +
                               '\nvalidate_default_model_release_closure'],
                              env=environment, capture_output=True, text=True)

    def test_missing_acceptance_refuses_every_voice_flag(self):
        for flag in ('0', '1', None):
            with self.subTest(flag=flag):
                result = self.admission(flag)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('mandatory default-model bundle', result.stderr)

    def test_every_voice_flag_delegates_to_the_carrier_verdict(self):
        for flag in ('0', '1', None):
            for verdict in (0, 1):
                with self.subTest(flag=flag, verdict=verdict):
                    result = self.admission(flag, carrier_result=verdict)
                    self.assertEqual(result.returncode, verdict, result.stderr)
                    self.assertEqual(result.stderr.count('carrier-checked'), 1)

    def test_nonrelease_development_does_not_claim_release_acceptance(self):
        result = self.admission('0', release_mode='0', carrier_result=1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('carrier-checked', result.stderr)

    def test_admission_precedes_actual_archive_verification_and_copy(self):
        source = (ROOT / 'build/remaster-iso.sh').read_text()
        admission = source.index('\nvalidate_default_model_release_closure\n')
        verify = source.index('python3 "$HERE/provision/install-default-models.py" --verify-only')
        copy = source.index('install -m 0644 "$DEFAULT_MODELS_BUNDLE"')
        self.assertLess(admission, verify)
        self.assertLess(verify, copy)


if __name__ == '__main__':
    unittest.main()
