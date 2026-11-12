#!/usr/bin/env python3
"""Verify and transactionally install the pinned RC9 Zell runtime."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import shutil
import tarfile
import tempfile

MAX_BYTES = 256 * 1024 * 1024
REQUIRED = {'zell-neuronte', 'bin/zell', 'VERSION', 'tools/desktop.py', 'tools/zell_secrets.py',
            'tools/zell_shell.py', 'weights/neuronte-split-v4.nrt', 'lib/libneuronte.so',
            'lib/libghostty-vt.so.0', 'libexec/neuronte-display/neuronte_display.py',
            'libexec/neuronte-display/build/libneuronte-display.so',
            'libexec/kilix-secrets', 'libexec/kilix-secretsd',
            'service/kilix-secrets.service', 'service/kilix-secrets.socket'}
REQUIRED.update('tools/'+name+'.py' for name in (
    'zell_os', 'zell_system', 'zell_files', 'zell_schedule', 'zell_devices', 'zell_audio'))


def unpack(archive, pin_path, stage):
    pin = json.loads(pin_path.read_text())
    if pin.get('schema') != 'plebian.zell-runtime/v1' or pin.get('architecture') != platform.machine():
        raise ValueError('Unsupported Zell runtime pin or architecture')
    if archive.is_symlink() or archive.stat().st_size != pin['bytes'] or pin['bytes'] > MAX_BYTES:
        raise ValueError('Zell archive size mismatch or unsafe path')
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != pin['sha256']:
            raise ValueError('Zell archive digest mismatch')
    entries = {}
    total = 0
    with tarfile.open(archive, 'r:xz') as bundle:
        for member in bundle:
            path = PurePosixPath(member.name)
            if (not member.isfile() or path.is_absolute() or '..' in path.parts
                or str(path) != member.name or member.name in entries
                or member.mode not in (0o644, 0o755) or member.size > MAX_BYTES):
                raise ValueError('Unsafe or duplicate Zell archive member')
            total += member.size
            if total > MAX_BYTES or len(entries) >= 1000:
                raise ValueError('Zell runtime exceeds package limits')
            target = stage.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = bundle.extractfile(member)
            with target.open('xb') as out:
                shutil.copyfileobj(stream, out)
            target.chmod(member.mode)
            entries[member.name] = dict(bytes=member.size, mode=member.mode,
                sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    manifest = json.loads((stage/'runtime.json').read_text())
    if (manifest.get('schema') != 'kilix.zell.runtime/v1' or manifest.get('version') != pin['version']
        or manifest.get('architecture') != pin['architecture'] or not REQUIRED <= entries.keys()):
        raise ValueError('Incomplete or mismatched Zell runtime manifest')
    entries.pop('runtime.json')
    if entries != manifest.get('files'):
        raise ValueError('Zell runtime file digest, mode, or inventory mismatch')
    if (stage/'VERSION').read_text().strip() != pin['version']:
        raise ValueError('Zell version mismatch')
    return manifest


def install(archive, pin, destination, bin_dir=None, unit_dir=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError('Refusing a symlink destination')
    with tempfile.TemporaryDirectory(prefix='.zell-', dir=destination.parent) as temporary:
        stage = Path(temporary)/'app'; stage.mkdir(mode=0o755)
        manifest = unpack(archive, pin, stage)
        backup = Path(temporary)/'previous'
        if destination.exists():
            destination.rename(backup)
        try:
            stage.rename(destination)
        except BaseException:
            if backup.exists():
                backup.rename(destination)
            raise
    if bin_dir:
        bin_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(destination/'bin/zell', bin_dir/'zell')
        (bin_dir/'zell').chmod(0o755)
    if unit_dir:
        unit_dir.mkdir(parents=True, exist_ok=True)
        service = (destination/'service/kilix-secrets.service').read_text()
        daemon = str(destination/'libexec/kilix-secretsd').replace('%', '%%').replace('\\', '\\\\').replace('"', '\\"')
        service = service.replace('/usr/local/bin/kilix-secretsd', '"'+daemon+'"')
        (unit_dir/'kilix-secrets.service').write_text(service)
        shutil.copyfile(destination/'service/kilix-secrets.socket', unit_dir/'kilix-secrets.socket')
        for name in ('kilix-secrets.service', 'kilix-secrets.socket'):
            (unit_dir/name).chmod(0o644)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--pin', type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--destination', type=Path, default=Path('/usr/local/share/kilix-zell'))
    parser.add_argument('--bin-dir', type=Path)
    parser.add_argument('--unit-dir', type=Path)
    args = parser.parse_args()
    try:
        if args.verify_only:
            with tempfile.TemporaryDirectory(prefix='zell-verify-') as temporary:
                manifest = unpack(args.archive, args.pin, Path(temporary))
        else:
            manifest = install(args.archive, args.pin, args.destination, args.bin_dir, args.unit_dir)
        print('Zell '+manifest['version']+' runtime '+('verified' if args.verify_only else 'installed'))
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError) as error:
        parser.exit(1, 'Zell runtime: '+str(error)+'\n')


if __name__ == '__main__':
    main()
