"""Both release consumers must accept the actual pinned Voice producer."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

import test_voice_release_contract as contract

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'build'))
import build_vm_image as vm


class WhistleReleaseCatalogTests(unittest.TestCase):
    def test_pinned_voice_catalog_passes_provision_and_vm_acceptance(self):
        pins = contract._manifest(ROOT/'releases/0.2.2.env')
        ref = pins['KILIX_VOICE_REF']
        repo = contract.repo_holding(contract._repo_candidates(
            'PLEBIAN_OS_KILIX_VOICE_REPO', ('kilix-apps', 'kilix-voice'), ('kilix-voice',)), ref)
        self.assertIsNotNone(repo, 'set PLEBIAN_OS_KILIX_VOICE_REPO to the pinned Voice repository')
        archive = subprocess.run(['git', '-C', str(repo), '--no-replace-objects',
                                  'archive', '--format=tar', ref], capture_output=True, check=True).stdout
        source = (ROOT/'provision/plebian-os-provision.sh').read_text()
        start = source.index('validate_voice_model_catalog() {')
        function = source[start:source.index('\n}\n', start) + 3]
        consumers = ([sys.executable, '-c', vm._voice_model_catalog_validation_script()],
                     ['bash', '-c', function + '\nvalidate_voice_model_catalog'])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tree = root/'voice'
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                tar.extractall(tree, filter='data')
            env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
                   'GPU_TERMINAL_HOME': str(root/'g'), 'KILIX_DATA_HOME': str(root/'data'),
                   'KILIX_CONFIG_HOME': str(root/'config'), 'KILIX_STATE_DIRECTORY': str(root/'state'),
                   'PYTHONDONTWRITEBYTECODE': '1'}
            produced = subprocess.run([sys.executable, str(tree/'kilix-stt'), '--models', '--json'],
                                      env=env, capture_output=True, text=True, check=True).stdout
            document = json.loads(produced)
            whistle = next(row for row in document['models'] if row['id'] == 'whistle')
            self.assertFalse(whistle['installed'])
            self.assertNotEqual(document['default_model'], 'whistle')
            for command in consumers:
                good = subprocess.run(command, input=produced, env=env, capture_output=True, text=True)
                self.assertEqual(good.returncode, 0, good.stderr)
            whistle['engine'] = 'whisper'
            for command in consumers:
                bad = subprocess.run(command, input=json.dumps(document), env=env,
                                     capture_output=True, text=True)
                self.assertNotEqual(bad.returncode, 0)
                self.assertIn('entries differ', bad.stderr)
