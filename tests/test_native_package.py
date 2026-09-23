"""Inert synthetic artifact controls; actual release-package replay is separate."""
import gzip
import hashlib
import importlib.util
import io
import json
import lzma
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'provision/native_package.py'
spec = importlib.util.spec_from_file_location('native_artifact', MODULE)
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
SOURCE = 'a' * 40
CONTENT = 'b' * 40


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def regular(name, payload, mode=0o644):
    info = tarfile.TarInfo(name)
    info.mode, info.size = mode, len(payload)
    return info, payload


def tar_bytes(files, *, dotted):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        if dotted:
            parents = {''}
            for name in files:
                parents.update(str(parent) for parent in Path(name).parents if str(parent) != '.')
            for name in sorted(parents):
                info = tarfile.TarInfo('./' + name)
                info.type, info.mode = tarfile.DIRTYPE, 0o755
                archive.addfile(info)
        for name, (entry, data) in sorted(files.items()):
            info = tarfile.TarInfo(('./' if dotted else '') + name)
            info.mode, info.type, info.linkname = entry.mode, entry.type, entry.linkname
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data) if info.isfile() else None)
    return result.getvalue()


def ar_bytes(members, *, slash=False):
    result = bytearray(b'!<arch>\n')
    for name, data in members:
        name += '/' if slash else ''
        result.extend(f'{name:<16}{0:<12}{0:<6}{0:<6}{"100644":<8}{len(data):<10}`\n'.encode())
        result.extend(data)
        if len(data) % 2:
            result.extend(b'\n')
    return bytes(result)


def fixture(*, mutate_control=None, mutate_data=None, mutate_source=None, mutate_record=None,
            source_commit=SOURCE, version_base='0.0.1'):
    """Tiny inert, explicitly synthetic selection; never production authority."""
    lock = {'schema': 'kilix.encodec.debian-dependencies/v1', 'architecture': 'amd64',
            'packages': {name: {'version': '1.0'} for name in ('libonnxruntime1.21', 'libssl3t64', 'libc6')}}
    source = {name: regular(name, b'inert fixture\n') for name in (
        'LICENSE', 'README.md', 'FILE-FORMAT.md', 'THIRD-PARTY-NOTICES.md', 'tools/build_native_package.py')}
    source['VERSION'] = regular('VERSION', (version_base + '\n').encode())
    source['tools/debian-dependencies.json'] = regular('tools/debian-dependencies.json', canonical(lock))
    if mutate_source:
        mutate_source(source)
    files = {name: regular(name, b'inert\n', 0o755 if name in (
        'usr/bin/kenc', 'usr/lib/libkilix-encodec.so.0') else 0o644) for name in native.FILES}
    link = tarfile.TarInfo(native.LINK)
    link.type, link.mode, link.linkname = tarfile.SYMTYPE, 0o777, 'libkilix-encodec.so.0'
    files[native.LINK] = link, b''
    for name in ('LICENSE', 'README.md', 'FILE-FORMAT.md', 'THIRD-PARTY-NOTICES.md'):
        files[native.DOC + name] = regular(native.DOC + name, source[name][1])
    files[native.DOC + 'debian-dependencies.json'] = regular('dependency', canonical(lock))
    files[native.DOC + 'source.tar.gz'] = regular('source', gzip.compress(tar_bytes(source, dotted=False), mtime=0))
    receipt = {'schema': 'kilix.encodec.content-build/v2', 'content_commit': CONTENT, 'bundle_sha256': 'c' * 64}
    files[native.DOC + 'content_bundle.receipt.json'] = regular('receipt', canonical(receipt))
    record = {'schema': 'kilix.encodec.native-package/v1', 'source_commit': source_commit,
              'source_tree': native.source_tree(source), 'content_commit': CONTENT,
              'content_bundle_sha256': 'c' * 64, 'files': {},
              'packages': {name: {'version': row['version'], 'source': 'installed-dpkg'}
                           for name, row in lock['packages'].items()},
              'runtime_files': {name: {'bytes': 6, 'sha256': hashlib.sha256(b'inert\n').hexdigest()}
                                for name in ('ld-linux-x86-64.so.2', 'libc.so.6', 'libcrypto.so.3',
                                             'libonnxruntime.so.1.21.0')}}
    for name, (entry, data) in files.items():
        record['files'][name] = {'link': entry.linkname} if entry.issym() else {
            'bytes': len(data), 'mode': entry.mode, 'sha256': hashlib.sha256(data).hexdigest()}
    if mutate_record:
        mutate_record(record)
    files[native.RECORD] = regular(native.RECORD, canonical(record))
    if mutate_data:
        mutate_data(files)
    version = version_base + '+git' + source_commit[:12] + '.' + CONTENT[:12]
    control_text = (f'Package: libkilix-encodec\nVersion: {version}\nArchitecture: amd64\n'
        'Maintainer: itsmygithubacct <itsmygithubacct@users.noreply.github.com>\n'
        'Depends: libonnxruntime1.21 (= 1.0), libssl3t64 (= 1.0), libc6 (= 1.0)\n'
        'Section: libs\nPriority: optional\n'
        'Description: Shared Kilix codec and installed-content admission\n'
        ' No model payload or model authorization is included.\n').encode()
    control = {'control': regular('control', control_text),
               'postinst': regular('postinst', native.SCRIPT, 0o755),
               'postrm': regular('postrm', native.SCRIPT, 0o755),
               'triggers': regular('triggers', b'activate-noawait ldconfig\n')}
    if mutate_control:
        mutate_control(control)
    return ar_bytes([('debian-binary', b'2.0\n'),
        ('control.tar.xz', lzma.compress(tar_bytes(control, dotted=True))),
        ('data.tar.xz', lzma.compress(tar_bytes(files, dotted=True)))])


