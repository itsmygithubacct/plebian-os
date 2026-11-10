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
import subprocess
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
PARADEE_ONNX = 'onnx/paradee_int8.onnx'
PARADEE_CONFIG = 'config.json'
PARADEE_LICENCE = 'notices/LICENSE-apache-2.0.txt'
PARADEE_FILES = (PARADEE_ONNX, PARADEE_CONFIG, PARADEE_LICENCE)
PARADEE_ONNX_URL = (
    'https://huggingface.co/sahilmahendrakar/Paradee-8M-v1.2/resolve/'
    'ed2934d4df8a4fd891e29584c5e1104649409765/onnx/paradee_int8.onnx')
PARADEE_CONFIG_URL = (
    'https://huggingface.co/sahilmahendrakar/Paradee-8M-v1.2/resolve/'
    'ed2934d4df8a4fd891e29584c5e1104649409765/config.json')
PARADEE_LICENCE_SOURCE = Path(__file__).resolve().parent / 'bundles' / 'paradee-8m-v1.2-LICENSE-apache-2.0.txt'
PARADEE_RUNTIME = Path('/usr/lib/kilix/paradee')
PARADEE_PYTHON = Path('/usr/lib/kilix/pd/bin/python')
PARADEE_WHEELHOUSE = SHARED_BASIC_PITCH / 'paradee-wheels'
PARADEE_WHEEL_LOCK = 'paradee-wheels.json'
SPACY_WHEEL = 'en_core_web_sm-3.8.0-py3-none-any.whl'
SPACY_LICENCE = 'notices/LICENSE-mit.txt'
SPACY_SOURCES = 'notices/LICENSES_SOURCES.txt'
SPACY_FILES = (SPACY_WHEEL, SPACY_LICENCE, SPACY_SOURCES)
SPACY_WHEEL_URL = (
    'https://github.com/explosion/spacy-models/releases/download/'
    'en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl')
SPACY_LICENCE_SOURCE = Path(__file__).resolve().parent / 'bundles' / 'en-core-web-sm-3.8.0-LICENSE-mit.txt'
SPACY_SOURCES_SOURCE = Path(__file__).resolve().parent / 'bundles' / 'en-core-web-sm-3.8.0-LICENSES_SOURCES.txt'
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


def validate_paradee_pin(pin):
    _validate_archive_pin(
        pin, label='Paradee', schema='plebian-os.paradee-archive/v1',
        asset_id='paradee-8m-v1.2', filename='paradee-8m-v1.2.tar',
        members=PARADEE_FILES, limit=16 * 1024 * 1024)
    if pin['files'][PARADEE_ONNX].get('url') != PARADEE_ONNX_URL:
        raise ValueError('invalid Paradee pin: the ONNX URL is not the pinned file')
    if pin['files'][PARADEE_CONFIG].get('url') != PARADEE_CONFIG_URL:
        raise ValueError('invalid Paradee pin: config.json URL is not the pinned file')


def validate_spacy_pin(pin):
    _validate_archive_pin(
        pin, label='en_core_web_sm', schema='plebian-os.en-core-web-sm-archive/v1',
        asset_id='en-core-web-sm-3.8.0', filename='en-core-web-sm-3.8.0.tar',
        members=SPACY_FILES, limit=16 * 1024 * 1024)
    if pin['files'][SPACY_WHEEL].get('url') != SPACY_WHEEL_URL:
        raise ValueError('invalid en_core_web_sm pin: the wheel URL is not the pinned file')


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


def _checked_input(pin, name, source, label):
    item = pin['files'][name]
    with _open_regular(source) as stream:
        data = stream.read(item['bytes'] + 1)
    if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
        raise ValueError(label + ' input size or checksum mismatch: ' + name)
    return data


def _build_ustar(members, output, verify):
    """Uncompressed ustar with the same fixed metadata as the Demucs archive."""
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
        verify(output)
    except BaseException:
        output.unlink()
        raise


def verify_paradee_archive(path, pin):
    """Check the Paradee archive, the int8 ONNX, config.json and the Apache-2.0 text."""
    validate_paradee_pin(pin)
    _verify_image_archive(path, pin, 'Paradee', 'r:')


def materialize_paradee(path, pin, destination):
    verify_paradee_archive(path, pin)
    _materialize_image_archive(path, pin, destination, 'Paradee', 'r:')


