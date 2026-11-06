#!/usr/bin/python3
"""Install Basic Pitch and the staged LFM2 command model for the desktop user.

Basic Pitch ships in the image and uses the standard distribution policy.
LFM2 is the pinned command-model archive. Installation records coverage of
that model's published custom terms on this machine. It does not waive those
terms, does not use the standard-policy receipt, and does not put a receipt
in the image. An existing model selection is left unchanged.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tarfile
import tempfile


BASIC_PITCH_FILES = (
    'models/nmp.onnx',
    'notices/LICENSE-apache-2.0.txt',
    'notices/NOTICE-basic-pitch.txt',
)
SHARED_BASIC_PITCH = Path('/usr/local/share/plebian-os')
COMMAND_CACHE = Path('/usr/local/share/kilix/model-archives')


def _load_pin(name):
    return json.loads(Path(__file__).with_name(name).read_text())


def _hex64(value):
    return isinstance(value, str) and len(value) == 64 and all(
        character in '0123456789abcdef' for character in value)


def validate_basic_pitch_pin(pin):
    files = pin.get('files')
    if (pin.get('schema') != 'plebian-os.basic-pitch-archive/v1'
            or pin.get('asset_id') != 'basic-pitch-icassp-2022-onnx'
            or pin.get('filename') != 'basic-pitch-icassp-2022-onnx.tar.xz'
            or not _hex64(pin.get('manifest_digest')) or not _hex64(pin.get('sha256'))
            or type(pin.get('bytes')) is not int or pin['bytes'] <= 0
            or not isinstance(files, dict) or set(files) != set(BASIC_PITCH_FILES)):
        raise ValueError('invalid Basic Pitch pin')
    for name, item in files.items():
        if (not isinstance(item, dict) or type(item.get('bytes')) is not int
                or item['bytes'] <= 0 or item['bytes'] > 16 * 1024 * 1024
                or not _hex64(item.get('sha256'))):
            raise ValueError('invalid Basic Pitch file pin: ' + name)


def validate_command_pin(pin):
    if (pin.get('schema') != 'plebian-os.command-model-archive/v1'
            or pin.get('asset_id') != 'lfm2-kilix-commands'
            or not _hex64(pin.get('sha256')) or not _hex64(pin.get('manifest_digest'))
            or type(pin.get('bytes')) is not int or pin['bytes'] <= 0
            or not isinstance(pin.get('version'), str) or not pin['version']
            or not isinstance(pin.get('root'), str) or not pin['root']
            or not isinstance(pin.get('url'), str) or not pin['url'].startswith('https://')
            or not isinstance(pin.get('weight_version'), str) or not pin['weight_version']):
        raise ValueError('invalid command model pin')


def _open_regular(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    stream = os.fdopen(descriptor, 'rb')
    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
        stream.close()
        raise ValueError('model archive must be a regular file')
    return stream


def verify_archive(path, pin):
    """Check the Basic Pitch archive bytes and its three catalogued members."""
    validate_basic_pitch_pin(pin)
    with _open_regular(path) as stream:
        if (os.fstat(stream.fileno()).st_size != pin['bytes']
                or hashlib.file_digest(stream, 'sha256').hexdigest() != pin['sha256']):
            raise ValueError('Basic Pitch archive size or checksum mismatch')
        stream.seek(0)
        seen = set()
        with tarfile.open(fileobj=stream, mode='r:xz') as archive:
            for member in archive:
                name = member.name.removeprefix('./')
                item = pin['files'].get(name)
                if (item is None or name in seen or not member.isfile()
                        or member.size != item['bytes']):
                    raise ValueError('unexpected Basic Pitch archive member: ' + member.name)
                with archive.extractfile(member) as payload:
                    data = payload.read(item['bytes'] + 1)
                if (len(data) != item['bytes']
                        or hashlib.sha256(data).hexdigest() != item['sha256']):
                    raise ValueError('Basic Pitch archive member checksum mismatch: ' + name)
                seen.add(name)
        if seen != set(pin['files']):
            raise ValueError('Basic Pitch archive is incomplete')


def materialize(path, pin, destination):
    verify_archive(path, pin)
    with _open_regular(path) as stream:
        with tarfile.open(fileobj=stream, mode='r:xz') as archive:
            for member in archive:
                name = member.name.removeprefix('./')
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise ValueError('Basic Pitch archive member escapes the archive')
                item = pin['files'].get(name)
                if item is None:
                    raise ValueError('unexpected Basic Pitch archive member: ' + member.name)
                with archive.extractfile(member) as payload:
                    data = payload.read(item['bytes'] + 1)
                if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
                    raise ValueError('Basic Pitch archive member checksum mismatch: ' + name)
                with target.open('xb') as output:
                    output.write(data)
                target.chmod(0o644)


def resolve_basic_pitch(explicit):
    if explicit is not None:
        return Path(explicit)
    filename = 'basic-pitch-icassp-2022-onnx.tar.xz'
    shared = SHARED_BASIC_PITCH / filename
    vendored = Path(__file__).resolve().parent / 'bundles' / filename
    for candidate in (shared, vendored):
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    raise ValueError('the installation media did not supply the Basic Pitch model')


def _load(kilix):
    config = str(Path(kilix) / 'config')
    if config not in sys.path:
        sys.path.insert(0, config)
    import content_models as cm
    import default_models
    return cm, default_models


def _apps_root():
    from kilix_sdk._content_runtime import apps_root
    return apps_root()


def _receipt_digests():
    from kilix_content.receipt import catalog_sha256, release_digest
    return catalog_sha256(), release_digest()


def _installed(cm, asset_id):
    api, lic = cm._api(), cm._license()
    spec = cm._verified_catalog(api).require_asset(asset_id)
    try:
        return cm._verify(api, lic, spec, _apps_root(), io.StringIO()) == 0
    except cm.SetupError:
        return False


def _catalog_spec(cm, asset_id):
    api, lic = cm._api(), cm._license()
    spec = cm._verified_catalog(api).require_asset(asset_id)
    return api, lic, spec, lic.load_determined_records(), lic.ReceiptStore.shared()


def install_basic_pitch(kilix, archive, pin):
    cm, defaults = _load(kilix)
    if _installed(cm, pin['asset_id']):
        print('Basic Pitch already verified; no bundle install needed.')
        return
    with tempfile.TemporaryDirectory(prefix='plebian-basic-pitch-') as temporary:
        root = Path(temporary)
        materialize(archive, pin, root)
        api, lic, spec, records, store = _catalog_spec(cm, pin['asset_id'])
        if spec.manifest_digest != pin['manifest_digest'] or spec.asset_id != pin['asset_id']:
            raise ValueError('Basic Pitch catalog differs from the image pin')
        for item in spec.licenses:
            record = cm._record(records, item.record_digest)
            if not lic.standard_policy_eligible(record):
                raise ValueError('Basic Pitch must use the standard distribution policy')
        with tempfile.TemporaryDirectory(prefix='plebian-basic-pitch-texts-') as scratch:
            texts = lic.load_determined_texts(Path(scratch) / 'texts')
            defaults.authorize(lic, spec, records, store)
            installer = api.Installer(_apps_root())
            installer.ensure_supplied_asset(
                spec, supplied=root, store=store, records=records, notices=texts, report=print)
    print('Basic Pitch installed: ' + pin['asset_id'])


def _command_cache(cache_dir, pin):
    path = Path(cache_dir) / pin['sha256']
    try:
        stream = _open_regular(path)
    except FileNotFoundError as error:
        raise ValueError('the installation media did not supply the command model archive') from error
    except OSError as error:
        raise ValueError('could not read the staged command model archive') from error
    with stream:
        if (os.fstat(stream.fileno()).st_size != pin['bytes']
                or hashlib.file_digest(stream, 'sha256').hexdigest() != pin['sha256']):
            raise ValueError('command model archive size or checksum mismatch')
    return path


def install_command_model(kilix, pin, cache_dir):
    """Install LFM2 from the staged archive and record its custom terms."""
    cm, _defaults = _load(kilix)
    if _installed(cm, pin['asset_id']):
        print('Command model already verified; no archive install needed.')
        return
    _command_cache(cache_dir, pin)
    api, lic, spec, records, store = _catalog_spec(cm, pin['asset_id'])
    if (spec.asset_id != pin['asset_id'] or spec.archive_sha256 != pin['sha256']
            or spec.archive_bytes != pin['bytes'] or spec.manifest_digest != pin['manifest_digest']
            or spec.version != pin['version'] or spec.root != pin['root']
            or spec.source_url != pin['url']):
        raise ValueError('command model catalog differs from the image pin')
    pending = []
    seen = set()
    for item in spec.licenses:
        record = cm._record(records, item.record_digest)
        if lic.standard_policy_eligible(record):
            raise ValueError('command model must keep its published custom terms')
        if record.digest not in seen:
            seen.add(record.digest)
            pending.append(record)
    catalogue_digest, release_digest = _receipt_digests()
    with tempfile.TemporaryDirectory(prefix='plebian-command-model-texts-') as scratch:
        texts = lic.load_determined_texts(Path(scratch) / 'texts')
        for record in pending:
            try:
                lic.require(lic.AssetRef(spec.asset_id, record.digest, spec.manifest_digest),
                            records=records, store=store)
            except lic.CoverageRefused:
                # The image install is the acceptance of the terms published with
                # this model. "yes" is the authority's explicit agreement, bound
                # to the commercial-use condition and the exact licence bytes.
                print('Command model: recording coverage of the published custom terms '
                      'for ' + record.id)
                agreement = lic.capture_agreement(record, 'yes')
                store.write(lic.receipt_from_agreement(
                    record, agreement, manifest_digest=spec.manifest_digest,
                    catalogue_digest=catalogue_digest, release_digest=release_digest))
        # The content installer copies this environment when it is constructed.
        # Point it at the archive just checked so it cannot fall through to a download.
        os.environ['KILIX_CONTENT_ARCHIVE_CACHE'] = str(Path(cache_dir))
        installer = api.Installer(_apps_root())
        installer.ensure_upstream_asset(
            spec, store=store, records=records, notices=texts, report=print)
    print('Command model installed: ' + pin['weight_version'])
    print('Licence documents: /usr/local/share/doc/plebian-os/models/'
          + pin['version'] + '/notices')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kilix', type=Path)
    parser.add_argument('--basic-pitch', type=Path)
    parser.add_argument('--command-cache', type=Path, default=COMMAND_CACHE)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args(argv)
    basic_pin = _load_pin('basic-pitch-model.json')
    command_pin = _load_pin('command-model.json')
    validate_basic_pitch_pin(basic_pin)
    validate_command_pin(command_pin)
    archive = resolve_basic_pitch(args.basic_pitch)
    verify_archive(archive, basic_pin)
    if args.verify_only:
        return 0
    if args.kilix is None:
        parser.error('--kilix is required')
    # --offline is the fresh-install call. Both archives are local either way;
    # this script never downloads model bytes.
    if args.offline and not archive.is_file():
        raise ValueError('the installation media did not supply the Basic Pitch model')
    install_basic_pitch(args.kilix, archive, basic_pin)
    install_command_model(args.kilix, command_pin, args.command_cache)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