def inspect(data, **overrides):
    args = {'sha256': hashlib.sha256(data).hexdigest(), 'byte_count': len(data),
            'source_commit': SOURCE, 'content_commit': CONTENT}
    args.update(overrides)
    return native.inspect_package(data, **args)


class ArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example = fixture()

    def test_import_and_valid_inspection_are_inert(self):
        with patch.object(native.os, 'open', side_effect=AssertionError('unexpected filesystem access')):
            result = inspect(self.example)
        self.assertEqual(result['source_commit'], SOURCE)
        self.assertEqual(result['content_commit'], CONTENT)
        self.assertEqual(set(result['files']), native.FILES | {native.RECORD})
        self.assertEqual(len(result['files']), 17)

    def test_explicit_archive_and_source_selection_cannot_be_omitted_or_changed(self):
        for args in ({'sha256': '0' * 64}, {'byte_count': len(self.example) + 1},
                     {'byte_count': True}, {'byte_count': native.MAX_ARCHIVE + 1},
                     {'source_commit': 'd' * 40}, {'content_commit': 'd' * 40},
                     {'source_commit': SOURCE.upper()}, {'sha256': 'A' * 64}):
            with self.subTest(args=args), self.assertRaises(native.InvalidPackage):
                inspect(self.example, **args)
        with self.assertRaises(native.InvalidPackage):
            inspect(bytearray(self.example))

    def test_plain_and_gnu_short_ar_names(self):
        members = native.ar_members(self.example)
        self.assertEqual(inspect(ar_bytes(list(members.items()), slash=True))['package'], 'libkilix-encodec')

    def test_bad_ar_shape_duplicate_extra_truncation(self):
        members = list(native.ar_members(self.example).items())
        for data in (b'not ar', self.example[:-1], self.example + b'x',
                     ar_bytes(members + [members[0]]), ar_bytes(members + [('extra', b'x')])):
            with self.subTest(data_sha=native.digest(data)), self.assertRaises(native.InvalidPackage):
                inspect(data)

    def test_decompressors_refuse_extra_streams_truncation_and_expansion(self):
        small = lzma.compress(b'x' * 4096)
        for data, limit in ((small + small, 10000), (small[:-8], 10000), (small, 128)):
            with self.subTest(limit=limit, size=len(data)), self.assertRaises(native.InvalidPackage):
                native.expand_xz(data, limit)
        compressed = gzip.compress(b'x' * 4096)
        for data in (compressed + compressed, compressed[:-8]):
            with self.assertRaises(native.InvalidPackage):
                native.expand_source(data)
        with patch.object(native, 'MAX_SOURCE', 128), self.assertRaises(native.InvalidPackage):
            native.expand_source(compressed)

    def test_exact_control_and_maintainer_script_population(self):
        def change_script(control):
            control['postinst'] = regular('postinst', b'#!/bin/sh\nexit 0\n', 0o755)
        def extra_script(control):
            control['preinst'] = regular('preinst', native.SCRIPT, 0o755)
        def wrong_mode(control):
            control['postrm'][0].mode = 0o644
        def extra_trigger(control):
            control['triggers'] = regular('triggers', b'activate other-package\n')
        def wrong_name(control):
            entry, data = control['control']
            control['control'] = regular('control', data.replace(b'libkilix-encodec', b'wrong-package', 1))
        for change in (change_script, extra_script, wrong_mode, extra_trigger, wrong_name):
            with self.subTest(change=change.__name__), self.assertRaises(native.InvalidPackage):
                inspect(fixture(mutate_control=change))

    def test_extra_missing_changed_and_linked_install_paths(self):
        def extra(files):
            files['etc/unowned'] = regular('etc/unowned', b'no')
        def missing(files):
            files.pop('usr/bin/kenc')
        def changed(files):
            files['usr/bin/kenc'] = regular('usr/bin/kenc', b'changed', 0o755)
        def unsafe_link(files):
            files[native.LINK][0].linkname = '/etc/passwd'
        def special(files):
            files['usr/bin/kenc'][0].type = tarfile.FIFOTYPE
        for change in (extra, missing, changed, unsafe_link, special):
            with self.subTest(change=change.__name__), self.assertRaises(native.InvalidPackage):
                inspect(fixture(mutate_data=change))

    def test_record_source_and_content_cannot_disagree(self):
        for field, value in (('schema', 'wrong'), ('source_commit', 'd' * 40),
                             ('source_tree', 'd' * 40), ('content_commit', 'd' * 40),
                             ('content_bundle_sha256', 'd' * 64)):
            with self.subTest(field=field), self.assertRaises(native.InvalidPackage):
                inspect(fixture(mutate_record=lambda row: row.update({field: value})))

    def test_runtime_and_package_dependency_records_are_bounded_and_consistent(self):
        changes = (
            lambda row: row.pop('runtime_files'),
            lambda row: row['runtime_files'].pop('libc.so.6'),
            lambda row: row['runtime_files'].update({'../outside': {'bytes': 6, 'sha256': 'c' * 64}}),
            lambda row: row['runtime_files']['libc.so.6'].update(bytes=True),
            lambda row: row['runtime_files']['libc.so.6'].update(bytes=96 * 1024**2 + 1),
            lambda row: row['runtime_files']['libc.so.6'].update(sha256='bad'),
            lambda row: row['packages'].pop('libc6'),
            lambda row: row['packages']['libc6'].update(version='wrong'),
            lambda row: row['packages']['libc6'].update(source='self-asserted'),
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(native.InvalidPackage):
                inspect(fixture(mutate_record=change))

    def test_duplicate_json_key_and_non_object_refuse(self):
        for raw in (b'{"a":1,"a":2}', b'[]', b'{', b'x' * (256 * 1024 + 1)):
            with self.assertRaises(native.InvalidPackage):
                native.json_object(raw)

    def test_tar_duplicates_traversal_extensions_and_trailing_payload_refuse(self):
        info, data = regular('one', b'one')
        good = tar_bytes({'one': (info, data)}, dotted=False)
        bad_tail = good[:-512] + b'x' + good[-511:]
        with self.assertRaises(native.InvalidPackage):
            native.tar_members(bad_tail, dotted=False, maximum_members=8)
        for name in ('../escape', '/absolute', './alias', 'a//b'):
            with self.subTest(name=name), self.assertRaises(native.InvalidPackage):
                native.tar_members(tar_bytes({name: regular(name, b'x')}, dotted=False), dotted=False, maximum_members=8)
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w', format=tarfile.USTAR_FORMAT) as archive:
            archive.addfile(info, io.BytesIO(data))
            archive.addfile(info, io.BytesIO(data))
        with self.assertRaises(native.InvalidPackage):
            native.tar_members(stream.getvalue(), dotted=False, maximum_members=8)

    def test_long_source_path_accepts_only_canonical_pax(self):
        name = 'receipts/' + 'a' * 130 + '.json'
        data = b'{"accepted":true}\n'
        def archive(extra=None):
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode='w', format=tarfile.PAX_FORMAT) as tar:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o644
                info.pax_headers = extra or {}
                tar.addfile(info, io.BytesIO(data))
            return stream.getvalue()
        valid = archive()
        self.assertEqual(native.tar_members(valid, dotted=False, maximum_members=8,
                                            canonical_source=True)[name][1], data)
        with self.assertRaises(native.InvalidPackage):
            native.tar_members(valid, dotted=False, maximum_members=8)
        with self.assertRaises(native.InvalidPackage):
            native.tar_members(archive({'comment': 'untrusted'}), dotted=False,
                               maximum_members=8, canonical_source=True)

    def test_source_offer_may_not_contain_models(self):
        for name in ('model.onnx', 'model.TH', 'payload.deb', 'nested/weights.safetensors'):
            with self.subTest(name=name), self.assertRaises(native.InvalidPackage):
                inspect(fixture(mutate_source=lambda source: source.update({name: regular(name, b'inert')})))

    def test_source_tree_matches_independent_single_blob(self):
        data = b'hello\n'
        blob = hashlib.sha1(b'blob 6\0' + data).digest()
        raw_tree = b'100644 note\0' + blob
        expected = hashlib.sha1(b'tree ' + str(len(raw_tree)).encode() + b'\0' + raw_tree).hexdigest()
        self.assertEqual(native.source_tree({'note': regular('note', data)}), expected)

    def test_held_input_reopen_success_and_all_refusals_close_descriptors(self):
        baseline = len(os.listdir('/proc/self/fd'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            good = root / 'good.deb'
            good.write_bytes(self.example)
            good.chmod(0o600)
            self.assertEqual(native.read_archive(good), self.example)
            link = root / 'link'
            link.symlink_to(good)
            fifo = root / 'fifo'
            os.mkfifo(fifo, 0o600)
            empty = root / 'empty'
            empty.touch(mode=0o600)
            for path in (link, fifo, empty, root):
                with self.subTest(path=path.name), self.assertRaises(native.InvalidPackage):
                    native.read_archive(path)
                self.assertEqual(len(os.listdir('/proc/self/fd')), baseline)
            other = root / 'other'
            os.link(good, other)
            with self.assertRaises(native.InvalidPackage):
                native.read_archive(good)
            other.unlink()
            good.chmod(0o666)
            with self.assertRaises(native.InvalidPackage):
                native.read_archive(good)
            good.chmod(0o600)
            with patch.object(native.os, 'read', side_effect=MemoryError), self.assertRaises(MemoryError):
                native.read_archive(good)
        self.assertEqual(len(os.listdir('/proc/self/fd')), baseline)


if __name__ == '__main__':
    unittest.main()
