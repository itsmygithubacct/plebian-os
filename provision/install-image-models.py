#!/usr/bin/python3
"""Install Kilix Playalong's default models and the staged LFM2 command model.

Playalong's defaults are Basic Pitch, Demucs htdemucs_6s and Whisper medium.en
(owner decision, 2026-11-08). They use the standard distribution policy and
are installed when missing unless the machine declined them: the model
wizard's kilix-playalong page answered "no", or KILIX_PLAYALONG_MODELS=0 in the
shared settings file. Kilix's config/playalong_models.py reads both answers.
An answer that cannot be read skips them, never installs on a guess.
Basic Pitch and Demucs ship in the image, and a fresh install (--offline)
takes them from there. An online run downloads what the image did not supply,
Demucs from Meta's pinned URL and medium.en from its pinned revision; a failed
download leaves the model out and the next upgrade tries again. Whisper
large-v3 is never a default.

LFM2 is the pinned command-model archive. By the owner's 2026-11-07
determination its published custom terms, including the commercial-use
limitation, are a notice. Installation records a notice receipt for them on
this machine, which claims no agreement. It does not waive those terms, does
not use the standard-policy receipt, does not put a receipt in the image, and
never answers terms that need a typed agreement. An existing model selection
is left unchanged.
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
import time


BASIC_PITCH_FILES = (
    'models/nmp.onnx',
    'notices/LICENSE-apache-2.0.txt',
    'notices/NOTICE-basic-pitch.txt',
)
SHARED_BASIC_PITCH = Path('/usr/local/share/plebian-os')
COMMAND_CACHE = Path('/usr/local/share/kilix/model-archives')
DEMUCS_WEIGHTS = 'models/5c90dfd2-34c22ccb.th'
DEMUCS_LICENCE = 'notices/LICENSE-mit.txt'
DEMUCS_FILES = (DEMUCS_WEIGHTS, DEMUCS_LICENCE)
DEMUCS_LICENCE_SOURCE = Path(__file__).resolve().parent / 'bundles' / 'demucs-htdemucs-6s-LICENSE-mit.txt'
WHISPER_MEDIUM = 'faster-whisper-medium-en'
PLAYALONG_DEFAULTS = ('demucs-htdemucs-6s', 'basic-pitch-icassp-2022-onnx', WHISPER_MEDIUM)
# One online fetch may take this long; Whisper medium.en is 1.5 GB.
FETCH_SECONDS = 7200


def _load_pin(name):
    return json.loads(Path(__file__).with_name(name).read_text())


def _hex64(value):
    return isinstance(value, str) and len(value) == 64 and all(
        character in '0123456789abcdef' for character in value)


def _validate_archive_pin(pin, *, label, schema, asset_id, filename, members, limit):
    files = pin.get('files')
    if (pin.get('schema') != schema or pin.get('asset_id') != asset_id
            or pin.get('filename') != filename
            or not _hex64(pin.get('manifest_digest')) or not _hex64(pin.get('sha256'))
            or type(pin.get('bytes')) is not int or pin['bytes'] <= 0
            or not isinstance(files, dict) or set(files) != set(members)):
        raise ValueError(f'invalid {label} pin')
    for name, item in files.items():
        if (not isinstance(item, dict) or type(item.get('bytes')) is not int
                or item['bytes'] <= 0 or item['bytes'] > limit
                or not _hex64(item.get('sha256'))):
            raise ValueError(f'invalid {label} file pin: ' + name)


def validate_basic_pitch_pin(pin):
    _validate_archive_pin(
        pin, label='Basic Pitch', schema='plebian-os.basic-pitch-archive/v1',
        asset_id='basic-pitch-icassp-2022-onnx', filename='basic-pitch-icassp-2022-onnx.tar.xz',
        members=BASIC_PITCH_FILES, limit=16 * 1024 * 1024)


def validate_demucs_pin(pin):
    _validate_archive_pin(
        pin, label='Demucs', schema='plebian-os.demucs-archive/v1',
        asset_id='demucs-htdemucs-6s', filename='demucs-htdemucs-6s.tar',
        members=DEMUCS_FILES, limit=64 * 1024 * 1024)
    if pin.get('url') != 'https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/5c90dfd2-34c22ccb.th':
        raise ValueError('invalid Demucs pin: the weights URL is not Meta\'s pinned URL')


def validate_playalong_inventory(inventory, basic_pin, demucs_pin):
    """playalong-models.json: the three defaults, how each arrives, and its manifest."""
    assets = inventory.get('assets')
    if (inventory.get('schema') != 'plebian-os.playalong-default-models/v1'
            or not isinstance(assets, dict) or set(assets) != set(PLAYALONG_DEFAULTS)
            or inventory.get('declined_by') != {'wizard_page': 'kilix-playalong',
                                                'setting': 'KILIX_PLAYALONG_MODELS'}):
        raise ValueError('invalid Playalong default model inventory')
    for asset_id, item in assets.items():
        if (not isinstance(item, dict) or set(item) != {'delivery', 'manifest_digest'}
                or item['delivery'] not in ('image', 'online') or not _hex64(item['manifest_digest'])):
            raise ValueError('invalid Playalong default model entry: ' + asset_id)
    for pin in (basic_pin, demucs_pin):
        if assets[pin['asset_id']] != {'delivery': 'image', 'manifest_digest': pin['manifest_digest']}:
            raise ValueError(pin['asset_id'] + ': the Playalong inventory differs from its image pin')
    if assets[WHISPER_MEDIUM]['delivery'] != 'online':
        raise ValueError('Whisper medium.en is not in the image; its delivery is online')


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


def _verify_image_archive(path, pin, label, mode):
    with _open_regular(path) as stream:
        if (os.fstat(stream.fileno()).st_size != pin['bytes']
                or hashlib.file_digest(stream, 'sha256').hexdigest() != pin['sha256']):
            raise ValueError(f'{label} archive size or checksum mismatch')
        stream.seek(0)
        seen = set()
        with tarfile.open(fileobj=stream, mode=mode) as archive:
            for member in archive:
                name = member.name.removeprefix('./')
                item = pin['files'].get(name)
                if (item is None or name in seen or not member.isfile()
                        or member.size != item['bytes']):
                    raise ValueError(f'unexpected {label} archive member: ' + member.name)
                with archive.extractfile(member) as payload:
                    data = payload.read(item['bytes'] + 1)
                if (len(data) != item['bytes']
                        or hashlib.sha256(data).hexdigest() != item['sha256']):
                    raise ValueError(f'{label} archive member checksum mismatch: ' + name)
                seen.add(name)
        if seen != set(pin['files']):
            raise ValueError(f'{label} archive is incomplete')


def _materialize_image_archive(path, pin, destination, label, mode):
    with _open_regular(path) as stream:
        with tarfile.open(fileobj=stream, mode=mode) as archive:
            for member in archive:
                name = member.name.removeprefix('./')
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise ValueError(f'{label} archive member escapes the archive')
                item = pin['files'].get(name)
                if item is None:
                    raise ValueError(f'unexpected {label} archive member: ' + member.name)
                with archive.extractfile(member) as payload:
                    data = payload.read(item['bytes'] + 1)
                if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
                    raise ValueError(f'{label} archive member checksum mismatch: ' + name)
                with target.open('xb') as output:
                    output.write(data)
                target.chmod(0o644)


def verify_archive(path, pin):
    """Check the Basic Pitch archive bytes and its three catalogued members."""
    validate_basic_pitch_pin(pin)
    _verify_image_archive(path, pin, 'Basic Pitch', 'r:xz')


def materialize(path, pin, destination):
    verify_archive(path, pin)
    _materialize_image_archive(path, pin, destination, 'Basic Pitch', 'r:xz')


def verify_demucs_archive(path, pin):
    """Check the Demucs archive bytes, Meta's weights file and its MIT text."""
    validate_demucs_pin(pin)
    _verify_image_archive(path, pin, 'Demucs', 'r:')


