#!/usr/bin/env python3
"""Inspect the selected native Debian artifact without executing its payload.

The externally selected archive digest is authority. Embedded build records
are consistency checks, not substitutes for that selection. This module has
no downloader, installer, model loader or import-time side effects.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
import zlib

MAX_ARCHIVE = 8 * 1024**2
MAX_DATA = 32 * 1024**2
MAX_SOURCE = 16 * 1024**2
DOC = 'usr/share/doc/kilix-encodec/'
RECORD = DOC + 'native-package.json'
LINK = 'usr/lib/libkilix-encodec.so'
FILES = frozenset((
    'usr/bin/kenc', 'usr/include/kilix_encodec.h',
    'usr/include/kilix_encodec_content.h', 'usr/include/kilix_encodec_file.h',
    'usr/lib/libkilix-encodec.a', LINK, 'usr/lib/libkilix-encodec.so.0',
    'usr/lib/pkgconfig/kilix-encodec.pc',
    *(DOC + name for name in ('CONTENT-LICENSE.txt', 'FILE-FORMAT.md', 'LICENSE',
        'README.md', 'THIRD-PARTY-NOTICES.md', 'content_bundle.receipt.json',
        'debian-dependencies.json', 'source.tar.gz')),
))
SCRIPT = b'#!/bin/sh\nset -e\nif [ "$1" = configure ] || [ "$1" = remove ]; then\n  ldconfig\nfi\n'
COMMIT = re.compile(r'[0-9a-f]{40}\Z')
DIGEST = re.compile(r'[0-9a-f]{64}\Z')
SAFE_PATH = re.compile(r'[A-Za-z0-9_.+/-]+\Z')


class InvalidPackage(ValueError):
    """The artifact does not match the selected, bounded native contract."""


def require(condition, message):
    if not condition:
        raise InvalidPackage(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_object(data):
    require(len(data) <= 256 * 1024, 'JSON record exceeds bound')
    def unique(pairs):
        result = {}
        for name, value in pairs:
            require(name not in result, 'duplicate JSON key')
            result[name] = value
        return result
    try:
        value = json.loads(data, object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise InvalidPackage('malformed JSON record') from error
    require(type(value) is dict, 'JSON record must be an object')
    return value


def read_archive(path: Path):
    """Read one immutable byte population through a held regular-file identity."""
    held = os.open(path, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC)
    fd = None
    try:
        before = os.fstat(held)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                'package input must be a single-link regular file')
        require(not before.st_mode & 0o022, 'package input is writable by others')
        require(0 < before.st_size <= MAX_ARCHIVE, 'package input exceeds bound')
        # O_PATH first rejects devices, sockets and FIFOs without opening them
        # for I/O. The deliberate procfs reopen consumes that held inode, never
        # a second lookup of the caller's mutable pathname.
        fd = os.open(f'/proc/self/fd/{held}', os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)
        opened = os.fstat(fd)
        require((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino),
                'package descriptor identity changed')
        chunks = []
        remaining = before.st_size + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(fd)
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                 before.st_ctime_ns, before.st_mode, before.st_nlink) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                 after.st_ctime_ns, after.st_mode, after.st_nlink),
                'package input changed while reading')
        data = b''.join(chunks)
        require(len(data) == before.st_size, 'package input length changed')
        return data
    finally:
        try:
            if fd is not None:
                os.close(fd)
        finally:
            os.close(held)


def ar_members(data):
    require(data.startswith(b'!<arch>\n'), 'not a Debian ar container')
    result = {}
    offset = 8
    while offset < len(data):
        header = data[offset:offset + 60]
        require(len(header) == 60 and header[58:60] == b'`\n', 'malformed ar header')
        try:
            name = header[:16].decode('ascii').rstrip(' ')
            # dpkg-deb writes plain short names; GNU ar may append one slash.
            if name.endswith('/'):
                name = name[:-1]
            count = header[48:58].decode('ascii').strip()
            require(count.isdecimal(), 'invalid ar size')
            count = int(count)
        except (UnicodeError, ValueError) as error:
            raise InvalidPackage('malformed ar member') from error
        require(name in ('debian-binary', 'control.tar.xz', 'data.tar.xz')
                and name not in result, 'unexpected or duplicate Debian member')
        offset += 60
        require(count <= MAX_ARCHIVE and offset + count <= len(data), 'truncated ar member')
        result[name] = data[offset:offset + count]
        offset += count
        if count % 2:
            require(data[offset:offset + 1] == b'\n', 'invalid ar padding')
            offset += 1
    require(set(result) == {'debian-binary', 'control.tar.xz', 'data.tar.xz'}
            and result['debian-binary'] == b'2.0\n', 'unsupported Debian package format')
    return result


def expand_xz(data, maximum):
    try:
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=64 * 1024**2)
        raw = decoder.decompress(data, max_length=maximum + 1)
    except lzma.LZMAError as error:
        raise InvalidPackage('invalid or oversized XZ input') from error
    require(len(raw) <= maximum and decoder.eof and not decoder.unused_data,
            'truncated, concatenated or oversized XZ input')
    return raw


def expand_source(data):
    try:
        decoder = zlib.decompressobj(31)
        raw = decoder.decompress(data, MAX_SOURCE + 1)
    except zlib.error as error:
        raise InvalidPackage('invalid source compression') from error
    require(len(raw) <= MAX_SOURCE and decoder.eof and not decoder.unused_data
            and not decoder.unconsumed_tail, 'truncated or oversized source archive')
    return raw


def tar_members(raw, *, dotted, maximum_members, canonical_source=False):
    """Only canonical directories, regular files and the sole linker symlink."""
    require(len(raw) % 512 == 0, 'unaligned tar archive')
    members = {}
    end = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
            for entry in archive:
                require(len(members) < maximum_members, 'too many tar members')
                require(entry.offset == end, 'noncontiguous tar member')
                if not canonical_source:
                    require(raw[entry.offset + 156:entry.offset + 157] == entry.type,
                            'extended tar headers are not supported')
                name = entry.name
                if dotted:
                    require(name == '.' or name.startswith('./'), 'noncanonical package path')
                    name = '' if name == '.' else name[2:]
                path = PurePosixPath(name)
                require((not name and entry.isdir()) or (bool(SAFE_PATH.fullmatch(name))
                        and not name.startswith('/') and str(path) == name
                        and '..' not in path.parts and '.' not in path.parts), 'unsafe tar path')
                require(name not in members, 'duplicate tar member')
                require(entry.uid == entry.gid == entry.mtime == 0
                        and (not entry.pax_headers or (canonical_source
                             and entry.pax_headers == {'path': entry.name})),
                        'unexpected ownership, time or extended metadata')
                require(entry.type in (tarfile.REGTYPE, tarfile.DIRTYPE, tarfile.SYMTYPE),
                        'unsupported tar member type')
                if entry.isdir():
                    require(entry.size == 0 and entry.mode == 0o755 and not entry.linkname,
                            'invalid directory entry')
                    payload = b''
                elif entry.issym():
                    require(dotted and name == LINK and entry.linkname == 'libkilix-encodec.so.0'
                            and entry.size == 0 and entry.mode == 0o777, 'unexpected link')
                    payload = b''
                else:
                    require(entry.mode in (0o644, 0o755) and not entry.linkname
                            and 0 <= entry.size <= MAX_SOURCE, 'invalid file metadata')
                    reader = archive.extractfile(entry)
                    require(reader is not None, 'missing file bytes')
                    with reader:
                        payload = reader.read(entry.size + 1)
                    require(len(payload) == entry.size, 'truncated tar payload')
                members[name] = (entry, payload)
                end = entry.offset_data + ((entry.size + 511) // 512) * 512
    except tarfile.TarError as error:
        raise InvalidPackage('invalid tar container') from error
    require(len(raw) - end >= 1024 and not any(raw[end:]), 'missing tar end or trailing payload')
    if canonical_source:
        # Python's PAX writer is deterministic for the builder's zeroed
        # metadata. Exact reconstruction rejects extra or reordered extended
        # records, alternate encodings and hidden archive members.
        rebuilt = io.BytesIO()
        with tarfile.open(fileobj=rebuilt, mode='w', format=tarfile.PAX_FORMAT) as archive:
            for name, (entry, payload) in members.items():
                clone = tarfile.TarInfo(name)
                clone.size, clone.mode, clone.mtime = len(payload), entry.mode, 0
                clone.uid = clone.gid = 0
                archive.addfile(clone, io.BytesIO(payload))
        require(rebuilt.getvalue() == raw, 'noncanonical source tar archive')
    return members


def source_tree(files):
    root = {}
    def object_id(kind, raw):
        return hashlib.sha1(kind + b' ' + str(len(raw)).encode() + b'\0' + raw).digest()
    for name, (entry, payload) in files.items():
        require(entry.isfile(), 'source offer must contain regular files only')
        node = root
        parts = name.split('/')
        require(len(parts) <= 12, 'source path is too deep')
        for part in parts[:-1]:
            child = node.setdefault(part, {})
            require(type(child) is dict, 'source path type conflict')
            node = child
        require(parts[-1] not in node, 'source path type conflict')
        node[parts[-1]] = (entry.mode, object_id(b'blob', payload))
    def tree(node):
        entries = []
        for name, value in node.items():
            directory = type(value) is dict
            mode, oid = (b'40000', tree(value)) if directory else (
                b'100755' if value[0] == 0o755 else b'100644', value[1])
            encoded = name.encode('ascii')
            entries.append((encoded + (b'/' if directory else b''), mode + b' ' + encoded + b'\0' + oid))
        return object_id(b'tree', b''.join(value for _, value in sorted(entries)))
    return tree(root).hex()


def inspect_package(data, *, sha256, byte_count, source_commit, content_commit):
    require(type(data) is bytes and type(byte_count) is int and 0 < byte_count <= MAX_ARCHIVE,
            'invalid selected archive size or byte population')
    require(type(sha256) is str and DIGEST.fullmatch(sha256)
            and type(source_commit) is str and COMMIT.fullmatch(source_commit)
            and type(content_commit) is str and COMMIT.fullmatch(content_commit),
            'exact lowercase source and archive identities are required')
    require(len(data) == byte_count and digest(data) == sha256, 'archive does not match selection')
    ar = ar_members(data)
    control = tar_members(expand_xz(ar['control.tar.xz'], 128 * 1024), dotted=True, maximum_members=8)
    require(set(control) == {'', 'control', 'postinst', 'postrm', 'triggers'},
            'unexpected Debian control population')
    for name in ('postinst', 'postrm'):
        require(control[name][0].isfile() and control[name][0].mode == 0o755
                and control[name][1] == SCRIPT, 'unexpected maintainer script')
    require(control['triggers'][0].isfile() and control['triggers'][0].mode == 0o644
            and control['triggers'][1] == b'activate-noawait ldconfig\n', 'unexpected trigger')
    installed = tar_members(expand_xz(ar['data.tar.xz'], MAX_DATA), dotted=True, maximum_members=64)
    actual_files = {name for name, (entry, _) in installed.items() if not entry.isdir()}
    require(actual_files == FILES | {RECORD}, 'unexpected installed path population')
    parents = {''}
    for name in actual_files:
        parents.update(str(parent) for parent in PurePosixPath(name).parents if str(parent) != '.')
    require(set(installed) == actual_files | parents, 'unexpected installed directory')
    require(installed[RECORD][0].isfile() and installed[RECORD][0].mode == 0o644, 'invalid package record')
    record = json_object(installed[RECORD][1])
    require(record.get('schema') == 'kilix.encodec.native-package/v1'
            and record.get('source_commit') == source_commit
            and record.get('content_commit') == content_commit, 'package source identity differs')
    file_records = record.get('files')
    require(type(file_records) is dict and set(file_records) == FILES, 'invalid file record population')
    for name in FILES:
        entry, payload = installed[name]
        expected = file_records[name]
        if name == LINK:
            require(entry.issym() and expected == {'link': 'libkilix-encodec.so.0'}, 'link record differs')
        else:
            mode = 0o755 if name in ('usr/bin/kenc', 'usr/lib/libkilix-encodec.so.0') else 0o644
            require(type(expected) is dict and type(expected.get('bytes')) is int
                    and type(expected.get('mode')) is int and entry.isfile() and entry.mode == mode and expected == {
                'bytes': len(payload), 'mode': mode, 'sha256': digest(payload)}, 'file record differs')
    source = tar_members(expand_source(installed[DOC + 'source.tar.gz'][1]), dotted=False,
                         maximum_members=256, canonical_source=True)
    require(all(PurePosixPath(name).suffix.lower() not in ('.onnx', '.pt', '.th', '.safetensors', '.deb')
                for name in source), 'model or binary package in source offer')
    require(source_tree(source) == record.get('source_tree'), 'source tree differs from archive')
    required = {'VERSION', 'LICENSE', 'README.md', 'FILE-FORMAT.md', 'THIRD-PARTY-NOTICES.md',
                'tools/debian-dependencies.json', 'tools/build_native_package.py'}
    require(required <= set(source), 'source offer incomplete')
    for name in ('LICENSE', 'README.md', 'FILE-FORMAT.md', 'THIRD-PARTY-NOTICES.md'):
        require(installed[DOC + name][1] == source[name][1], 'source notice differs')
    lock_raw = source['tools/debian-dependencies.json'][1]
    require(installed[DOC + 'debian-dependencies.json'][1] == lock_raw, 'dependency offer differs')
    lock = json_object(lock_raw)
    require(lock.get('schema') == 'kilix.encodec.debian-dependencies/v1'
            and lock.get('architecture') == 'amd64' and type(lock.get('packages')) is dict,
            'unsupported dependency closure')
    package_names = ('libonnxruntime1.21', 'libssl3t64', 'libc6')
    dependencies = {}
    for name in package_names:
        row = lock['packages'].get(name)
        require(type(row) is dict and type(row.get('version')) is str
                and re.fullmatch(r'[A-Za-z0-9.+:~_-]{1,100}', row['version']), 'invalid dependency version')
        dependencies[name] = row['version']
    recorded_packages = record.get('packages')
    require(type(recorded_packages) is dict and set(recorded_packages) == set(lock['packages']),
            'recorded dependency package population differs')
    for name, selected in lock['packages'].items():
        row = recorded_packages[name]
        require(type(selected) is dict and type(row) is dict
                and row.get('version') == selected.get('version'), 'recorded package version differs')
        if row.get('source') == 'installed-dpkg':
            require(set(row) == {'version', 'source'}, 'unexpected installed package record')
        else:
            require(row.get('source') == 'verified-private-deb' and set(row) == {'version', 'source', 'sha256'}
                    and type(row.get('sha256')) is str and DIGEST.fullmatch(row['sha256'])
                    and row['sha256'] == selected.get('sha256'), 'private dependency archive record differs')
    runtime_files = record.get('runtime_files')
    require(type(runtime_files) is dict and 1 <= len(runtime_files) <= 128,
            'invalid runtime dependency population')
    require({'ld-linux-x86-64.so.2', 'libc.so.6', 'libcrypto.so.3', 'libonnxruntime.so.1.21.0'} <= set(runtime_files),
            'required runtime dependency identity missing')
    for name, row in runtime_files.items():
        require(type(name) is str and re.fullmatch(r'[A-Za-z0-9_+.-]{1,160}', name)
                and name not in ('.', '..') and type(row) is dict and set(row) == {'bytes', 'sha256'}
                and type(row.get('bytes')) is int and 0 < row['bytes'] <= 96 * 1024**2
                and type(row.get('sha256')) is str and DIGEST.fullmatch(row['sha256']),
                'invalid runtime dependency file identity')
    version_base = source['VERSION'][1].decode('ascii').strip()
    require(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version_base), 'invalid source version')
    version = version_base + '+git' + source_commit[:12] + '.' + content_commit[:12]
    depends = ', '.join(name + ' (= ' + dependencies[name] + ')' for name in package_names)
    expected_control = (f'Package: libkilix-encodec\nVersion: {version}\nArchitecture: amd64\n'
        'Maintainer: itsmygithubacct <itsmygithubacct@users.noreply.github.com>\n'
        f'Depends: {depends}\nSection: libs\nPriority: optional\n'
        'Description: Shared Kilix codec and installed-content admission\n'
        ' No model payload or model authorization is included.\n').encode()
    require(control['control'][0].isfile() and control['control'][0].mode == 0o644
            and control['control'][1] == expected_control, 'Debian control differs')
    receipt = json_object(installed[DOC + 'content_bundle.receipt.json'][1])
    require(receipt.get('schema') == 'kilix.encodec.content-build/v2'
            and receipt.get('content_commit') == content_commit
            and receipt.get('bundle_sha256') == record.get('content_bundle_sha256')
            and type(receipt.get('bundle_sha256')) is str and DIGEST.fullmatch(receipt['bundle_sha256']),
            'embedded Content receipt differs')
    return {'schema': 'plebian-os.native-artifact/v1', 'package': 'libkilix-encodec',
            'version': version, 'architecture': 'amd64', 'sha256': sha256, 'bytes': byte_count,
            'source_commit': source_commit, 'content_commit': content_commit,
            'source_tree': record['source_tree'], 'source_files': len(source),
            'record_sha256': digest(installed[RECORD][1]), 'files': file_records | {
                RECORD: {'bytes': len(installed[RECORD][1]), 'mode': 0o644, 'sha256': digest(installed[RECORD][1])}},
            'dependencies': dependencies, 'runtime_files': runtime_files,
            'content_bundle_sha256': receipt['bundle_sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--bytes', dest='byte_count', type=int, required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--content-commit', required=True)
    args = parser.parse_args()
    try:
        data = read_archive(args.artifact)
        result = inspect_package(data, sha256=args.sha256, byte_count=args.byte_count,
                                 source_commit=args.source_commit, content_commit=args.content_commit)
    except (OSError, InvalidPackage, UnicodeError) as error:
        parser.exit(1, 'native artifact refused: ' + str(error) + '\n')
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
