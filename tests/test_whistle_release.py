"""Optional Whistle weights participate in the no-download image census."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WhistleImageCensusTests(unittest.TestCase):
    def test_whistle_weights_are_detected_in_both_model_stores(self):
        source = (ROOT/'provision/plebian-os-provision.sh').read_text()
        start = source.index('voice_dictation_asset_paths() {')
        function = source[start:source.index('\n}\n', start) + 3]
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
                   'KILIX_DATA_HOME': str(data)}
            def census():
                return subprocess.run(['bash', '-c', 'set -eu\n' + function +
                                       '\nvoice_dictation_asset_paths'], env=env,
                                      capture_output=True, text=True, check=True).stdout.splitlines()
            self.assertEqual(census(), [])
            for relative in ('desktop-apps/assets/whistle', 'voice/models/whistle'):
                model = data/relative
                model.mkdir(parents=True)
                (model/'whistle.cact').write_bytes(b'weight fixture')
                self.assertIn(str(model), census())
