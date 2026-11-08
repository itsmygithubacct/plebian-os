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
        # The release this tree builds. Its Kilix installs the pinned Voice
        # and adds whisper-medium-en to the staged library with
        # scripts/patch-whisper-medium-model.py, so the producer is that
        # patched library, not the bare Voice commit.
        version = (ROOT/'VERSION').read_text().strip()
        pins = contract._manifest(ROOT/f'releases/{version}.env')
        ref = pins['KILIX_VOICE_REF']
        repo = contract.repo_holding(contract._repo_candidates(
            'PLEBIAN_OS_KILIX_VOICE_REPO', ('kilix-apps', 'kilix-voice'), ('kilix-voice',)), ref)
        self.assertIsNotNone(repo, 'set PLEBIAN_OS_KILIX_VOICE_REPO to the pinned Voice repository')
        kilix = contract.repo_holding(contract._repo_candidates(
            'PLEBIAN_OS_KILIX_REPO', ('kilix',)), pins['KILIX_REF'])
        self.assertIsNotNone(kilix, 'set PLEBIAN_OS_KILIX_REPO to the pinned Kilix repository')
        installer = subprocess.run(['git', '-C', str(kilix), 'show',
                                    pins['KILIX_REF'] + ':scripts/install-kilix-voice.sh'],
                                   capture_output=True, text=True, check=True).stdout
        self.assertIn('patch-whisper-medium-model.py', installer)
        patcher = subprocess.run(['git', '-C', str(kilix), 'show',
                                  pins['KILIX_REF'] + ':scripts/patch-whisper-medium-model.py'],
                                 capture_output=True, check=True).stdout
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
            stt = [sys.executable, str(tree/'kilix-stt'), '--models', '--json']
            unpatched = subprocess.run(stt, env=env, capture_output=True, text=True,
                                       check=True).stdout
            (root/'patch.py').write_bytes(patcher)
            subprocess.run([sys.executable, str(root/'patch.py'), str(tree)], env=env,
                           capture_output=True, check=True)
            produced = subprocess.run(stt, env=env, capture_output=True, text=True,
                                      check=True).stdout
            document = json.loads(produced)
            self.assertIn('whisper-medium-en', [row['id'] for row in document['models']])
            self.assertNotIn('whisper-medium-en', unpatched)
            whistle = next(row for row in document['models'] if row['id'] == 'whistle')
            self.assertFalse(whistle['installed'])
            self.assertNotEqual(document['default_model'], 'whistle')
            for command in consumers:
                good = subprocess.run(command, input=produced, env=env, capture_output=True, text=True)
                self.assertEqual(good.returncode, 0, good.stderr)
                # Without the patch the advertised whisper-medium-en is missing.
                bare = subprocess.run(command, input=unpatched, env=env, capture_output=True, text=True)
                self.assertNotEqual(bare.returncode, 0)
            whistle['engine'] = 'whisper'
            for command in consumers:
                bad = subprocess.run(command, input=json.dumps(document), env=env,
                                     capture_output=True, text=True)
                self.assertNotEqual(bad.returncode, 0)
                self.assertIn('entries differ', bad.stderr)
