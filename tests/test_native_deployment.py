"""Native helper file population, actual private staging and rerooted media copy.

No privileged deployment, dpkg, ldconfig or native ELF is executed here.
The staging test supplies only systemd-analyze's installed-service existence
precondition; actual file copies, shell/Python validation and byte checks run.
The media-copy test substitutes a private target and an explicit chown observer;
it does not claim installed root ownership or a real installer run.
"""
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPDATE = ROOT / 'provision/plebian-os-update.sh'
MODULES = ('native_package.py', 'native_state.py', 'native_process.py', 'native_runtime.py')
NATIVE = ('plebian-os-native-runtime', *MODULES)
SOURCES = {
    'plebian-os-provision': 'provision/plebian-os-provision.sh',
    'plebian-os-install-deps': 'provision/install-deps.sh',
    'plebian-os-passwd': 'provision/plebian-os-passwd',
    'plebian-os-update': 'provision/plebian-os-update.sh',
    'plebian-os-firstboot.service': 'provision/plebian-os-firstboot.service',
    'plebian-os-firstboot-attempt': 'provision/plebian-os-firstboot-attempt',
    'VERSION': 'VERSION',
    'desktop-wallpaper.png': 'assets/desktop/plebian-os.png',
    'ATTRIBUTION.md': 'assets/installer/ATTRIBUTION.md',
    'COPYING.GPL-2': 'assets/COPYING.GPL-2',
    'lightdm-gtk-greeter.conf': 'provision/lightdm-gtk-greeter.conf',
    'plebian-os-select-closure': 'provision/plebian-os-select-closure.sh',
    'plebian-os-install-ollama-converter': 'provision/plebian-os-install-ollama-converter',
    'plebian-os-install-kilix-vulkan-tts': 'provision/plebian-os-install-kilix-vulkan-tts',
    'plebian-os-install-kilix-ollama-runtime': 'provision/plebian-os-install-kilix-ollama-runtime',
    **{name: 'provision/' + name for name in NATIVE},
}


def body(text, name):
    start = text.index('<<' + "'" + name + "'")
    return text[start:text.index('\n' + name, start)]


def array(text, name):
    match = re.search(r'^\s*' + name + r'=\((.*?)\)\s*$', text, re.M | re.S)
    if match is None:
        raise AssertionError('missing array ' + name)
    return shlex.split(match.group(1))


class NativeDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='native-deploy-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.checkout = self.base / 'checkout'
        for relative in SOURCES.values():
            target = self.checkout / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)

    def stage(self, label):
        target = self.base / label
        target.mkdir(mode=0o700)
        script = r'''
set -euo pipefail
export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1
source "$NATIVE_UPDATE"
PLEBIAN_OS_DIR="$NATIVE_CHECKOUT"
systemd-analyze() {
    [ "$#" = 2 ] && [ "$1" = verify ] && [ "$2" = "$NATIVE_STAGE/plebian-os-firstboot.service" ]
}
stage_and_validate_os_layer "$NATIVE_STAGE"
'''
        result = subprocess.run(['/bin/bash', '-c', script], capture_output=True,
            timeout=15, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
                'HOME': str(self.base), 'NATIVE_UPDATE': str(UPDATE),
                'NATIVE_CHECKOUT': str(self.checkout), 'NATIVE_STAGE': str(target)})
        return result, target

    def test_exact_staged_bytes_modes_and_all_twenty_names(self):
        result, stage = self.stage('valid')
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(set(p.name for p in stage.iterdir()), set(SOURCES))
        for name, relative in SOURCES.items():
            self.assertEqual((stage / name).read_bytes(), (ROOT / relative).read_bytes(), name)
        for name in NATIVE:
            self.assertEqual(stat.S_IMODE((stage / name).stat().st_mode),
                             0o755 if name == NATIVE[0] else 0o644)

    def test_every_native_file_is_required_without_installed_fallback(self):
        for index, name in enumerate(NATIVE):
            with self.subTest(name=name):
                source = self.checkout / 'provision' / name
                saved = source.with_suffix(source.suffix + '.saved')
                source.rename(saved)
                try:
                    result, _ = self.stage('missing-' + str(index))
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(b'required file missing', result.stderr)
                finally:
                    saved.rename(source)

    def test_every_native_source_link_refuses(self):
        for index, name in enumerate(NATIVE):
            with self.subTest(name=name):
                source = self.checkout / 'provision' / name
                source.unlink()
                source.symlink_to(ROOT / 'provision' / name)
                try:
                    result, _ = self.stage('link-' + str(index))
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(b'unsafe native helper', result.stderr)
                finally:
                    source.unlink()
                    shutil.copy2(ROOT / 'provision' / name, source)

    def test_every_native_module_is_parsed_without_execution(self):
        for index, name in enumerate(MODULES):
            with self.subTest(name=name):
                source = self.checkout / 'provision' / name
                original = source.read_bytes()
                source.write_bytes(b'this is not valid Python !!!\n')
                try:
                    result, _ = self.stage('syntax-' + str(index))
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(b'staged Python helper validation failed', result.stderr)
                finally:
                    source.write_bytes(original)

    def test_snapshot_restore_deployment_and_root_validation_match(self):
        text = UPDATE.read_text()
        deploy = body(text, 'ROOT_DEPLOY')
        names = array(deploy, 'names')
        self.assertEqual(names, list(SOURCES))
        self.assertEqual(array(text, 'stage_names'), names)
        paths = array(deploy, 'dests')
        modes = array(deploy, 'modes')
        sizes = array(deploy, 'max_sizes')
        provision = (ROOT / 'provision/plebian-os-provision.sh').read_text()
        provision_paths = array(provision, 'PROVISION_ROOT_TRANSACTION_PATHS')
        for name in NATIVE:
            index = names.index(name)
            directory = '/usr/local/sbin/' if name == NATIVE[0] else '/usr/local/libexec/plebian-os/'
            self.assertEqual(paths[index], directory + name)
            self.assertEqual(modes[index], '0755' if name == NATIVE[0] else '0644')
            self.assertEqual(sizes[index], '131072')
            self.assertIn(paths[index], array(body(text, 'ROOT_SNAPSHOT'), 'paths'))
            self.assertIn(paths[index], array(body(text, 'ROOT_RESTORE'), 'paths'))
            self.assertIn(paths[index], provision_paths)
            validation = deploy[deploy.index('# Re-validate the root-owned copies,'):]
            validation = validation[:validation.index('# Nothing becomes destination-readable')]
            self.assertIn('"${new_paths[' + str(index) + ']}"', validation)
        for marker in ('ROOT_SNAPSHOT', 'ROOT_RESTORE'):
            directories = array(body(text, marker), 'managed_dirs')
            self.assertLess(directories.index('/usr/local/libexec'),
                            directories.index('/usr/local/libexec/plebian-os'))

    def test_media_copy_uses_only_fixed_files_and_private_target(self):
        text = (ROOT / 'preseed/preseed.cfg').read_text()
        start = text.index('    mkdir -p /target/usr/local/libexec/plebian-os;')
        end = text.index('    cp /cdrom/plebian-os/plebian-os-update.sh', start)
        copied = self.base / 'media'
        copied.mkdir()
        target = self.base / 'target'
        (target / 'usr/local/sbin').mkdir(parents=True)
        for name in NATIVE:
            shutil.copy2(ROOT / 'provision' / name, copied / name)
        snippet = text[start:end].replace('\\\n', '\n')
        snippet = snippet.replace('/cdrom/plebian-os', shlex.quote(str(copied)))
        snippet = snippet.replace('/target', shlex.quote(str(target)))
        script = 'set -euo pipefail\nchown() { [ "$1" = root:root ]; }\n' + snippet
        result = subprocess.run(['/bin/bash', '-c', script], capture_output=True, timeout=5,
                                env={'PATH': '/usr/bin:/bin', 'HOME': str(self.base)})
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        for name in NATIVE:
            path = target / ('usr/local/sbin' if name == NATIVE[0] else 'usr/local/libexec/plebian-os') / name
            self.assertEqual(path.read_bytes(), (ROOT / 'provision' / name).read_bytes())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755 if name == NATIVE[0] else 0o644)
        wrapper = (ROOT / 'provision/plebian-os-native-runtime').read_text()
        self.assertEqual(wrapper.splitlines()[-1],
            'exec /usr/bin/python3 -I -B /usr/local/libexec/plebian-os/native_runtime.py "$@"')
        self.assertEqual(subprocess.run(['/bin/sh', '-n'], input=wrapper.encode(),
                         capture_output=True, timeout=5).returncode, 0)
        remaster = (ROOT / 'build/remaster-iso.sh').read_text()
        for name in NATIVE:
            self.assertIn(name, remaster)


