"""Neuronte in the 0.2.3 image, on first boot and on upgrade.

The release pins NEURONTE_REF; provision/neuronte-payload.json pins the git blob
id of each file of that commit the Kilix 95 desktop opens. These tests build a
small Neuronte-shaped repository (a real C library with the two entry points
the probe calls) and drive provision/install-neuronte.py through every path:
manifest generation, the blob-less fetch, archive verification, the
user-owned install and its refusals, and the provisioner, updater and image
hooks that call it.
"""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / 'provision' / 'install-neuronte.py'
MANIFEST = ROOT / 'provision' / 'neuronte-payload.json'
PROVISION = ROOT / 'provision' / 'plebian-os-provision.sh'
UPDATE = ROOT / 'provision' / 'plebian-os-update.sh'
SELECT = ROOT / 'provision' / 'plebian-os-select-closure.sh'
REMASTER = ROOT / 'build' / 'remaster-iso.sh'
PRESEED = ROOT / 'preseed' / 'preseed.cfg'
RELEASE_ENV = ROOT / 'releases' / '0.2.3.env'
NOTES = ROOT / 'releases' / '0.2.3-notes.md'
VM_BUILDER = ROOT / 'build' / 'build_vm_image.py'

SPEC = importlib.util.spec_from_file_location('install_neuronte', INSTALLER)
neuronte = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(neuronte)

HAVE_TOOLCHAIN = bool(shutil.which('cc') and shutil.which('make') and shutil.which('git'))

LIBRARY_C = r'''
#include <stdio.h>
#include <stdlib.h>
#include "neuronte.h"
int neuronte_open_file(const char *path, void **out) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    fclose(f);
    *out = malloc(1);
    return *out ? 0 : -1;
}
void neuronte_close(void *handle) { free(handle); }
'''
MAKEFILE = (
    'CC ?= cc\nCFLAGS ?= -O2\n'
    'build/libneuronte.so: src/neuronte.c include/neuronte.h\n'
    '\tmkdir -p build\n'
    '\t$(CC) $(CFLAGS) -std=c11 -fPIC -Iinclude -c -o build/neuronte.o src/neuronte.c\n'
    '\t$(CC) -shared -o $@ build/neuronte.o\n')
FILES = {
    'Makefile': MAKEFILE,
    'LICENSE': 'MIT License\n',
    'THIRD_PARTY_NOTICES.md': '# Third-party notices\n',
    'PROVENANCE.md': '# Provenance\n',
    'README.md': '# Neuronte\n',
    'include/neuronte.h': 'int neuronte_open_file(const char *, void **);\nvoid neuronte_close(void *);\n',
    'src/neuronte.c': LIBRARY_C,
    'train/glyphs.py': 'UI_TOP = {12: 3}\n',
    'weights/neuronte-ui12-v0.nrt': 'NRT small 12\n',
    'weights/neuronte-ui12-italic-v0.nrt': 'NRT italic 12\n',
    'weights/neuronte-ui-large-v0.nrt': 'NRT large\n',
    'weights/neuronte-flame-v0.nrt': 'NRT flame\n',
    'font/ui-12.txt': '# The baseline is row 9.\n',
    'font/ui-12-italic.txt': '# The baseline is row 9.\n',
    # Present in the repository, never opened by the desktop.
    'weights/neuronte-ui40-v0.nrt': 'unused upright 40\n',
    'weights/neuronte-full-v3.nrt': 'unused full\n',
    'font/ui-40.txt': 'unused header 40\n',
    'tests/check.py': 'unused test\n',
}
SELECTED = sorted(name for name in FILES
                  if not name.startswith(('tests/', 'font/ui-40', 'weights/neuronte-ui40',
                                          'weights/neuronte-full')))


