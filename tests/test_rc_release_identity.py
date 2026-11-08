"""RC identity and refusal controls using disposable Git/source fixtures.

No real ISO, VM, installed updater or release acceptance is produced.
"""
import os
import re
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

import test_closure_selection as closure_fixtures
import test_update_latest_release as update_fixtures

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ('build/acceptance-release-iso.sh', 'build/acceptance-vm.sh',
           'provision/plebian-os-select-closure.sh', 'provision/plebian-os-update.sh')


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


class RcReleaseIdentityTests(unittest.TestCase):
    def test_only_exact_numeric_version_and_numbered_rc_tags(self):
        functions = []
        for name in SCRIPTS:
            source = (ROOT / name).read_text()
            functions.append(re.search(r'valid_release_tag\(\) \{.*?\n\}', source, re.S)[0])
        self.assertEqual(len(set(functions)), 1)
        for version, tag, accepted in [
                ('0.2.3', 'v0.2.3', True), ('0.2.3', 'v0.2.3-rc1', True),
                ('0.2.3', 'v0.2.3-rc12', True), ('0.2.2.1', 'v0.2.2.1', True),
                ('0.2.3', 'v0.2.4-rc1', False), ('0.2.3', 'v0.2.3-rc0', False),
                ('0.2.3', 'v0.2.3-rc01', False), ('0.2.3', 'v0.2.3-rc', False),
                ('0.2.3', 'v0.2.3-rc1-extra', False), ('0.2.3', 'v0.2.3-beta1', False),
                ('0.2.3', 'refs/tags/v0.2.3-rc1', False),
                ('0.2.3', 'v0.2.3-rc1\n', False), ('0.2.3-rc1', 'v0.2.3-rc1', False)]:
            with self.subTest(version=version, tag=tag):
                r = subprocess.run(['bash', '-c', functions[0] + '\nvalid_release_tag "$1" "$2"',
                                    'bash', version, tag])
                self.assertEqual(r.returncode == 0, accepted)

    def _media_fixture(self, base, ref='v0.2.3-rc1', annotated=True):
        repo = base / 'repo'
        (repo / 'build').mkdir(parents=True)
        (repo / 'releases').mkdir()
        (repo / 'VERSION').write_text('0.2.3\n')
        for name in SCRIPTS[:2]:
            (repo / name).write_bytes((ROOT / name).read_bytes())
        (repo / 'build/lib.sh').write_text(
            'PLEBIAN_OS_SESSION_HOME="$FIXTURE_BASE/session"\n'
            'PLEBIAN_OS_ARTIFACTS="$FIXTURE_BASE/artifacts"\n')
        (repo / 'build/build_vm_image.py').write_text(
            '#!/bin/bash\nprintf "%s\\n" "$*" >>"$FIXTURE_BASE/plans"\n')
        (repo / 'build/build_vm_image.py').chmod(0o755)
        vm = (repo / SCRIPTS[1]).read_text()
        # Execute the complete unmodified identity preflight, stopping before
        # any remaster, SSH configuration or VM action.
        (repo / 'build/preflight.sh').write_text(vm[:vm.index('manifest_sha256=')] + 'echo preflight-passed\n')
        manifest = f'PLEBIAN_OS_VERSION=0.2.3\nPLEBIAN_OS_RELEASE_MODE=1\nPLEBIAN_OS_REF={ref}\n'
        (repo / 'releases/0.2.3.env').write_text(manifest)
        git(repo, 'init', '-q')
        git(repo, 'config', 'user.name', 'fixture')
        git(repo, 'config', 'user.email', 'fixture@example.invalid')
        git(repo, 'add', '.')
        git(repo, 'commit', '-qm', 'fixture')
        if annotated:
            git(repo, 'tag', '-a', ref, '-m', 'disposable test fixture')
        else:
            git(repo, 'tag', ref)
        commit = git(repo, 'rev-parse', 'HEAD')
        (base / 'build-info').write_text(manifest +
            f'PLEBIAN_OS_RELEASE=0.2.3\nPLEBIAN_OS_COMMIT={commit}\nPLEBIAN_OS_DIRTY=0\n'
            'PLEBIAN_OS_SSH_ENABLED=0\nPLEBIAN_OS_AUTOBOOT=0\nPLEBIAN_OS_UNATTENDED_DISK=0\n'
            'PLEBIAN_OS_ISO_VOLUME_ID=PLEBIAN-OS 0.2.3 AMD64\n')
        (base / 'fixture.iso').write_bytes(b'public metadata fixture; not an ISO')
        (base / 'bin').mkdir()
        xorriso = base / 'bin/xorriso'
        xorriso.write_text('#!/bin/bash\ncase "$*" in\n'
            '*-extract*) cp "$FIXTURE_BASE/build-info" "${@: -1}" ;;\n'
            '*-report_el_torito*) printf "El Torito boot img BIOS\\nEl Torito boot img UEFI\\n" ;;\n'
            '*-pvd_info*) echo "Volume id    : \'PLEBIAN-OS 0.2.3 AMD64\'" ;;\n'
            '*) exit 90 ;;\nesac\n')
        xorriso.chmod(0o755)
        return repo

    def _media_run(self, repo, vm=False):
        base = repo.parent
        env = dict(os.environ, FIXTURE_BASE=str(base), PATH=str(base / 'bin') + ':' + os.environ['PATH'])
        args = ['bash', str(repo / ('build/preflight.sh' if vm else SCRIPTS[0]))]
        if not vm:
            args += ['--iso', str(base / 'fixture.iso'), '--release', '0.2.3', '--target', 'qemu', '--dry-run']
        return subprocess.run(args, env=env, text=True, capture_output=True)

    def test_rc_strict_and_instrumented_preflight_keep_exact_identity(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = self._media_fixture(base)
            for vm in [False, True]:
                r = self._media_run(repo, vm)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            plans = (base / 'plans').read_text()
            self.assertIn('--firmware bios', plans)
            self.assertIn('--firmware efi', plans)
            self.assertEqual(len(plans.splitlines()), 2)
            # Moving HEAD leaves the tag/ISO pair intact and must still refuse.
            (repo / 'new').write_text('different head\n')
            git(repo, 'add', '.')
            git(repo, 'commit', '-qm', 'different head')
            for vm in [False, True]:
                self.assertNotEqual(self._media_run(repo, vm).returncode, 0)

    def test_media_refuses_lightweight_wrong_suffix_and_manifest_drift(self):
        for mode in ['lightweight', 'suffix', 'manifest', 'hidden-trailing-newline', 'iso-commit', 'missing-tag']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                repo = self._media_fixture(base, ref='v0.2.3-beta1' if mode == 'suffix' else 'v0.2.3-rc1',
                                           annotated=mode != 'lightweight')
                if mode == 'manifest':
                    with (repo / 'releases/0.2.3.env').open('a') as f:
                        f.write('EXTRA=changed\n')
                elif mode == 'hidden-trailing-newline':
                    manifest = repo / 'releases/0.2.3.env'
                    manifest.write_bytes(manifest.read_bytes() + b'\n')
                    git(repo, 'update-index', '--assume-unchanged', 'releases/0.2.3.env')
                elif mode == 'iso-commit':
                    text = (base / 'build-info').read_text()
                    (base / 'build-info').write_text(re.sub(r'PLEBIAN_OS_COMMIT=.*', 'PLEBIAN_OS_COMMIT=' + 'a' * 40, text))
                elif mode == 'missing-tag':
                    git(repo, 'tag', '-d', 'v0.2.3-rc1')
                self.assertNotEqual(self._media_run(repo).returncode, 0)
                if mode != 'iso-commit':
                    self.assertNotEqual(self._media_run(repo, True).returncode, 0)

    def test_selector_explicit_rc_and_trusted_object_controls(self):
        fixture = closure_fixtures.ClosureSelectionTests()
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            fixture._machine(base)
            commit = fixture._source(base, manifest_text=fixture._manifest_text(PLEBIAN_OS_REF='v0.1.8-rc1'),
                                     tag='v0.1.8-rc1')
            trust = git(base / 'src', 'rev-parse', 'refs/tags/v0.1.8-rc1')
            args = ['0.1.8', '--release-tag', 'v0.1.8-rc1', '--source', str(base / 'src'), '--offline', '--dry-run']
            extra = {'PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA': trust}
            r = fixture._run(base, *args, env_extra=extra, trust_tag=False)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(git(base / 'src', 'rev-parse', 'HEAD'), commit)
            for changed in [{'PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA': 'a' * 40}, {}]:
                self.assertNotEqual(fixture._run(base, *args, env_extra=changed, trust_tag=False).returncode, 0)
            for tag in ['v0.1.9-rc1', 'v0.1.8-rc0', 'v0.1.8-rc01', 'v0.1.8-test']:
                bad = args.copy(); bad[2] = tag
                self.assertNotEqual(fixture._run(base, *bad, env_extra=extra, trust_tag=False).returncode, 0)
            # Stable default cannot silently consume the RC manifest/tag.
            self.assertNotEqual(fixture._run(base, '0.1.8', '--source', str(base / 'src'), '--offline',
                                             '--dry-run', env_extra=extra, trust_tag=False).returncode, 0)

    def test_selector_rc_selection_keeps_numeric_version_and_rollback(self):
        fixture = closure_fixtures.ClosureSelectionTests()
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            fixture._machine(base)
            before = (base / 'root/etc/pleb/session.env').read_bytes()
            commit = fixture._source(base, manifest_text=fixture._manifest_text(PLEBIAN_OS_REF='v0.1.8-rc1'),
                                     tag='v0.1.8-rc1')
            trust = git(base / 'src', 'rev-parse', 'refs/tags/v0.1.8-rc1')
            r = fixture._run(base, '0.1.8', '--release-tag', 'v0.1.8-rc1', '--source', str(base / 'src'),
                             '--offline', env_extra={'PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA': trust}, trust_tag=False)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            values = fixture._values(base / 'root/etc/pleb/session.env')
            self.assertEqual(values['PLEBIAN_OS_VERSION'], '0.1.8')
            self.assertEqual(values['PLEBIAN_OS_REF'], commit)
            r = fixture._run(base, '--rollback')
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual((base / 'root/etc/pleb/session.env').read_bytes(), before)

    def test_updater_recovers_rc_tag_from_exact_installed_commit(self):
        fixture = update_fixtures.LatestReleaseUpdateTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo, selector, updater = fixture._candidate_fixture(base)
            manifest = repo / 'releases/0.2.2.env'
            manifest.write_text(manifest.read_text().replace('v0.2.2\n', 'v0.2.2-rc1\n'))
            git(repo, 'add', '.')
            git(repo, 'commit', '-qm', 'rc fixture')
            git(repo, 'tag', '-a', 'v0.2.2-rc1', '-m', 'disposable RC fixture')
            commit = git(repo, 'rev-parse', 'HEAD')
            for ref in ['v0.2.2-rc1', commit]:
                r = fixture._candidate_result(repo, selector, updater, [('PLEBIAN_OS_REF', ref)])
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            # Keep the tag name while changing the object after admission.
            cmd = ('local_candidate_matches_selected_closure 0.2.2; '
                   'git -C "$PLEBIAN_OS_DIR" tag -fa v0.2.2-rc1 -m changed; '
                   'checkout_pinned_ref "$PLEBIAN_OS_DIR" "$PLEBIAN_OS_REF" plebian-os')
            env = dict(os.environ, PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY='1', PLEBIAN_OS_DIR=str(repo),
                       PLEBIAN_OS_RELEASE_MODE='1', PLEBIAN_OS_RELEASE='0.2.2', PLEBIAN_OS_VERSION='0.2.2',
                       PLEBIAN_OS_REF=commit, PLEBIAN_OS_INSTALLED_SELECTOR=str(selector),
                       PLEBIAN_OS_INSTALLED_UPDATER=str(updater))
            r = subprocess.run(['bash', '-c', 'set --; source ' + shlex.quote(str(fixture.update)) + '; ' + cmd],
                               env=env, text=True, capture_output=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('changed before checkout', r.stdout + r.stderr)


if __name__ == '__main__':
    unittest.main()