def materialize_demucs(path, pin, destination):
    verify_demucs_archive(path, pin)
    _materialize_image_archive(path, pin, destination, 'Demucs', 'r:')


def build_demucs_archive(weights, output, pin):
    """Write the image's Demucs archive from Meta's weights file and the Demucs MIT text.

    Both inputs are checked against the pin first. The archive is an
    uncompressed ustar file with fixed metadata, so the same inputs always give
    the pinned bytes; the result is verified before this returns.
    """
    validate_demucs_pin(pin)
    members = []
    for name, source in ((DEMUCS_WEIGHTS, Path(weights)), (DEMUCS_LICENCE, DEMUCS_LICENCE_SOURCE)):
        item = pin['files'][name]
        with _open_regular(source) as stream:
            data = stream.read(item['bytes'] + 1)
        if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('Demucs input size or checksum mismatch: ' + name)
        members.append((name, data))
    output = Path(output)
    with output.open('xb') as stream:
        try:
            with tarfile.open(fileobj=stream, mode='w', format=tarfile.USTAR_FORMAT) as archive:
                for name, data in members:
                    info = tarfile.TarInfo(name)
                    info.size, info.mode, info.mtime = len(data), 0o644, 0
                    info.uid = info.gid = 0
                    info.uname = info.gname = ''
                    archive.addfile(info, io.BytesIO(data))
        except BaseException:
            output.unlink()
            raise
    try:
        verify_demucs_archive(output, pin)
    except BaseException:
        output.unlink()
        raise
    print('Demucs image archive written: ' + str(output))


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


