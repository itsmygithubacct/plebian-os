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


if __name__ == '__main__':
    unittest.main()