def git(*args, cwd):
    env = dict(os.environ, GIT_AUTHOR_NAME='fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
               GIT_COMMITTER_NAME='fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid',
               GIT_AUTHOR_DATE='2026-01-01T00:00:00Z', GIT_COMMITTER_DATE='2026-01-01T00:00:00Z',
               GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1')
    return subprocess.run(['git', *args], cwd=cwd, env=env, check=True,
                          capture_output=True, text=True).stdout.strip()


def make_repo(base, files=FILES):
    repo = base / 'neuronte-upstream'
    repo.mkdir()
    git('init', '-q', '-b', 'main', '.', cwd=repo)
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git('add', '-A', cwd=repo)
    git('commit', '-q', '-m', 'fixture', cwd=repo)
    # What GitHub offers: fetch by commit id, with a blob filter.
    git('config', 'uploadpack.allowFilter', 'true', cwd=repo)
    git('config', 'uploadpack.allowAnySHA1InWant', 'true', cwd=repo)
    return repo, git('rev-parse', 'HEAD', cwd=repo)


def run_installer(*args, env=None, cwd=None):
    base_env = {k: v for k, v in os.environ.items() if k not in ('NEURONTE_HOME', 'NEURONTE_LIB')}
    base_env.update(GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1',
                    PYTHONDONTWRITEBYTECODE='1')
    base_env.update(env or {})
    return subprocess.run([sys.executable, str(INSTALLER), *map(str, args)], env=base_env,
                          capture_output=True, text=True, timeout=300, cwd=cwd)


class Fixture:
    """A repository, its manifest and a fetched archive, in one temporary tree."""

    def __init__(self, base):
        self.base = base
        self.repo, self.ref = make_repo(base)
        self.url = self.repo.as_uri()
        self.manifest = base / 'neuronte-payload.json'
        result = run_installer('write-manifest', '--repo-dir', self.repo, '--commit', self.ref,
                               '--repository', self.url, '--out', self.manifest)
        assert result.returncode == 0, result.stderr
        self.archive = base / ('neuronte-%s.tar.xz' % self.ref)
        result = run_installer('fetch-archive', '--xz', '--manifest', self.manifest, '--ref',
                               self.ref, '--repo', self.url, '--out', self.archive)
        assert result.returncode == 0, result.stderr
        self.destination = base / 'home' / 'sources' / 'neuronte'

    def install(self, *extra, env=None):
        return run_installer('install', '--manifest', self.manifest, '--ref', self.ref,
                             '--repo', self.url, '--destination', self.destination, *extra,
                             env=env)


def tar_with(members):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w') as bundle:
        for name, payload, kind in members:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.mode = 0o644
            info.size = len(payload) if kind == tarfile.REGTYPE else 0
            info.linkname = '/etc/passwd' if kind != tarfile.REGTYPE else ''
            bundle.addfile(info, io.BytesIO(payload) if kind == tarfile.REGTYPE else None)
    return data.getvalue()


class ReleasePinTests(unittest.TestCase):
    """The committed manifest, the release env and the notes name one commit."""

    def env_value(self, key):
        values = re.findall(r'^%s=(.*)$' % key, RELEASE_ENV.read_text(), re.M)
        self.assertEqual(len(values), 1, key)
        return values[0]

    def test_manifest_pins_the_release_commit_and_repository(self):
        manifest = json.loads(MANIFEST.read_text())
        ref = self.env_value('NEURONTE_REF')
        self.assertRegex(ref, r'^[0-9a-f]{40}$')
        self.assertEqual(manifest['commit'], ref)
        self.assertEqual(manifest['repository'], self.env_value('NEURONTE_REPO'))
        self.assertEqual(manifest['repository'], 'https://github.com/itsmygithubacct/neuronte.git')
        self.assertNotIn('NEURONTE_BRANCH', RELEASE_ENV.read_text())
        self.assertIn('| `NEURONTE_REF` | `%s` |' % ref, NOTES.read_text())
        # load_manifest is the gate every path uses.
        neuronte.load_manifest(MANIFEST, ref)
        with self.assertRaisesRegex(ValueError, 'not NEURONTE_REF'):
            neuronte.load_manifest(MANIFEST, '0' * 40)

    def test_manifest_holds_exactly_what_the_desktop_opens(self):
        files = json.loads(MANIFEST.read_text())['files']
        for name in files:
            with self.subTest(name=name):
                self.assertTrue(neuronte.selected(name))
                self.assertNotIn(name, ('build/libneuronte.so', neuronte.RECORD))
        # Kilix 95 af691fe: weight_path() and _face_path() for every small em,
        # the scalable face, the flame, the UI_TOP table and the build inputs.
        for em in range(1, 33):
            self.assertIn('weights/neuronte-ui%d-v0.nrt' % em, files)
            self.assertIn('font/ui-%d.txt' % em, files)
        for em in range(3, 33):
            self.assertIn('weights/neuronte-ui%d-italic-v0.nrt' % em, files)
            self.assertIn('font/ui-%d-italic.txt' % em, files)
        for name in ('weights/neuronte-ui-large-v0.nrt', 'weights/neuronte-flame-v0.nrt',
                     'train/glyphs.py', 'Makefile', 'src/neuronte.c', 'src/utf8.c',
                     'include/neuronte.h', 'LICENSE', 'THIRD_PARTY_NOTICES.md'):
            self.assertIn(name, files)
        # Never opened: em 33 and up go to ui-large, which reads no header.
        for name in ('weights/neuronte-ui33-v0.nrt', 'font/ui-33.txt', 'font/ui-128.txt'):
            self.assertNotIn(name, files)
            self.assertFalse(neuronte.selected(name))
        self.assertEqual(len(files), 135)
        total = sum(entry['bytes'] for entry in files.values())
        self.assertLess(total, 50 * 1024 * 1024)

    def test_no_payload_blob_is_committed(self):
        tracked = subprocess.run(['git', 'ls-files', '-s', 'provision'], cwd=ROOT,
                                 capture_output=True, text=True, check=True).stdout
        self.assertNotIn('neuronte-', ''.join(line for line in tracked.splitlines()
                                              if line.endswith(('.tar', '.tar.xz'))))
        self.assertLess(MANIFEST.stat().st_size, 64 * 1024)


@unittest.skipUnless(HAVE_TOOLCHAIN, 'needs cc, make and git')
class PayloadTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.fx = Fixture(self.base)
        self.manifest = neuronte.load_manifest(self.fx.manifest, self.fx.ref)

    def tearDown(self):
        self._tmp.cleanup()

    def test_write_manifest_selects_by_rule_and_records_git_blob_ids(self):
        files = self.manifest['files']
        self.assertEqual(sorted(files), SELECTED)
        for name in SELECTED:
            blob = git('rev-parse', '%s:%s' % (self.fx.ref, name), cwd=self.fx.repo)
            self.assertEqual(files[name]['blob'], blob)
            self.assertEqual(files[name]['blob'],
                             neuronte.blob_id(FILES[name].encode()))
        self.assertEqual(self.manifest['tree'], git('rev-parse', self.fx.ref + '^{tree}',
                                                    cwd=self.fx.repo))

    def test_fetched_archive_holds_only_the_pinned_files(self):
        with tarfile.open(self.fx.archive, 'r:xz') as bundle:
            names = sorted(m.name for m in bundle if m.isfile())
        self.assertEqual(names, SELECTED)
        result = run_installer('verify', '--manifest', self.fx.manifest, '--ref', self.fx.ref,
                               '--archive', self.fx.archive)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fetch_refuses_a_commit_the_manifest_does_not_pin(self):
        out = self.base / 'other.tar'
        result = run_installer('fetch-archive', '--manifest', self.fx.manifest, '--ref', '1' * 40,
                               '--repo', self.fx.url, '--out', out)
        self.assertEqual(result.returncode, 1)
        self.assertIn('not NEURONTE_REF', result.stderr)
        self.assertFalse(out.exists())

    def test_verify_refuses_every_planted_archive_defect(self):
        good = {m: FILES[m].encode() for m in SELECTED}
        cases = {
            'content mismatch': {**good, 'LICENSE': b'MIT Licensf\n'},
            'size mismatch': {**good, 'LICENSE': b'MIT License, longer\n'},
            'unpinned file': {**good, 'weights/neuronte-ui40-v0.nrt': FILES['weights/neuronte-ui40-v0.nrt'].encode()},
            'lacks 1 pinned': {k: v for k, v in good.items() if k != 'train/glyphs.py'},
        }
        for message, members in cases.items():
            with self.subTest(message=message):
                path = self.base / 'bad.tar'
                path.write_bytes(tar_with([(k, v, tarfile.REGTYPE) for k, v in members.items()]))
                with self.assertRaisesRegex(ValueError, message):
                    neuronte.verify_archive(path, self.manifest)
        for name, kind, message in (('../LICENSE', tarfile.REGTYPE, 'unsafe path'),
                                    ('LICENSE', tarfile.SYMTYPE, 'non-regular'),
                                    ('LICENSE', tarfile.LNKTYPE, 'non-regular'),
                                    ('/LICENSE', tarfile.REGTYPE, 'unsafe path')):
            with self.subTest(name=name, kind=kind):
                path = self.base / 'bad.tar'
                path.write_bytes(tar_with([(name, b'MIT License\n', kind)]))
                with self.assertRaisesRegex(ValueError, message):
                    neuronte.verify_archive(path, self.manifest)
        duplicate = [(k, v, tarfile.REGTYPE) for k, v in good.items()] + [
            ('LICENSE', good['LICENSE'], tarfile.REGTYPE)]
        path = self.base / 'dup.tar'
        path.write_bytes(tar_with(duplicate))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            neuronte.verify_archive(path, self.manifest)

    def test_install_builds_probes_records_and_is_idempotent(self):
        result = self.fx.install('--archive', self.fx.archive, '--no-fetch')
        self.assertEqual(result.returncode, 0, result.stderr)
        tree = self.fx.destination
        self.assertEqual(sorted(p.relative_to(tree).as_posix() for p in tree.rglob('*')
                                if p.is_file()),
                         sorted(SELECTED + ['build/libneuronte.so', neuronte.RECORD]))
        record = json.loads((tree / neuronte.RECORD).read_text())
        self.assertEqual(record['commit'], self.fx.ref)
        self.assertEqual(record['repository'], self.fx.url)
        self.assertEqual(record['library_sha256'],
                         hashlib.sha256((tree / 'build/libneuronte.so').read_bytes()).hexdigest())
        self.assertEqual(record['manifest_sha256'],
                         hashlib.sha256(self.fx.manifest.read_bytes()).hexdigest())
        for path in [tree, *tree.rglob('*')]:
            mode = path.stat().st_mode & 0o777
            expected = 0o755 if path.is_dir() or path.name == 'libneuronte.so' else 0o644
            self.assertEqual(mode, expected, path)
        self.assertEqual(list(tree.parent.glob('.neuronte-*')), [])
        again = self.fx.install('--archive', self.fx.archive, '--no-fetch')
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn('already installed', again.stdout)
        self.assertEqual(json.loads((tree / neuronte.RECORD).read_text()), record)

    def test_install_fetches_only_the_pinned_files_when_no_archive_is_present(self):
        result = self.fx.install('--archive', self.base / 'absent.tar.xz')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.fx.destination / 'build/libneuronte.so').is_file())
        self.assertFalse((self.fx.destination / 'tests').exists())
        self.assertFalse((self.fx.destination / 'weights/neuronte-ui40-v0.nrt').exists())

    def test_failed_download_warns_on_update_and_fails_first_boot(self):
        self.assertEqual(self.fx.install('--archive', self.fx.archive, '--no-fetch').returncode, 0)
        before = (self.fx.destination / neuronte.RECORD).read_bytes()
        manifest = json.loads(self.fx.manifest.read_text())
        unreachable = (self.base / 'unreachable').as_uri()
        manifest.update(commit='2' * 40, repository=unreachable)
        moved = self.base / 'moved.json'
        moved.write_text(json.dumps(manifest))
        common = ('install', '--manifest', moved, '--ref', '2' * 40, '--repo',
                  unreachable, '--destination', self.fx.destination)
        update = run_installer(*common, '--fetch-failure', 'warn')
        self.assertEqual(update.returncode, 0, update.stderr)
        self.assertIn('the next update tries again', update.stderr)
        self.assertEqual((self.fx.destination / neuronte.RECORD).read_bytes(), before)
        first_boot = run_installer(*common)
        self.assertEqual(first_boot.returncode, 1)
        self.assertIn('could not fetch Neuronte', first_boot.stderr)
        self.assertEqual((self.fx.destination / neuronte.RECORD).read_bytes(), before)
        self.assertEqual(list(self.fx.destination.parent.glob('.neuronte-*')), [])

    def test_a_moved_pin_replaces_an_intact_tree(self):
        self.assertEqual(self.fx.install('--archive', self.fx.archive, '--no-fetch').returncode, 0)
        (self.fx.repo / 'LICENSE').write_text('MIT License (next)\n')
        git('commit', '-q', '-am', 'next', cwd=self.fx.repo)
        ref = git('rev-parse', 'HEAD', cwd=self.fx.repo)
        moved = self.base / 'next.json'
        self.assertEqual(run_installer('write-manifest', '--repo-dir', self.fx.repo, '--commit', ref,
                                       '--repository', self.fx.url, '--out', moved).returncode, 0)
        result = run_installer('install', '--manifest', moved, '--ref', ref, '--repo', self.fx.url,
                               '--destination', self.fx.destination)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.fx.destination / 'LICENSE').read_text(), 'MIT License (next)\n')
        self.assertEqual(json.loads((self.fx.destination / neuronte.RECORD).read_text())['commit'], ref)

    def test_local_changes_and_foreign_trees_are_refused_untouched(self):
        def installed():
            shutil.rmtree(self.fx.destination, ignore_errors=True)
            self.assertEqual(self.fx.install('--archive', self.fx.archive, '--no-fetch').returncode, 0)
            return self.fx.destination

        def edit(tree):
            (tree / 'weights/neuronte-ui12-v0.nrt').write_text('edited\n')

        def add(tree):
            (tree / 'weights/mine.nrt').write_text('mine\n')

        def remove(tree):
            (tree / 'font/ui-12.txt').unlink()

        def rebuild(tree):
            (tree / 'build/libneuronte.so').write_bytes(b'not the recorded library')

        def link(tree):
            (tree / 'weights/link.nrt').symlink_to(tree / 'LICENSE')

        for change in (edit, add, remove, rebuild, link):
            with self.subTest(change=change.__name__):
                tree = installed()
                change(tree)
                snapshot = sorted((p.relative_to(tree).as_posix(), p.is_symlink() or p.read_bytes())
                                  for p in tree.rglob('*') if p.is_file() or p.is_symlink())
                manifest = json.loads(self.fx.manifest.read_text())
                result = self.fx.install('--archive', self.fx.archive, '--no-fetch')
                self.assertEqual(result.returncode, 1)
                self.assertIn('refusing', result.stderr)
                self.assertIn('local changes', result.stderr)
                after = sorted((p.relative_to(tree).as_posix(), p.is_symlink() or p.read_bytes())
                               for p in tree.rglob('*') if p.is_file() or p.is_symlink())
                self.assertEqual(after, snapshot)
                self.assertEqual(json.loads(self.fx.manifest.read_text()), manifest)

        shutil.rmtree(self.fx.destination)
        self.fx.destination.mkdir(parents=True)
        (self.fx.destination / 'README.md').write_text('my own clone\n')
        result = self.fx.install('--archive', self.fx.archive, '--no-fetch')
        self.assertEqual(result.returncode, 1)
        self.assertIn('was not installed by Plebian-OS', result.stderr)
        self.assertIn('NEURONTE_HOME', result.stderr)
        self.assertEqual((self.fx.destination / 'README.md').read_text(), 'my own clone\n')

        shutil.rmtree(self.fx.destination)
        elsewhere = self.base / 'elsewhere'
        elsewhere.mkdir()
        self.fx.destination.symlink_to(elsewhere)
        result = self.fx.install('--archive', self.fx.archive, '--no-fetch')
        self.assertEqual(result.returncode, 1)
        self.assertIn('symlink', result.stderr)
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_neuronte_home_naming_the_destination_is_left_alone(self):
        self.fx.destination.mkdir(parents=True)
        (self.fx.destination / 'mine').write_text('mine\n')
        result = self.fx.install('--archive', self.fx.archive, '--no-fetch',
                                 env={'NEURONTE_HOME': str(self.fx.destination)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('leaving that tree to its owner', result.stdout)
        self.assertEqual(sorted(p.name for p in self.fx.destination.iterdir()), ['mine'])
        # A NEURONTE_HOME elsewhere is neither read nor written.
        other = self.base / 'dev-checkout'
        other.mkdir()
        shutil.rmtree(self.fx.destination)
        result = self.fx.install('--archive', self.fx.archive, '--no-fetch',
                                 env={'NEURONTE_HOME': str(other)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.fx.destination / 'build/libneuronte.so').is_file())
        self.assertEqual(list(other.iterdir()), [])

    def test_a_library_that_cannot_open_the_weights_is_not_installed(self):
        files = dict(FILES)
        files['src/neuronte.c'] = LIBRARY_C.replace('return *out ? 0 : -1;', 'return -1;')
        base = self.base / 'broken'
        base.mkdir()
        repo, ref = make_repo(base, files)
        manifest = base / 'm.json'
        self.assertEqual(run_installer('write-manifest', '--repo-dir', repo, '--commit', ref,
                                       '--repository', repo.as_uri(), '--out', manifest).returncode, 0)
        destination = base / 'sources' / 'neuronte'
        result = run_installer('install', '--manifest', manifest, '--ref', ref, '--repo',
                               repo.as_uri(), '--destination', destination)
        self.assertEqual(result.returncode, 1)
        self.assertIn('failed its probe', result.stderr)
        self.assertFalse(destination.exists())
        self.assertEqual(list(destination.parent.glob('.neuronte-*')), [])

    def test_the_installer_refuses_to_run_as_root_unless_told(self):
        source = INSTALLER.read_text()
        self.assertIn("os.geteuid() == 0 and not args.allow_root", source)


class HookTests(unittest.TestCase):
    """Where each path calls the installer, and what it passes."""

    def test_image_build_fetches_verifies_and_stages_the_archive(self):
        text = REMASTER.read_text()
        block = text[text.index('# The Neuronte faces Kilix 95 reads'):]
        block = block[:block.index('\nfi\n') + 4]
        self.assertIn('install-neuronte.py" fetch-archive --xz', block)
        self.assertIn('install-neuronte.py" verify', block)
        self.assertIn('install -m 0644 "$neuronte_archive" "$EXTRACT/plebian-os/neuronte-$NEURONTE_REF.tar.xz"', block)
        self.assertLess(block.index('verify'), block.index('install -m 0644'))
        self.assertIn('elif release_requires_neuronte; then', block)
        self.assertIn('validate_neuronte_release_root\n    validate_voice_release_closure', text)
        self.assertEqual(text.count('    validate_neuronte_release_root\n'), 2)

    def test_installer_copies_the_archive_into_the_target(self):
        late = PRESEED.read_text().split('d-i preseed/late_command string', 1)[1]
        self.assertIn('for neuronte in /cdrom/plebian-os/neuronte-*.tar.xz; do', late)
        self.assertIn('cp "$neuronte" "/target/usr/local/share/plebian-os/${neuronte##*/}" || exit 1', late)
        self.assertIn('chmod 0644 "/target/usr/local/share/plebian-os/${neuronte##*/}"', late)

    def test_first_boot_installs_after_the_models_and_fails_closed(self):
        text = PROVISION.read_text()
        self.assertIn('PROVISION_DEFAULT_MODELS_VERIFIED=1\ninstall_neuronte\n', text)
        body = text[text.index('install_neuronte() {'):text.index('\n}\n', text.index('install_neuronte() {'))]
        self.assertIn('as_user env "${install_env[@]}" /usr/bin/python3 "$installer" install', body)
        self.assertIn('--archive "$archive"', body)
        self.assertIn('|| die "required Neuronte installation failed"', body)
        self.assertNotIn('--fetch-failure', body)
        self.assertIn('NEURONTE_IMAGE_ARCHIVE_DIR=/usr/local/share/plebian-os', text)

    def test_update_installs_after_the_image_models_and_tolerates_only_downloads(self):
        text = UPDATE.read_text()
        self.assertIn('    test_fail_after_boundary image-models\n    install_neuronte_update\n'
                      '    test_fail_after_boundary neuronte\n', text)
        body = text[text.index('install_neuronte_update() {'):]
        body = body[:body.index('\n}\n')]
        self.assertIn('env "${stack_env[@]}" /usr/bin/python3 "$installer" install', body)
        self.assertIn('--fetch-failure warn', body)
        self.assertIn('|| die "required Neuronte installation failed"', body)
        self.assertIn('"NEURONTE_REF=$NEURONTE_REF"', text)
        self.assertIn('NEURONTE_REF NEURONTE_REPO\n', text)  # session.env name gate

    def test_selector_requires_and_announces_the_pin_with_a_blobless_cache(self):
        text = SELECT.read_text()
        self.assertIn('release_requires_neuronte() {\n    [ "$TARGET" = 0.2.3 ]\n}', text)
        self.assertIn('closure_reject "NEURONTE_REPO must name the canonical release repository"', text)
        self.assertIn('"Neuronte" NEURONTE_REF NEURONTE_REPO neuronte blob:none', text)
        self.assertIn('NEURONTE_REF) label="Neuronte" ;;', text)
        self.assertIn('git -C "$cache" config remote.origin.partialclonefilter "$filter"', text)
        self.assertIn('"${filter_args[@]}" origin', text)

    def test_vm_acceptance_loads_neuronte_through_kilix_95(self):
        text = VM_BUILDER.read_text()
        self.assertIn('checks.append(("Neuronte faces", neuronte_contract(neuronte_ref)))', text)
        spec = importlib.util.spec_from_file_location('neuronte_build_vm_image', VM_BUILDER)
        builder = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = builder
        sys.path.insert(0, str(VM_BUILDER.parent))
        try:
            spec.loader.exec_module(builder)
        finally:
            sys.path.remove(str(VM_BUILDER.parent))
            sys.modules.pop(spec.name, None)
        command = builder.neuronte_contract('c' * 40)
        self.assertIn('/usr/local/share/plebian-os/neuronte-' + 'c' * 40 + '.tar.xz', command)
        self.assertIn('cd "$KILIX95_DIR"', command)
        self.assertIn('neuronte_face._library()', command)
        self.assertIn('neuronte_flame.image(32)', command)


@unittest.skipUnless(shutil.which('bash'), 'needs bash')
class ShellPathTests(unittest.TestCase):
    """The provisioner's and updater's functions, sourced, against a stub installer."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.os_dir = self.base / 'plebian-os'
        (self.os_dir / 'provision').mkdir(parents=True)
        self.calls = self.base / 'calls'
        stub = self.os_dir / 'provision' / 'install-neuronte.py'
        stub.write_text('import json, os, sys\n'
                        'open(%r, "a").write(json.dumps(sys.argv[1:]) + "\\n")\n'
                        'sys.exit(int(os.environ.get("STUB_RC", "0")))\n' % str(self.calls))
        shutil.copy(MANIFEST, self.os_dir / 'provision' / 'neuronte-payload.json')
        self.ref = json.loads(MANIFEST.read_text())['commit']

    def tearDown(self):
        self._tmp.cleanup()

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('PLEBIAN_OS_', 'NEURONTE_', 'KILIX', 'PLEB_', 'GPU_TERMINAL'))}
        env.update(HOME=str(self.base / 'home'), **extra)
        return env

    def provision(self, body, **extra):
        script = (f'. "{PROVISION}"\n'
                  'as_user() { "$@"; }\n'
                  'install_env=()\n'
                  f'PLEBIAN_OS_DIR={str(self.os_dir)!r}\n'
                  f'GPU_TERMINAL_SOURCE_HOME={str(self.base / "sources")!r}\n'
                  f'NEURONTE_IMAGE_ARCHIVE_DIR={str(self.base / "image")!r}\n'
                  'DRY_RUN=0\n' + body)
        return subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                              env=self.env(PLEBIAN_OS_PROVISION_LIB_ONLY='1', **extra))

    def update(self, body, **extra):
        script = ('set -euo pipefail\nexport PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n'
                  f'PLEB_STATE_HOME={str(self.base / "state")!r}\n'
                  f'source "{UPDATE}"\n'
                  f'PLEBIAN_OS_DIR={str(self.os_dir)!r}\n'
                  f'GPU_TERMINAL_SOURCE_HOME={str(self.base / "sources")!r}\n' + body)
        return subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                              env=self.env(**extra))

    def recorded(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] \
            if self.calls.exists() else []

    def test_provision_passes_the_image_archive_and_dies_on_failure(self):
        result = self.provision(f'NEURONTE_REF={self.ref}\ninstall_neuronte\necho done\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        call, = self.recorded()
        self.assertEqual(call[0], 'install')
        self.assertEqual(call[call.index('--ref') + 1], self.ref)
        self.assertEqual(call[call.index('--destination') + 1], str(self.base / 'sources/neuronte'))
        self.assertEqual(call[call.index('--archive') + 1],
                         str(self.base / 'image' / ('neuronte-%s.tar.xz' % self.ref)))
        self.assertNotIn('--fetch-failure', call)
        failed = self.provision(f'NEURONTE_REF={self.ref}\ninstall_neuronte\necho done\n',
                                STUB_RC='1')
        self.assertNotEqual(failed.returncode, 0)
        self.assertNotIn('done', failed.stdout)
        self.assertIn('required Neuronte installation failed', failed.stderr)

    def test_provision_refuses_a_partial_ref_a_foreign_repo_and_an_unsafe_archive(self):
        for body, message in (
                ('NEURONTE_REF=eb835f0\n', 'exact NEURONTE_REF'),
                (f'NEURONTE_REF={self.ref}\nNEURONTE_REPO=https://example.invalid/n.git\n',
                 'canonical NEURONTE_REPO')):
            with self.subTest(message=message):
                result = self.provision(body + 'install_neuronte\n')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
        (self.base / 'image').mkdir()
        (self.base / 'image' / ('neuronte-%s.tar.xz' % self.ref)).symlink_to('/etc/hostname')
        result = self.provision(f'NEURONTE_REF={self.ref}\ninstall_neuronte\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('archive is unsafe', result.stderr)
        self.assertEqual(self.recorded(), [])

    def test_provision_without_a_pin_installs_nothing(self):
        result = self.provision('NEURONTE_REF=\ninstall_neuronte\necho done\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.recorded(), [])

    def test_release_mode_requires_the_neuronte_pin(self):
        result = self.provision('PLEBIAN_OS_RELEASE=0.2.3\nNEURONTE_REF=\n'
                                'release_requires_neuronte && echo required\n')
        self.assertIn('required', result.stdout)
        provision = PROVISION.read_text()
        block = provision[provision.index('    if release_requires_neuronte; then'):]
        self.assertIn('die "release mode requires NEURONTE_REF to be a full 40-character', block[:400])

    def test_update_tolerates_a_failed_download_only_inside_the_installer(self):
        result = self.update(f'NEURONTE_REF={self.ref}\ninstall_neuronte_update\necho done\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        call, = self.recorded()
        self.assertIn('--fetch-failure', call)
        self.assertEqual(call[call.index('--fetch-failure') + 1], 'warn')
        self.assertEqual(call[call.index('--archive') + 1],
                         '/usr/local/share/plebian-os/neuronte-%s.tar.xz' % self.ref)
        failed = self.update(f'NEURONTE_REF={self.ref}\ninstall_neuronte_update\necho done\n',
                             STUB_RC='1')
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('required Neuronte installation failed', failed.stderr)

    def test_recorded_commit_feeds_provenance(self):
        tree = self.base / 'sources' / 'neuronte'
        tree.mkdir(parents=True)
        (tree / neuronte.RECORD).write_text(json.dumps({'commit': self.ref}))
        for run in (self.provision, self.update):
            with self.subTest(script=run.__name__):
                result = run('installed_neuronte_commit\n')
                self.assertEqual(result.stdout.strip(), self.ref, result.stderr)
        (tree / neuronte.RECORD).write_text(json.dumps({'commit': 'not-a-commit'}))
        self.assertEqual(self.update('installed_neuronte_commit\n').stdout.strip(), '')

    # Only the parts of the whole-stack transaction that are not about the
    # Neuronte tree are stubbed: begin_stack_transaction's snapshot list and
    # rollback_stack_transaction's restore list are the production ones.
    STACK_STUBS = '\n'.join(f'{name}() {{ :; }}' for name in (
        'require_standard_install_destinations', 'acquire_kilix_transaction_lock',
        'release_kilix_transaction_lock', 'validate_kilix_fork_stamp_path',
        'validate_legacy_kilix_fork_stamp_path', 'validate_shared_settings_snapshot_path',
        'record_stack_transaction_owner', 'record_stack_checkout', 'record_kilix_submodule_tree',
        'snapshot_kilix_engine_generation', 'acquire_voicebox_delivery_lock',
        'validate_root_transaction_dir', 'begin_kilix_engine_mutation',
        'rollback_mpv_runtime_transaction', 'rollback_qt_runtime_transaction',
        'rollback_native_runtime_transaction', 'deinit_new_kilix_submodules',
        'restore_stack_checkout', 'restore_recorded_kilix_submodules',
        'restore_kilix_engine_generation', 'restore_root_stack_snapshot')) + '\n' \
        'begin_root_stack_snapshot() { echo /var/lib/plebian-os/update-rollback.test; }\n'

    def test_a_failed_update_puts_the_previous_tree_back(self):
        tree = self.base / 'sources' / 'neuronte'
        for previous in ('present', 'absent'):
            with self.subTest(previous=previous):
                shutil.rmtree(tree, ignore_errors=True)
                if previous == 'present':
                    (tree / 'weights').mkdir(parents=True)
                    (tree / 'weights' / 'face.nrt').write_text('old')
                    (tree / neuronte.RECORD).write_text('{"commit": "old"}')
                result = self.update(
                    self.STACK_STUBS +
                    'begin_stack_transaction\ntrap - EXIT INT TERM HUP PIPE\n'
                    f'rm -rf -- {str(tree)!r}\nmkdir -p {str(tree / "weights")!r}\n'
                    f'echo new >{str(tree / "weights" / "face.nrt")!r}\n'
                    'rollback_stack_transaction\necho rolled-back\n')
                self.assertIn('rolled-back', result.stdout, result.stderr)
                if previous == 'present':
                    self.assertEqual((tree / 'weights' / 'face.nrt').read_text(), 'old')
                    self.assertEqual((tree / neuronte.RECORD).read_text(), '{"commit": "old"}')
                else:
                    self.assertFalse(tree.exists() or tree.is_symlink(),
                                     'a tree this update created must not survive its rollback')


class OlderUpdaterTests(unittest.TestCase):
    """RC8's updater runs RC9's image-model step; that step installs Neuronte for it."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            'neuronte_image_models', ROOT / 'provision' / 'install-image-models.py')
        cls.models = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.models)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.ref = json.loads(MANIFEST.read_text())['commit']
        self.closure = self.base / 'closure.env'
        self.calls = []

    def tearDown(self):
        self._tmp.cleanup()

    def run_shim(self, closure_text, environ):
        self.closure.write_text(closure_text)

        def run(argv):
            self.calls.append(argv)
            return subprocess.CompletedProcess(argv, int(environ.get('STUB_RC', '0')))
        return self.models.install_neuronte_for_an_older_updater(
            closure=self.closure, environ=environ, run=run)

    def pinned(self, ref=None, repo='https://github.com/itsmygithubacct/neuronte.git'):
        return ('PLEBIAN_OS_VERSION=0.2.3\nNEURONTE_REF=%s\nNEURONTE_REPO=%s\n'
                % (ref or self.ref, repo))

    def test_an_updater_without_neuronte_gets_the_selected_pin_installed(self):
        sources = self.base / 'sources'
        self.assertEqual(self.run_shim(self.pinned(), {'GPU_TERMINAL_SOURCE_HOME': str(sources)}), 0)
        argv, = self.calls
        self.assertEqual(Path(argv[1]), ROOT / 'provision' / 'install-neuronte.py')
        self.assertEqual(argv[argv.index('--ref') + 1], self.ref)
        self.assertEqual(argv[argv.index('--manifest') + 1], str(MANIFEST))
        self.assertEqual(argv[argv.index('--destination') + 1], str(sources / 'neuronte'))
        self.assertEqual(argv[argv.index('--archive') + 1],
                         '/usr/local/share/plebian-os/neuronte-%s.tar.xz' % self.ref)
        self.assertEqual(argv[argv.index('--fetch-failure') + 1], 'warn')

    def test_an_updater_that_installs_neuronte_itself_is_not_doubled(self):
        for value in (self.ref, ''):
            with self.subTest(value=value):
                self.assertEqual(self.run_shim(self.pinned(), {'NEURONTE_REF': value}), 0)
        self.assertEqual(self.calls, [])

    def test_no_pin_no_closure_and_bad_pins(self):
        self.assertEqual(self.run_shim('PLEBIAN_OS_VERSION=0.2.3\n', {}), 0)
        self.assertEqual(self.models.install_neuronte_for_an_older_updater(
            closure=self.base / 'absent.env', environ={}, run=None), 0)
        self.assertEqual(self.calls, [])
        for text in (self.pinned(ref='eb835f0'),
                     self.pinned(repo='https://example.invalid/neuronte.git')):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'invalid Neuronte pin'):
                self.run_shim(text, {})
        self.assertEqual(self.calls, [])
        with self.assertRaisesRegex(ValueError, 'Neuronte installation failed'):
            self.run_shim(self.pinned(), {'STUB_RC': '1'})

    def test_it_runs_only_on_the_online_user_step(self):
        source = (ROOT / 'provision' / 'install-image-models.py').read_text()
        self.assertIn('    if not args.offline:\n        return install_neuronte_for_an_older_updater()\n'
                      '    return 0\n', source)
        # RC8's updater calls exactly this step from the updated checkout.
        update = UPDATE.read_text()
        self.assertIn('"$PLEBIAN_OS_DIR/provision/install-image-models.py" --kilix "$KILIX_DIR"', update)
        self.assertIn('"NEURONTE_REF=$NEURONTE_REF"', update)


if __name__ == '__main__':
    unittest.main()