def resolve_demucs(explicit):
    """The Demucs image archive, or None when this machine has no copy of it."""
    if explicit is not None:
        return Path(explicit)
    shared = SHARED_BASIC_PITCH / 'demucs-htdemucs-6s.tar'
    if shared.is_file() and not shared.is_symlink():
        return shared
    return None


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


def _playalong_installed(cm, asset_id):
    """_installed for a Playalong default, where an incomplete install means "not installed".

    A failed download keeps the standard-policy receipt recorded before it, so
    the next run's verify finds that receipt but not the files and raises
    kilix-content's InstallError. That must lead to another install attempt,
    never to a failed upgrade. The command model keeps _installed as it is.
    """
    try:
        return _installed(cm, asset_id)
    except cm._api().InstallError as error:
        print(f'{asset_id} is not completely installed ({error}); installing it again.',
              file=sys.stderr)
        return False


def _catalog_spec(cm, asset_id):
    api, lic = cm._api(), cm._license()
    spec = cm._verified_catalog(api).require_asset(asset_id)
    return api, lic, spec, lic.load_determined_records(), lic.ReceiptStore.shared()


def _require_standard_policy(cm, lic, spec, records, label):
    for item in spec.licenses:
        record = cm._record(records, item.record_digest)
        if not lic.standard_policy_eligible(record):
            raise ValueError(label + ' must use the standard distribution policy')


def _install_from_image(kilix, archive, pin, label, unpack):
    cm, defaults = _load(kilix)
    if _playalong_installed(cm, pin['asset_id']):
        print(label + ' already verified; no bundle install needed.')
        return
    with tempfile.TemporaryDirectory(prefix='plebian-image-model-') as temporary:
        root = Path(temporary)
        unpack(archive, pin, root)
        api, lic, spec, records, store = _catalog_spec(cm, pin['asset_id'])
        if spec.manifest_digest != pin['manifest_digest'] or spec.asset_id != pin['asset_id']:
            raise ValueError(label + ' catalog differs from the image pin')
        _require_standard_policy(cm, lic, spec, records, label)
        with tempfile.TemporaryDirectory(prefix='plebian-image-model-texts-') as scratch:
            texts = lic.load_determined_texts(Path(scratch) / 'texts')
            defaults.authorize(lic, spec, records, store)
            installer = api.Installer(_apps_root())
            installer.ensure_supplied_asset(
                spec, supplied=root, store=store, records=records, notices=texts, report=print)
    print(label + ' installed: ' + pin['asset_id'])


def install_basic_pitch(kilix, archive, pin):
    _install_from_image(kilix, archive, pin, 'Basic Pitch', materialize)


def fetch_default(kilix, asset_id, label, manifest_digest):
    """Download one Playalong default from its pinned source; False if that failed.

    The catalogued asset must be the one this release pinned, and the licence
    gate is the same as the image's: the standard distribution policy or
    nothing. Only the download may fail without stopping the caller.
    """
    cm, defaults = _load(kilix)
    api, lic, spec, records, store = _catalog_spec(cm, asset_id)
    if spec.asset_id != asset_id or spec.manifest_digest != manifest_digest:
        raise ValueError(label + ' catalog differs from the Playalong inventory')
    _require_standard_policy(cm, lic, spec, records, label)
    with tempfile.TemporaryDirectory(prefix='plebian-playalong-texts-') as scratch:
        texts = lic.load_determined_texts(Path(scratch) / 'texts')
        defaults.authorize(lic, spec, records, store)
        installer = api.Installer(_apps_root())
        try:
            installer.ensure_upstream_asset(
                spec, store=store, records=records, notices=texts, report=print,
                deadline=time.monotonic() + FETCH_SECONDS)
        except (OSError, RuntimeError) as error:
            print(f'{label} was not installed ({error}); the next upgrade tries again.',
                  file=sys.stderr)
            return False
    print(label + ' installed: ' + asset_id)
    return True