def build_paradee_archive(onnx, config, output, pin):
    """Write the image's Paradee archive from the pinned ONNX, config.json and Apache-2.0 text."""
    validate_paradee_pin(pin)
    members = [
        (PARADEE_ONNX, _checked_input(pin, PARADEE_ONNX, onnx, 'Paradee')),
        (PARADEE_CONFIG, _checked_input(pin, PARADEE_CONFIG, config, 'Paradee')),
        (PARADEE_LICENCE, _checked_input(pin, PARADEE_LICENCE, PARADEE_LICENCE_SOURCE, 'Paradee')),
    ]
    _build_ustar(members, output, lambda path: verify_paradee_archive(path, pin))
    print('Paradee image archive written: ' + str(output))


def verify_spacy_archive(path, pin):
    """Check the spaCy archive, the en_core_web_sm wheel, its MIT text and LICENSES_SOURCES."""
    validate_spacy_pin(pin)
    _verify_image_archive(path, pin, 'en_core_web_sm', 'r:')


def materialize_spacy(path, pin, destination):
    verify_spacy_archive(path, pin)
    _materialize_image_archive(path, pin, destination, 'en_core_web_sm', 'r:')


def build_spacy_archive(wheel, output, pin):
    """Write the image's en_core_web_sm archive from the pinned wheel and its two texts."""
    validate_spacy_pin(pin)
    members = [
        (SPACY_WHEEL, _checked_input(pin, SPACY_WHEEL, wheel, 'en_core_web_sm')),
        (SPACY_LICENCE, _checked_input(pin, SPACY_LICENCE, SPACY_LICENCE_SOURCE, 'en_core_web_sm')),
        (SPACY_SOURCES, _checked_input(pin, SPACY_SOURCES, SPACY_SOURCES_SOURCE, 'en_core_web_sm')),
    ]
    _build_ustar(members, output, lambda path: verify_spacy_archive(path, pin))
    print('en_core_web_sm image archive written: ' + str(output))


def verify_paradee_runtime(pin, root=None):
    """The runtime files preseed wrote, including the Apache-2.0 text. This does not write them."""
    validate_paradee_pin(pin)
    root = PARADEE_RUNTIME if root is None else Path(root)
    for name in PARADEE_FILES:
        item = pin['files'][name]
        try:
            stream = _open_regular(root / name)
        except (FileNotFoundError, OSError) as error:
            raise ValueError('Paradee runtime file is missing: ' + name) from error
        with stream:
            data = stream.read(item['bytes'] + 1)
        if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('Paradee runtime file size or checksum mismatch: ' + name)


def stage_paradee_runtime(archive, pin, root):
    """Copy a missing ONNX, config.json, or Apache-2.0 text. Root calls this."""
    verify_paradee_archive(archive, pin)
    root = Path(root)
    missing = []
    for name in PARADEE_FILES:
        target = root / name
        if target.exists() or target.is_symlink():
            continue
        missing.append(name)
    if missing:
        with tempfile.TemporaryDirectory(prefix='plebian-paradee-runtime-') as temporary:
            materialize_paradee(archive, pin, Path(temporary))
            for name in missing:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                data = (Path(temporary) / name).read_bytes()
                with target.open('xb') as output:
                    output.write(data)
                target.chmod(0o644)
    verify_paradee_runtime(pin, root)


def load_wheel_lock(path=None):
    path = Path(__file__).with_name(PARADEE_WHEEL_LOCK) if path is None else Path(path)
    lock = json.loads(path.read_text())
    wheels = lock.get('wheels')
    if (lock.get('schema') != 'plebian-os.paradee-wheels/v1' or lock.get('python') != '3.13'
            or not isinstance(wheels, list) or not wheels):
        raise ValueError('invalid Paradee wheel lock')
    seen = set()
    for item in wheels:
        filename = item.get('filename') if isinstance(item, dict) else None
        bundled = item.get('bundle') == filename if isinstance(item, dict) else False
        has_url = (isinstance(item, dict) and isinstance(item.get('url'), str)
                   and item['url'].startswith('https://'))
        if (not isinstance(item, dict) or not isinstance(item.get('name'), str) or not item['name']
                or not isinstance(item.get('version'), str) or not item['version']
                or not isinstance(filename, str) or not filename or filename in seen
                or '/' in filename or filename.startswith('.')
                or bundled == has_url
                or type(item.get('bytes')) is not int or item['bytes'] <= 0
                or not _hex64(item.get('sha256'))):
            raise ValueError('invalid Paradee wheel lock entry')
        seen.add(filename)
    if not any(item['name'] == 'en_core_web_sm' for item in wheels):
        raise ValueError('invalid Paradee wheel lock: en_core_web_sm is missing')
    return lock


