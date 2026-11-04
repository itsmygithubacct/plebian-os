#!/usr/bin/python3
"""Install the release's checksummed default model bundle as the desktop user."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import urllib.request


def verify(path, pin):
    with path.open('rb') as stream:
        if path.stat().st_size != pin['bytes'] or hashlib.file_digest(stream, 'sha256').hexdigest() != pin['sha256']:
            raise ValueError('default model bundle size or checksum mismatch')
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode='r:xz') as archive:
            manifests = [member for member in archive
                         if member.name.removeprefix('./') == 'manifest.json']
            if (len(manifests) != 1 or not manifests[0].isfile()
                    or manifests[0].size > 16384):
                raise ValueError('default model bundle has no unique regular manifest')
            with archive.extractfile(manifests[0]) as manifest:
                inventory = json.load(manifest)
            if inventory != {'schema': 'plebian-os.default-models/v1', 'assets': pin['assets']}:
                raise ValueError('default model bundle inventory differs from the release')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kilix', type=Path)
    parser.add_argument('--archive', type=Path,
                        default=Path('/usr/local/share/plebian-os/default-models.tar.xz'))
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args(argv)
    pin = json.loads(Path(__file__).with_name('default-models.json').read_text())
    if args.verify_only:
        verify(args.archive, pin)
        return 0
    if args.kilix is None:
        parser.error('--kilix is required')
    command = ['/usr/bin/python3', str(args.kilix / 'config/default_models.py')]
    if subprocess.run(command + ['verify'], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode == 0:
        print('Default models already verified; no bundle download needed.')
        return 0
    with tempfile.TemporaryDirectory(prefix='plebian-default-models-') as temporary:
        archive = args.archive
        if not archive.exists():
            if args.offline:
                raise ValueError('the installation media did not supply the default model bundle')
            archive = Path(temporary) / 'default-models.tar.xz'
            with urllib.request.urlopen(pin['url'], timeout=120) as source, archive.open('xb') as target:
                remaining = pin['bytes']
                while remaining:
                    block = source.read(min(1024 * 1024, remaining))
                    if not block:
                        raise ValueError('incomplete default model bundle download')
                    target.write(block)
                    remaining -= len(block)
                if source.read(1):
                    raise ValueError('default model bundle exceeds its pinned size')
        verify(archive, pin)
        subprocess.run(command + ['install', '--archive', str(archive),
                                  '--sha256', pin['sha256']], check=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
