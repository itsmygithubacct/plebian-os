"""Runtime dependency verification for the native package's two record schemas.

A synthetic root and a synthetic dpkg database; version comparison is the real
`dpkg --compare-versions`, so Debian ordering (security revisions, epochs) is
what production sees.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_native_transaction import runtime

LIBDIR = 'usr/lib/x86_64-linux-gnu/'


@unittest.skipUnless(shutil.which('dpkg'), 'dpkg --compare-versions is required')
class DependencyPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / LIBDIR).mkdir(parents=True)
        (self.root / 'var/lib/dpkg/info').mkdir(parents=True)
        self.installed = {}      # package -> version
        self.state = {}          # package -> dpkg status line
        self.arch = {}           # package -> architecture
        self.extra_search = {}   # path -> additional dpkg-query --search lines
        self.queries = []
        self.owner = {}          # /absolute path -> package
        self.tree = runtime.state.Tree(self.root, uid=os.getuid())
        self.addCleanup(self.tree.close)
        self.backend = runtime.Dpkg(self.tree, None)
        self.backend.run = self.fake_dpkg
        self.backend.guard = lambda: None
        self.backend.runner = type('Runner', (), {'check': staticmethod(lambda: None)})()

    def fake_dpkg(self, argv, accepted=(0,)):
        if argv[0] == '/usr/bin/dpkg' and argv[1] == '--compare-versions':
            code = subprocess.run(argv, capture_output=True).returncode
            self.assertIn(code, accepted)
            return code, b'', b''
        if argv[0] == '/usr/bin/dpkg-query' and '--search' in argv:
            path = argv[-1]
            if path in self.owner:
                return 0, (self.extra_search.get(path, '') + f'{self.owner[path]}: {path}\n').encode(), b''
            self.assertIn(1, accepted)
            return 1, b'', b'dpkg-query: no path found matching pattern ' + path.encode() + b'\n'
        if argv[0] == '/usr/bin/dpkg-query' and '--show' in argv:
            query = argv[-1]
            name = query.partition(':')[0]
            # The minimum policy qualifies every status query; the exact policy
            # of the previous package is deliberately left as it shipped.
            self.assertIn(query, (name + ':amd64', name))
            self.queries.append(query)
            if name not in self.installed:
                return 1, b'', f'dpkg-query: no packages found matching {query}\n'.encode()
            state = self.state.get(name, 'install ok installed')
            return 0, f'{state}\n{self.installed[name]}\n{self.arch.get(name, "amd64")}\n'.encode(), b''
        raise AssertionError(argv)

    def ship(self, package, version, name, data, *, md5=None):
        self.installed[package] = version
        path = self.root / LIBDIR / name
        path.write_bytes(data)
        path.chmod(0o644)
        self.owner['/' + LIBDIR + name] = package + ':amd64'
        sums = self.root / 'var/lib/dpkg/info' / (package + ':amd64.md5sums')
        line = f'{md5 or hashlib.md5(data).hexdigest()}  {LIBDIR}{name}\n'
        sums.write_text((sums.read_text() if sums.exists() else '') + line)

    def minimum(self, built='2.41-12+deb13u3'):
        return {'dependencies': {'libc6': built},
                'runtime_libraries': {'libc.so.6': {'package': 'libc6', 'version': built,
                                                    'built': {'bytes': 5, 'sha256': '0' * 64}}}}

    def test_a_security_update_to_a_dependency_is_accepted(self):
        self.ship('libc6', '2.41-12+deb13u4', 'libc.so.6', b'patched libc')
        self.backend.dependencies(self.minimum())
        self.assertTrue(self.queries)
        self.assertTrue(all(query.endswith(':amd64') for query in self.queries), self.queries)

    def test_an_older_dependency_than_built_against_refuses(self):
        self.ship('libc6', '2.41-12+deb13u2', 'libc.so.6', b'older libc')
        with self.assertRaisesRegex(Exception, 'at or above'):
            self.backend.dependencies(self.minimum())

    def test_a_library_that_differs_from_its_package_refuses(self):
        self.ship('libc6', '2.41-12+deb13u4', 'libc.so.6', b'patched libc', md5='0' * 32)
        with self.assertRaisesRegex(Exception, 'differs from its package'):
            self.backend.dependencies(self.minimum())

    def test_a_library_owned_by_another_package_refuses(self):
        self.ship('libc6', '2.41-12+deb13u4', 'libc.so.6', b'patched libc')
        self.owner['/' + LIBDIR + 'libc.so.6'] = 'impostor:amd64'
        with self.assertRaisesRegex(Exception, 'not owned by its recorded package'):
            self.backend.dependencies(self.minimum())

    def test_an_unowned_library_refuses(self):
        self.ship('libc6', '2.41-12+deb13u4', 'libc.so.6', b'patched libc')
        del self.owner['/' + LIBDIR + 'libc.so.6']
        with self.assertRaisesRegex(Exception, 'not owned by its recorded package'):
            self.backend.dependencies(self.minimum())

    def test_a_writable_or_linked_library_refuses(self):
        self.ship('libc6', '2.41-12+deb13u4', 'libc.so.6', b'patched libc')
        (self.root / LIBDIR / 'libc.so.6').chmod(0o666)
        # The bounded reader refuses it before the ownership check does.
        with self.assertRaisesRegex(Exception, 'root-owned file|trusted single-link regular file'):
            self.backend.dependencies(self.minimum())
        (self.root / LIBDIR / 'libc.so.6').unlink()
        (self.root / LIBDIR / 'real').write_bytes(b'patched libc')
        (self.root / LIBDIR / 'libc.so.6').symlink_to('real')
        with self.assertRaisesRegex(Exception, 'root-owned file'):
            self.backend.dependencies(self.minimum())

    def test_a_package_without_checksums_refuses(self):
        self.ship('libc6', '2.41-12+deb13u4', 'libc.so.6', b'patched libc')
        (self.root / 'var/lib/dpkg/info/libc6:amd64.md5sums').unlink()
        with self.assertRaisesRegex(Exception, 'no dpkg checksums'):
            self.backend.dependencies(self.minimum())

    def test_an_installed_version_equal_to_the_build_is_accepted(self):
        self.ship('libc6', '2.41-12+deb13u3', 'libc.so.6', b'same libc')
        self.backend.dependencies(self.minimum())

    def test_a_path_with_two_owners_refuses(self):
        self.ship('libc6', '2.41-12+deb13u4', 'libc.so.6', b'patched libc')
        self.owner['/' + LIBDIR + 'libc.so.6'] = 'libc6:amd64, other:amd64'
        with self.assertRaisesRegex(Exception, 'not owned by its recorded package'):
            self.backend.dependencies(self.minimum())

    def test_a_checksum_list_without_the_library_refuses(self):
        self.ship('libc6', '2.41-12+deb13u4', 'libc.so.6', b'patched libc')
        (self.root / 'var/lib/dpkg/info/libc6:amd64.md5sums').write_text('0' * 32 + '  usr/lib/other.so\n')
        with self.assertRaisesRegex(Exception, 'differs from its package'):
            self.backend.dependencies(self.minimum())

    def test_a_package_that_is_not_fully_installed_refuses(self):
        self.ship('libc6', '2.41-12+deb13u4', 'libc.so.6', b'patched libc')
        self.state['libc6'] = 'deinstall ok config-files'
        with self.assertRaisesRegex(Exception, 'at or above'):
            self.backend.dependencies(self.minimum())

    def test_a_foreign_architecture_refuses(self):
        self.ship('libc6', '2.41-12+deb13u4', 'libc.so.6', b'patched libc')
        self.arch['libc6'] = 'i386'
        with self.assertRaisesRegex(Exception, 'at or above'):
            self.backend.dependencies(self.minimum())

    def test_an_old_direct_dependency_without_a_loaded_library_refuses(self):
        self.ship('libc6', '2.41-12+deb13u4', 'libc.so.6', b'patched libc')
        self.installed['libssl3t64'] = '3.5.6-1~deb13u1'
        metadata = self.minimum()
        metadata['dependencies']['libssl3t64'] = '3.5.6-1~deb13u2'
        with self.assertRaisesRegex(Exception, 'at or above.*libssl3t64'):
            self.backend.dependencies(metadata)

    def test_a_diversion_record_beside_the_owner_is_not_an_owner(self):
        self.ship('libc6', '2.41-12+deb13u4', 'libc.so.6', b'patched libc')
        path = '/' + LIBDIR + 'libc.so.6'
        self.extra_search[path] = f'diversion by libc6 from: {path}\ndiversion by libc6 to: {path}.usr-is-merged\n'
        self.backend.dependencies(self.minimum())

    def test_the_minimum_policy_checks_the_loader_closure_it_records(self):
        real = Path('/usr/lib/x86_64-linux-gnu/libc.so.6')
        if not real.exists():
            self.skipTest('needs an amd64 libc')
        metadata = self.minimum()
        metadata.update(content_commit='c' * 40, content_bundle_sha256='d' * 64)
        replies = {}
        def loader(argv, accepted=(0,)):
            if argv[0] == '/usr/bin/ldd':
                return 0, replies['ldd'], b''
            return 0, ('["' + 'c' * 40 + '", "' + 'd' * 64 + '"]\n').encode(), b''
        self.backend.run = loader
        replies['ldd'] = f'\tlibc.so.6 => {real} (0x00007f0000000000)\n'.encode()
        self.backend.loader_health(metadata)
        replies['ldd'] = f'\tlibc.so.6 => {real} (0x00007f0000000000)\n\tlibm.so.6 => {real.with_name("libm.so.6")} (0x00007f0000000000)\n'.encode()
        with self.assertRaisesRegex(Exception, 'closure differs'):
            self.backend.loader_health(metadata)

    def test_a_same_length_change_past_the_first_block_refuses(self):
        original = b'L' * 8192
        self.ship('libc6', '2.41-12+deb13u4', 'libc.so.6', original)
        self.backend.dependencies(self.minimum())    # the whole file is hashed
        (self.root / LIBDIR / 'libc.so.6').write_bytes(original[:6000] + b'X' + original[6001:])
        with self.assertRaisesRegex(Exception, 'differs from its package'):
            self.backend.dependencies(self.minimum())

    def test_the_architecture_qualified_checksums_are_preferred(self):
        self.ship('libc6', '2.41-12+deb13u4', 'libc.so.6', b'patched libc')
        (self.root / 'var/lib/dpkg/info/libc6.md5sums').write_text('0' * 32 + '  ' + LIBDIR + 'libc.so.6\n')
        self.backend.dependencies(self.minimum())
        (self.root / 'var/lib/dpkg/info/libc6:amd64.md5sums').write_text('0' * 32 + '  ' + LIBDIR + 'libc.so.6\n')
        (self.root / 'var/lib/dpkg/info/libc6.md5sums').unlink()
        with self.assertRaisesRegex(Exception, 'differs from its package'):
            self.backend.dependencies(self.minimum())

    def test_a_foreign_architecture_owner_refuses(self):
        self.ship('libc6', '2.41-12+deb13u4', 'libc.so.6', b'patched libc')
        self.owner['/' + LIBDIR + 'libc.so.6'] = 'libc6:i386'
        with self.assertRaisesRegex(Exception, 'not owned by its recorded package'):
            self.backend.dependencies(self.minimum())

    def test_the_exact_policy_of_the_previous_package_is_unchanged(self):
        self.ship('libc6', '2.41-12+deb13u4', 'libc.so.6', b'patched libc')
        with self.assertRaisesRegex(Exception, 'exact installed selection'):
            self.backend.dependencies({'dependencies': {'libc6': '2.41-12+deb13u3'},
                                       'runtime_files': {}})


if __name__ == '__main__':
    unittest.main()