def wheel_requirements(lock):
    lines = []
    for item in lock['wheels']:
        lines.append(item['name'] + '==' + item['version'] + ' \\\n    --hash=sha256:' + item['sha256'])
    return '\n'.join(lines) + '\n'


def verify_paradee_wheels(wheelhouse, lock):
    wheelhouse = Path(wheelhouse)
    if not wheelhouse.is_dir() or wheelhouse.is_symlink():
        raise ValueError('the installation media did not supply the Paradee wheelhouse')
    for item in lock['wheels']:
        try:
            stream = _open_regular(wheelhouse / item['filename'])
        except (FileNotFoundError, OSError) as error:
            raise ValueError('Paradee wheel is missing: ' + item['filename']) from error
        with stream:
            data = stream.read(item['bytes'] + 1)
        if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('Paradee wheel size or checksum mismatch: ' + item['filename'])


def install_paradee_venv(wheelhouse, lock, python):
    """Create /usr/lib/kilix/pd from the hash-locked wheelhouse. An existing Python is left alone."""
    python = Path(python)
    if python.is_symlink():
        raise ValueError('Paradee runtime Python is a symlink')
    if python.is_file():
        print('Paradee runtime Python already present: ' + str(python))
        return
    venv = python.parents[1]
    if venv.exists():
        raise ValueError('Paradee runtime directory exists without its Python')
    verify_paradee_wheels(wheelhouse, lock)
    subprocess.run([sys.executable, '-I', '-m', 'venv', '--copies', str(venv)], check=True)
    if python.is_symlink() or not python.is_file():
        raise ValueError('Paradee runtime Python was not created')
    with tempfile.TemporaryDirectory(prefix='plebian-paradee-wheels-') as temporary:
        requirements = Path(temporary) / 'requirements.txt'
        requirements.write_text(wheel_requirements(lock))
        subprocess.run([
            str(python), '-I', '-m', 'pip', 'install', '--disable-pip-version-check',
            '--no-index', '--no-deps', '--find-links', str(wheelhouse),
            '--require-hashes', '--ignore-requires-python', '-r', str(requirements),
        ], check=True)
    print('Paradee runtime Python installed: ' + str(python))


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


def _resolve_shared_archive(explicit, filename):
    """An image archive, or None when this machine has no regular copy of it."""
    if explicit is not None:
        return Path(explicit)
    shared = SHARED_BASIC_PITCH / filename
    if shared.is_file() and not shared.is_symlink():
        return shared
    return None


def resolve_paradee(explicit):
    return _resolve_shared_archive(explicit, 'paradee-8m-v1.2.tar')


def resolve_spacy(explicit):
    return _resolve_shared_archive(explicit, 'en-core-web-sm-3.8.0.tar')


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


def install_paradee(kilix, archive, pin):
    """Paradee from the image. The runtime files are checked and never rewritten here."""
    verify_paradee_runtime(pin)
    cm, _defaults = _load(kilix)
    if _playalong_installed(cm, pin['asset_id']):
        print('Paradee already verified; no bundle install needed.')
        return
    if archive is None:
        raise ValueError('the installation media did not supply the Paradee model')
    _install_from_image(kilix, archive, pin, 'Paradee', materialize_paradee)


