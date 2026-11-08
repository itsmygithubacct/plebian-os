#!/usr/bin/python3
"""Stage the pinned command model archive and licence documents for offline use.

Runs inside OS installation/upgrade's admin context. This stages bytes only;
Kilix still requires model licence coverage before selecting an installed model.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tarfile
import tempfile
import urllib.request


def check(stream, pin):
    stream.seek(0)
    if (os.fstat(stream.fileno()).st_size != pin['bytes'] or
            hashlib.file_digest(stream, 'sha256').hexdigest() != pin['sha256']):
        raise ValueError('command model archive size or checksum mismatch')
    stream.seek(0)


@contextmanager
def verified(path, pin):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('command model archive must be a regular file')
        check(stream, pin)
        yield stream
        check(stream, pin)


def read_documents(stream, pin):
    documents = {}
    expected = {pin['root'] + '/' + name: (name, item)
                for name, item in pin['documents'].items()}
    with tarfile.open(fileobj=stream, mode='r|gz') as archive:
        for member in archive:
            if member.name not in expected:
                continue
            name, item = expected[member.name]
            if (name in documents or not member.isfile() or
                    member.size != item['bytes'] or member.size > 2 * 1024 * 1024):
                raise ValueError('invalid command model licence document')
            with archive.extractfile(member) as source:
                payload = source.read(item['bytes'] + 1)
            if (len(payload) != item['bytes'] or
                    hashlib.sha256(payload).hexdigest() != item['sha256']):
                raise ValueError('command model licence document checksum mismatch')
            documents[name] = payload
    if set(documents) != set(pin['documents']):
        raise ValueError('command model licence documents are missing')
    return documents


def public_directory(path):
    if os.path.lexists(path):
        if path.is_symlink() or not path.is_dir():
            raise ValueError('command model destination must be a directory')
        return
    public_directory(path.parent)
    try:
        path.mkdir(mode=0o755)
    except FileExistsError:
        public_directory(path)
    else:
        path.chmod(0o755)


def write_documents(root, version, documents):
    public_directory(root)
    target = root / version
    if target.exists():
        if target.is_symlink() or (target / 'notices').is_symlink() or any(
                (target / name).is_symlink() or not (target / name).is_file() or
                (target / name).read_bytes() != data for name, data in documents.items()):
            raise ValueError('existing command model licence documents differ')
        return
    with tempfile.TemporaryDirectory(prefix='.command-model-docs-', dir=root) as tmp:
        stage = Path(tmp) / version
        stage.mkdir(mode=0o755)
        stage.chmod(0o755)
        (stage / 'notices').mkdir(mode=0o755)
        (stage / 'notices').chmod(0o755)
        for name, data in documents.items():
            path = stage / name
            path.write_bytes(data)
            path.chmod(0o644)
        os.rename(stage, target)


def download(target, pin):
    with urllib.request.urlopen(pin['url'], timeout=120) as source, target.open('xb') as out:
        remaining = pin['bytes']
        while remaining:
            block = source.read(min(1024 * 1024, remaining))
            if not block:
                raise ValueError('incomplete command model download')
            out.write(block)
            remaining -= len(block)
        if source.read(1):
            raise ValueError('command model download exceeds pinned size')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--cache-dir', type=Path,
                        default=Path('/usr/local/share/kilix/model-archives'))
    parser.add_argument('--documents-dir', type=Path,
                        default=Path('/usr/local/share/doc/plebian-os/models'))
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args(argv)
    pin = json.loads(Path(__file__).with_name('command-model.json').read_text())
    if (not re.fullmatch(r'[0-9a-f]{64}', pin['sha256']) or
            not re.fullmatch(r'[a-zA-Z0-9._-]+', pin['version']) or
            not re.fullmatch(r'[a-zA-Z0-9._-]+', pin['root']) or
            not pin['documents'] or any(not re.fullmatch(r'notices/[a-zA-Z0-9._-]+', name)
                                        for name in pin['documents'])):
        raise ValueError('invalid command model pin')
    if args.verify_only:
        if args.archive is None:
            parser.error('--verify-only requires --archive')
        with verified(args.archive, pin) as stream:
            read_documents(stream, pin)
        return 0
    cached = args.cache_dir / pin['sha256']
    if os.path.lexists(cached):
        with verified(cached, pin) as stream:
            documents = read_documents(stream, pin)
    else:
        if args.offline and args.archive is None:
            raise ValueError('installation media did not supply the command model archive')
        public_directory(args.cache_dir)
        with tempfile.TemporaryDirectory(prefix='.command-model-', dir=args.cache_dir) as tmp:
            staged = Path(tmp) / 'archive'
            if args.archive is not None:
                with verified(args.archive, pin) as stream, staged.open('xb') as out:
                    shutil.copyfileobj(stream, out, 1024 * 1024)
            else:
                download(staged, pin)
            with verified(staged, pin) as stream:
                documents = read_documents(stream, pin)
            staged.chmod(0o644)
            # Atomic, without overwriting a concurrent stager's verified file.
            try:
                os.link(staged, cached)
            except FileExistsError:
                with verified(cached, pin):
                    pass
    write_documents(args.documents_dir, pin['version'], documents)
    print('Command model archive verified and staged: ' + pin['weight_version'])
    print('Licence documents: ' + str(args.documents_dir / pin['version'] / 'notices'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