class BootstrapNativeHelpersTests(unittest.TestCase):
    """Execute the exact copy program with only fixed destinations/UID rerooted.

    All copies, O_PATH reads, syntax checks, modes and rename operations are
    real. This is not root-owned deployment or outer-stack rollback acceptance.
    """
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='native-bootstrap-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'root'
        self.entry = self.root / 'usr/local/sbin'
        self.entry.mkdir(parents=True)
        for path in (self.root, self.root / 'usr', self.root / 'usr/local', self.entry):
            path.chmod(0o755)
        self.modules = self.root / 'usr/local/libexec/plebian-os'
        self.source = self.base / 'source'
        self.source.mkdir()
        for name in NATIVE:
            shutil.copy2(ROOT / 'provision' / name, self.source / name)
        text = (ROOT / 'provision/plebian-os-provision.sh').read_text()
        start = text.index('install_native_runtime_helpers() {')
        begin = text.index('\nimport os\n', start)
        end = text.index('\nPY\n}', begin)
        self.original_program = text[begin:end]
        self.program = self.original_program.replace('required_uid = 0',
                                                     'required_uid = ' + str(os.geteuid()))
        self.program = self.program.replace("Path('/')", 'Path(' + repr(str(self.root)) + ')')
        self.program = self.program.replace("'/usr", repr(str(self.root))[:-1] + '/usr')
        self.assertNotIn("Path('/usr", self.program)
        self.assertNotIn("Path('/')", self.program)
        self.assertIn("'/proc/self/fd/'", self.program)

    def run_copy(self, *, source=None, dry=False):
        return subprocess.run(['/usr/bin/python3', '-I', '-B', '-',
            str(source or self.source), '1' if dry else '0'], input=self.program.encode(),
            capture_output=True, timeout=10, env={'PATH': '/usr/bin:/bin', 'HOME': str(self.base)})

    def test_bootstrap_publishes_complete_set_and_installed_path_keeps_inodes(self):
        result = self.run_copy()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        before = {}
        for name in NATIVE:
            path = (self.entry if name == NATIVE[0] else self.modules) / name
            self.assertEqual(path.read_bytes(), (self.source / name).read_bytes())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755 if name == NATIVE[0] else 0o644)
            before[name] = path.stat().st_ino
        self.assertEqual(set(p.name for p in self.modules.iterdir()), set(MODULES))
        result = self.run_copy(source=self.entry)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        for name in NATIVE:
            path = (self.entry if name == NATIVE[0] else self.modules) / name
            self.assertEqual(path.stat().st_ino, before[name])

    def test_every_missing_source_refuses_before_destination_allocation(self):
        for name in NATIVE:
            with self.subTest(name=name):
                path = self.source / name
                saved = path.with_suffix(path.suffix + '.held')
                path.rename(saved)
                try:
                    result = self.run_copy()
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(self.modules.parent.exists())
                    self.assertEqual(list(self.entry.iterdir()), [])
                finally:
                    saved.rename(path)

    def test_invalid_last_module_does_not_publish_earlier_valid_files(self):
        (self.source / MODULES[-1]).write_text('invalid Python !!!\n')
        result = self.run_copy()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'SyntaxError', result.stderr)
        self.assertFalse(self.modules.parent.exists())
        self.assertEqual(list(self.entry.iterdir()), [])

    def test_destination_symlink_and_writable_parent_preserve_unrelated_files(self):
        outside = self.base / 'outside'
        outside.mkdir()
        sentinel = outside / 'unrelated'
        sentinel.write_bytes(b'unchanged')
        self.modules.parent.symlink_to(outside, target_is_directory=True)
        result = self.run_copy()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'unsafe native helper destination directory', result.stderr)
        self.assertEqual(sentinel.read_bytes(), b'unchanged')
        self.assertEqual(set(p.name for p in outside.iterdir()), {'unrelated'})
        self.modules.parent.unlink()
        self.modules.parent.mkdir()
        self.modules.parent.chmod(0o777)
        result = self.run_copy()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.entry.iterdir()), [])
        self.assertEqual(list(self.modules.parent.iterdir()), [])

    def test_dry_run_checks_complete_source_and_allocates_nothing(self):
        result = self.run_copy(dry=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn(b'dry-run did not deploy files', result.stdout)
        self.assertFalse(self.modules.parent.exists())
        self.assertEqual(list(self.entry.iterdir()), [])
        text = (ROOT / 'provision/plebian-os-provision.sh').read_text()
        self.assertLess(text.index('\nbegin_provision_root_transaction\n'),
                        text.index('\ninstall_native_runtime_helpers\n'))
        self.assertLess(text.index('\ninstall_native_runtime_helpers\n'),
                        text.index('\ncommit_provision_root_transaction\n'))


if __name__ == '__main__':
    unittest.main()