def install_demucs(kilix, archive, pin, *, offline):
    """Demucs from the image archive when this machine has it, else from Meta's URL."""
    if archive is not None:
        _install_from_image(kilix, archive, pin, 'Demucs', materialize_demucs)
        return
    cm, _defaults = _load(kilix)
    if _playalong_installed(cm, pin['asset_id']):
        print('Demucs already verified; no download needed.')
    elif offline:
        print('Demucs: the installation media did not supply its archive; '
              'the first online upgrade downloads it.')
    else:
        fetch_default(kilix, pin['asset_id'], 'Demucs', pin['manifest_digest'])


def install_whisper_medium(kilix, manifest_digest, *, offline):
    """Whisper medium.en is not in the image: an online run downloads it."""
    cm, _defaults = _load(kilix)
    if _playalong_installed(cm, WHISPER_MEDIUM):
        print('Whisper medium.en already verified; no download needed.')
    elif offline:
        print('Whisper medium.en is not in the image; the first online upgrade downloads it.')
    else:
        fetch_default(kilix, WHISPER_MEDIUM, 'Whisper medium.en', manifest_digest)


def playalong_declined(kilix):
    """None to install Playalong's defaults, else why this machine skips them."""
    _load(kilix)
    import playalong_models
    if tuple(playalong_models.DEFAULT_MODELS) != PLAYALONG_DEFAULTS:
        raise ValueError("the pinned Kilix names other Playalong default models")
    try:
        return playalong_models.declined()
    except (OSError, ValueError) as error:
        return f'whether this machine declined them cannot be read ({error})'


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
    """Install LFM2 from the staged archive and record its notice terms."""
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
                # Owner determination 2026-11-07 (Debian style): LFM2's terms,
                # including the commercial-use limitation, are a notice. They are
                # shipped with the model under the documents path, not waived, and
                # the receipt records that notice and claims no agreement. Terms
                # that need a typed agreement are never answered here: the image
                # install stops instead.
                if record.expected_decision != 'record':
                    raise ValueError('command model terms need a typed agreement; '
                                     'the image never answers one')
                print('Command model: recording the published notice terms for ' + record.id)
                agreement = lic.capture_agreement(record)
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
    parser.add_argument('--demucs', type=Path,
                        help='the Demucs image archive (default: the copy the image installed, if any)')
    parser.add_argument('--command-cache', type=Path, default=COMMAND_CACHE)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--build-demucs-archive', type=Path, metavar='OUTPUT',
                        help='write the Demucs image archive from --demucs-weights and exit')
    parser.add_argument('--demucs-weights', type=Path)
    args = parser.parse_args(argv)
    basic_pin = _load_pin('basic-pitch-model.json')
    command_pin = _load_pin('command-model.json')
    demucs_pin = _load_pin('demucs-model.json')
    playalong = _load_pin('playalong-models.json')
    validate_basic_pitch_pin(basic_pin)
    validate_command_pin(command_pin)
    validate_demucs_pin(demucs_pin)
    validate_playalong_inventory(playalong, basic_pin, demucs_pin)
    if args.build_demucs_archive is not None:
        if args.demucs_weights is None:
            parser.error('--build-demucs-archive needs --demucs-weights')
        build_demucs_archive(args.demucs_weights, args.build_demucs_archive, demucs_pin)
        return 0
    archive = resolve_basic_pitch(args.basic_pitch)
    verify_archive(archive, basic_pin)
    if args.demucs is not None:
        verify_demucs_archive(args.demucs, demucs_pin)
    if args.verify_only:
        return 0
    if args.kilix is None:
        parser.error('--kilix is required')
    # --offline is the fresh-install call: it downloads nothing. Basic Pitch,
    # Demucs and the command model come from the image.
    if args.offline and not archive.is_file():
        raise ValueError('the installation media did not supply the Basic Pitch model')
    declined = playalong_declined(args.kilix)
    if declined is None:
        install_basic_pitch(args.kilix, archive, basic_pin)
        install_demucs(args.kilix, resolve_demucs(args.demucs), demucs_pin, offline=args.offline)
    else:
        print("Playalong's default models skipped: " + declined)
    install_command_model(args.kilix, command_pin, args.command_cache)
    # The one large download comes last, after everything the image supplies.
    if declined is None:
        install_whisper_medium(args.kilix, playalong['assets'][WHISPER_MEDIUM]['manifest_digest'],
                               offline=args.offline)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