def install_spacy(kilix, archive, pin):
    """en_core_web_sm from the image. This never downloads the wheel."""
    cm, _defaults = _load(kilix)
    if _playalong_installed(cm, pin['asset_id']):
        print('en_core_web_sm already verified; no bundle install needed.')
        return
    if archive is None:
        raise ValueError('the installation media did not supply the en_core_web_sm model')
    _install_from_image(kilix, archive, pin, 'en_core_web_sm', materialize_spacy)


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
    parser.add_argument('--paradee', type=Path,
                        help='the Paradee image archive (default: the copy the image installed, if any)')
    parser.add_argument('--en-core-web-sm', type=Path, dest='spacy',
                        help='the en_core_web_sm image archive (default: the copy the image installed, if any)')
    parser.add_argument('--build-demucs-archive', type=Path, metavar='OUTPUT',
                        help='write the Demucs image archive from --demucs-weights and exit')
    parser.add_argument('--demucs-weights', type=Path)
    parser.add_argument('--build-paradee-archive', type=Path, metavar='OUTPUT',
                        help='write the Paradee image archive from --paradee-onnx and --paradee-config and exit')
    parser.add_argument('--paradee-onnx', type=Path)
    parser.add_argument('--paradee-config', type=Path)
    parser.add_argument('--build-en-core-web-sm-archive', type=Path, dest='build_spacy_archive', metavar='OUTPUT',
                        help='write the en_core_web_sm image archive from --en-core-web-sm-wheel and exit')
    parser.add_argument('--en-core-web-sm-wheel', type=Path, dest='spacy_wheel')
    parser.add_argument('--install-paradee-runtime', action='store_true',
                        help='as root, copy a missing Paradee ONNX and config.json into the runtime directory')
    parser.add_argument('--paradee-runtime', type=Path, default=PARADEE_RUNTIME)
    parser.add_argument('--paradee-wheels', type=Path, default=PARADEE_WHEELHOUSE)
    parser.add_argument('--paradee-python', type=Path, default=PARADEE_PYTHON)
    parser.add_argument('--verify-paradee-wheels', type=Path, metavar='DIR',
                        help='check the hash-locked Paradee wheelhouse and exit')
    args = parser.parse_args(argv)
    basic_pin = _load_pin('basic-pitch-model.json')
    command_pin = _load_pin('command-model.json')
    demucs_pin = _load_pin('demucs-model.json')
    paradee_pin = _load_pin('paradee-model.json')
    spacy_pin = _load_pin('en-core-web-sm-model.json')
    playalong = _load_pin('playalong-models.json')
    validate_basic_pitch_pin(basic_pin)
    validate_command_pin(command_pin)
    validate_demucs_pin(demucs_pin)
    validate_paradee_pin(paradee_pin)
    validate_spacy_pin(spacy_pin)
    validate_playalong_inventory(playalong, basic_pin, demucs_pin)
    if args.verify_paradee_wheels is not None:
        verify_paradee_wheels(args.verify_paradee_wheels, load_wheel_lock())
        print('Paradee wheelhouse verified: ' + str(args.verify_paradee_wheels))
        return 0
    if args.build_demucs_archive is not None:
        if args.demucs_weights is None:
            parser.error('--build-demucs-archive needs --demucs-weights')
        build_demucs_archive(args.demucs_weights, args.build_demucs_archive, demucs_pin)
        return 0
    if args.build_paradee_archive is not None:
        if args.paradee_onnx is None or args.paradee_config is None:
            parser.error('--build-paradee-archive needs --paradee-onnx and --paradee-config')
        build_paradee_archive(args.paradee_onnx, args.paradee_config, args.build_paradee_archive, paradee_pin)
        return 0
    if args.build_spacy_archive is not None:
        if args.spacy_wheel is None:
            parser.error('--build-en-core-web-sm-archive needs --en-core-web-sm-wheel')
        build_spacy_archive(args.spacy_wheel, args.build_spacy_archive, spacy_pin)
        return 0
    if args.install_paradee_runtime:
        paradee_archive = resolve_paradee(args.paradee)
        if paradee_archive is None:
            raise ValueError('the installation media did not supply the Paradee model')
        stage_paradee_runtime(paradee_archive, paradee_pin, args.paradee_runtime)
        install_paradee_venv(args.paradee_wheels, load_wheel_lock(), args.paradee_python)
        print('Paradee runtime files verified: ' + str(args.paradee_runtime))
        return 0
    archive = resolve_basic_pitch(args.basic_pitch)
    verify_archive(archive, basic_pin)
    if args.demucs is not None:
        verify_demucs_archive(args.demucs, demucs_pin)
    if args.paradee is not None:
        verify_paradee_archive(args.paradee, paradee_pin)
    if args.spacy is not None:
        verify_spacy_archive(args.spacy, spacy_pin)
    if args.verify_only:
        return 0
    if args.kilix is None:
        parser.error('--kilix is required')
    # --offline is the fresh-install call: it downloads nothing. Basic Pitch,
    # Demucs, Paradee, en_core_web_sm and the command model come from the image.
    if args.offline and not archive.is_file():
        raise ValueError('the installation media did not supply the Basic Pitch model')
    declined = playalong_declined(args.kilix)
    if declined is None:
        install_basic_pitch(args.kilix, archive, basic_pin)
        install_demucs(args.kilix, resolve_demucs(args.demucs), demucs_pin, offline=args.offline)
    else:
        print("Playalong's default models skipped: " + declined)
    install_paradee(args.kilix, resolve_paradee(args.paradee), paradee_pin)
    install_spacy(args.kilix, resolve_spacy(args.spacy), spacy_pin)
    install_command_model(args.kilix, command_pin, args.command_cache)
    # The one large download comes last, after everything the image supplies.
    if declined is None:
        install_whisper_medium(args.kilix, playalong['assets'][WHISPER_MEDIUM]['manifest_digest'],
                               offline=args.offline)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
