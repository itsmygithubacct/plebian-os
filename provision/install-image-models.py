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

Paradee and en_core_web_sm ship in the image, and a fresh install that lacks
their archives is an error. A machine installed without them, such as one
installed from 0.2.2, gets them on an online upgrade. The root step
(--install-paradee-runtime) downloads the pinned files and builds the same
archives, checks each against its image pin, and only then puts it where the
image would have. The Paradee wheels are downloaded and checked against the
hash lock the same way. A failed download changes nothing, and the next
upgrade tries again. The desktop user's step then installs both from those
archives, as on a fresh install.

The espeakng-loader wheel in that interpreter bundles libespeak-ng
(GPL-3.0-or-later) and ships no licence file. The image puts the loader's MIT
text, its build notes and script, and the pinned espeak-ng 1.52.0 source under
/usr/local/share/doc/plebian-os/espeak-ng. The root step puts any of them that
are missing there too, so an upgraded machine has them. The loader texts come
from this checkout. An online run downloads the source and checks it against
espeak-ng-source.json. A failed download leaves it out, and the next upgrade
tries again.

PDF Conversion's page OCR models, PaddlePaddle's PP-OCRv6 small detector and
recogniser, are Apache-2.0 (owner determination, 2026-11-10) and ship in the
image. They install whether or not Playalong's models were declined. A fresh
install takes them from the image; an online run without the archives
downloads the same files from the pinned revisions.

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
import re
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
ESPEAK_SOURCE_PIN = 'espeak-ng-source.json'
ESPEAK_DOCS = Path('/usr/local/share/doc/plebian-os/espeak-ng')
ESPEAK_NOTICES = ('espeakng-loader-0.2.4-LICENSE', 'espeakng-loader-0.2.4-build.txt',
                  'espeakng-loader-0.2.4-build.sh')
SPACY_WHEEL ='en_core_web_sm-3.8.0-py3-none-any.whl'
SPACY_LICENCE = 'notices/LICENSE-mit.txt'
SPACY_SOURCES = 'notices/LICENSES_SOURCES.txt'
SPACY_FILES = (SPACY_WHEEL, SPACY_LICENCE, SPACY_SOURCES)
SPACY_WHEEL_URL = (
    'https://github.com/explosion/spacy-models/releases/download/'
    'en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl')
SPACY_LICENCE_SOURCE = Path(__file__).resolve().parent / 'bundles' / 'en-core-web-sm-3.8.0-LICENSE-mit.txt'
SPACY_SOURCES_SOURCE = Path(__file__).resolve().parent / 'bundles' / 'en-core-web-sm-3.8.0-LICENSES_SOURCES.txt'
# PDF Conversion's page OCR models: each asset id, the pinned revision's file
# URL prefix and the files page OCR reads. Neither repository has a LICENSE
# file, so the Apache-2.0 text is Debian's copy (owner determination 2026-11-10).
PP_OCR_MODELS = {
    'pp-ocrv6-small-det': (
        'https://huggingface.co/PaddlePaddle/PP-OCRv6_small_det_onnx/resolve/'
        '28fe5895c24fd108c19eb3e8479f4ab385fbfc62/', ('inference.onnx',)),
    'pp-ocrv6-small-rec': (
        'https://huggingface.co/PaddlePaddle/PP-OCRv6_small_rec_onnx/resolve/'
        'b8f84f0b80c529de40b4fbb3544b84fa7233a513/', ('inference.onnx', 'inference.yml')),
}
PP_OCR_LICENCE = 'notices/LICENSE-apache-2.0.txt'
PP_OCR_LICENCE_SOURCE = Path(__file__).resolve().parent / 'bundles' / 'pp-ocrv6-small-LICENSE-apache-2.0.txt'
# The Neuronte faces (install-neuronte.py), for an updater that predates them.
NEURONTE_INSTALLER = Path(__file__).resolve().parent / 'install-neuronte.py'
NEURONTE_MANIFEST = Path(__file__).resolve().parent / 'neuronte-payload.json'
NEURONTE_REPO = 'https://github.com/itsmygithubacct/neuronte.git'
SELECTED_CLOSURE = Path('/etc/pleb/closure.env')
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


def pp_ocr_files(asset_id):
    """The members of one page OCR archive, in archive order."""
    if asset_id not in PP_OCR_MODELS:
        raise ValueError(f'not a page OCR model: {asset_id!r}')
    return PP_OCR_MODELS[asset_id][1] + (PP_OCR_LICENCE,)


def validate_pp_ocr_pin(pin, asset_id):
    members = pp_ocr_files(asset_id)
    base, models = PP_OCR_MODELS[asset_id]
    _validate_archive_pin(
        pin, label=asset_id, schema='plebian-os.pp-ocrv6-small-archive/v1',
        asset_id=asset_id, filename=asset_id + '.tar',
        members=members, limit=32 * 1024 * 1024)
    for name in models:
        if pin['files'][name].get('url') != base + name:
            raise ValueError(f'invalid {asset_id} pin: the {name} URL is not the pinned file')


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


def verify_pp_ocr_archive(path, pin):
    """Check one page OCR archive, PaddlePaddle's unchanged files and the Apache-2.0 text."""
    validate_pp_ocr_pin(pin, pin.get('asset_id'))
    _verify_image_archive(path, pin, pin['asset_id'], 'r:')


def materialize_pp_ocr(path, pin, destination):
    verify_pp_ocr_archive(path, pin)
    _materialize_image_archive(path, pin, destination, pin['asset_id'], 'r:')


def build_pp_ocr_archive(sources, output, pin):
    """Write one page OCR image archive from the pinned files in sources and the Apache-2.0 text.

    sources holds each upstream file at its member path, as the build fetched it.
    """
    asset_id = pin.get('asset_id')
    validate_pp_ocr_pin(pin, asset_id)
    members = [
        (name, _checked_input(pin, name, Path(sources) / name, asset_id))
        for name in PP_OCR_MODELS[asset_id][1]
    ]
    members.append((PP_OCR_LICENCE, _checked_input(pin, PP_OCR_LICENCE, PP_OCR_LICENCE_SOURCE, asset_id)))
    _build_ustar(members, output, lambda path: verify_pp_ocr_archive(path, pin))
    print(asset_id + ' image archive written: ' + str(output))


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


def refuse_runtime_symlinks(root):
    """Refuse a runtime that is a symlink, or has one in place of any of its directories or files.

    Root writes and chmods inside the runtime, and a symlink there would send
    those writes and modes outside it.
    """
    root = Path(root)
    paths = {root}
    for name in PARADEE_FILES:
        parts = Path(name).parts
        paths.update(root.joinpath(*parts[:index]) for index in range(1, len(parts) + 1))
    for path in sorted(paths):
        if path.is_symlink():
            raise ValueError('Paradee runtime path is a symlink: ' + str(path))


def stage_paradee_runtime(archive, pin, root):
    """Copy a missing ONNX, config.json, or Apache-2.0 text. Root calls this."""
    verify_paradee_archive(archive, pin)
    root = Path(root)
    refuse_runtime_symlinks(root)
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


def _download_pinned(url, size, target):
    """Write exactly the pinned number of bytes from an https URL. The caller checks the digest."""
    if not isinstance(url, str) or not url.startswith('https://'):
        raise ValueError('refusing a download that is not https: ' + str(url))
    import urllib.request
    with urllib.request.urlopen(url, timeout=120) as source, Path(target).open('xb') as output:
        remaining = size
        while remaining:
            block = source.read(min(1024 * 1024, remaining))
            if not block:
                raise ValueError('incomplete download: ' + url)
            output.write(block)
            remaining -= len(block)
        if source.read(1):
            raise ValueError('download exceeds its pinned size: ' + url)


def _place_shared_archive(built, pin, verify):
    """Put a checked archive where the image would have, without replacing another copy."""
    SHARED_BASIC_PITCH.mkdir(parents=True, exist_ok=True)
    target = SHARED_BASIC_PITCH / pin['filename']
    with tempfile.TemporaryDirectory(prefix='.plebian-image-archive-', dir=SHARED_BASIC_PITCH) as tmp:
        staged = Path(tmp) / pin['filename']
        staged.write_bytes(Path(built).read_bytes())
        verify(staged, pin)
        staged.chmod(0o644)
        try:
            os.link(staged, target)
        except FileExistsError:
            verify(target, pin)
    return target


def fetch_paradee_media(paradee_pin, spacy_pin, lock, scratch, *, paradee, spacy, wheels):
    """Download what this machine's image did not supply; nothing is placed unless all of it checks.

    Each archive is built from its pinned upstream files by the image's own
    builder, which checks every input and then the archive against its pin.
    Returns the Paradee archive and the wheelhouse to install from.
    """
    scratch = Path(scratch)
    built = []
    # Upstream files already downloaded and checked here, by size and digest.
    checked = {}
    if paradee:
        for name in (PARADEE_ONNX, PARADEE_CONFIG):
            item = paradee_pin['files'][name]
            _download_pinned(item['url'], item['bytes'], scratch / Path(name).name)
        output = scratch / paradee_pin['filename']
        build_paradee_archive(scratch / Path(PARADEE_ONNX).name, scratch / PARADEE_CONFIG,
                              output, paradee_pin)
        built.append((output, paradee_pin, verify_paradee_archive))
    if spacy:
        item = spacy_pin['files'][SPACY_WHEEL]
        _download_pinned(item['url'], item['bytes'], scratch / SPACY_WHEEL)
        output = scratch / spacy_pin['filename']
        build_spacy_archive(scratch / SPACY_WHEEL, output, spacy_pin)
        built.append((output, spacy_pin, verify_spacy_archive))
        # The builder checked the wheel, so the wheelhouse can reuse it.
        checked[(item['bytes'], item['sha256'])] = scratch / SPACY_WHEEL
    wheelhouse = None
    if wheels:
        wheelhouse = scratch / 'paradee-wheels'
        wheelhouse.mkdir()
        bundles = Path(__file__).resolve().parent / 'bundles'
        for item in lock['wheels']:
            target = wheelhouse / item['filename']
            if 'bundle' in item:
                target.write_bytes((bundles / item['bundle']).read_bytes())
            elif (item['bytes'], item['sha256']) in checked:
                target.write_bytes(checked[(item['bytes'], item['sha256'])].read_bytes())
            else:
                _download_pinned(item['url'], item['bytes'], target)
        verify_paradee_wheels(wheelhouse, lock)
    placed = {pin['asset_id']: _place_shared_archive(path, pin, verify) for path, pin, verify in built}
    return placed.get(paradee_pin['asset_id']), wheelhouse


def load_espeak_pin(path=None):
    path = Path(__file__).with_name(ESPEAK_SOURCE_PIN) if path is None else Path(path)
    pin = json.loads(path.read_text())
    filename = pin.get('filename')
    if (pin.get('schema') != 'plebian-os.espeak-ng-source/v1'
            or not isinstance(filename, str) or not filename or '/' in filename
            or filename.startswith('.')
            or not isinstance(pin.get('url'), str) or not pin['url'].startswith('https://')
            or type(pin.get('bytes')) is not int or pin['bytes'] <= 0
            or not _hex64(pin.get('sha256')) or not _hex64(pin.get('loader_licence_sha256'))):
        raise ValueError('invalid espeak-ng source pin')
    return pin


def _check_bytes(path, size, digest, label):
    with _open_regular(path) as stream:
        data = stream.read(size + 1) if size is not None else stream.read()
    if (size is not None and len(data) != size) or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(label + ' size or checksum mismatch')


def _place_doc(source, target, check):
    """Put a checked copy of source at target, 0644, without replacing a file already there."""
    with tempfile.TemporaryDirectory(prefix='.plebian-espeak-', dir=target.parent) as tmp:
        staged = Path(tmp) / target.name
        staged.write_bytes(Path(source).read_bytes())
        check(staged)
        staged.chmod(0o644)
        try:
            os.link(staged, target)
        except FileExistsError:
            pass


def install_espeak_notices(docs, pin, scratch, *, offline):
    """The espeak-ng source and the espeakng-loader texts, where the image puts them.

    Missing files only; what is there is left alone. The loader texts come
    from this checkout, the licence checked against the pin. An online run
    downloads a missing source tarball and checks it first. False when that
    download failed; nothing else is changed by a failure.
    """
    docs = Path(docs)
    if docs.is_symlink():
        raise ValueError('the espeak-ng notice directory is a symlink')
    docs.mkdir(parents=True, exist_ok=True)
    _chmod_owned(docs, 0o755)
    bundles = Path(__file__).resolve().parent / 'bundles'
    for name in ESPEAK_NOTICES:
        target = docs / name
        if target.exists() or target.is_symlink():
            continue
        if name.endswith('-LICENSE'):
            check = lambda path: _check_bytes(path, None, pin['loader_licence_sha256'],
                                              'espeakng-loader licence')
        else:
            check = lambda path: None
        _place_doc(bundles / name, target, check)
    source = docs / pin['filename']
    if source.exists() or source.is_symlink():
        return True
    if offline:
        print('The espeak-ng source is not installed: the installation media did not supply it.',
              file=sys.stderr)
        return False
    download = Path(scratch) / pin['filename']
    try:
        _download_pinned(pin['url'], pin['bytes'], download)
        check = lambda path: _check_bytes(path, pin['bytes'], pin['sha256'], 'espeak-ng source')
        check(download)
        _place_doc(download, source, check)
    except (OSError, ValueError) as error:
        print(f'The espeak-ng source was not installed ({error}); the next upgrade tries again.',
              file=sys.stderr)
        return False
    print('espeak-ng source installed: ' + str(source))
    return True


def _chmod_owned(path, mode):
    """chmod one path the step created, never through a symlink."""
    if not path.is_symlink() and path.exists():
        os.chmod(path, mode)


def publish_paradee_runtime(runtime):
    """The staged runtime, readable by the desktop user: its directories 0755 and its files 0644.

    Only the runtime's own files and their directories are touched, and a
    symlink at any of them is refused first.
    """
    runtime = Path(runtime)
    refuse_runtime_symlinks(runtime)
    for directory in sorted({runtime} | {(runtime / name).parent for name in PARADEE_FILES}):
        _chmod_owned(directory, 0o755)
    for name in PARADEE_FILES:
        _chmod_owned(runtime / name, 0o644)


def publish_paradee_venv(venv):
    """The interpreter tree, readable and runnable by the desktop user.

    Directories become 0755. Files become 0755 when already executable and
    0644 otherwise. Only a directory holding pyvenv.cfg is walked, and the walk
    does not follow symlinks.
    """
    venv = Path(venv)
    if venv.is_symlink() or not (venv / 'pyvenv.cfg').is_file():
        return
    for current, _directories, files in os.walk(venv):
        os.chmod(current, 0o755)
        for name in files:
            target = Path(current) / name
            if target.is_symlink() or not target.is_file():
                continue
            os.chmod(target, 0o755 if target.stat().st_mode & 0o111 else 0o644)


def install_paradee_runtime(paradee_pin, spacy_pin, *, paradee=None, spacy=None, runtime=None,
                            wheelhouse=None, python=None, docs=None, espeak_pin=None, offline):
    """The root half of Paradee: the runtime files, the en_core_web_sm archive, and /usr/lib/kilix/pd.

    A fresh install (offline) takes all of it from the image. An online run on
    a machine without the image archives or the wheelhouse downloads them first,
    see fetch_paradee_media. False when that download failed and nothing changed.

    sudo keeps the caller's umask, and a 0077 umask would leave a root-only
    runtime that the desktop user cannot read. So this step runs under 0022.
    Afterwards the runtime, the interpreter and /usr/lib/kilix are made
    readable. That also repairs a runtime an earlier run left root-only. A
    runtime that is a symlink, or holds one in place of its own directories
    or files, is refused before anything is downloaded, written or chmodded.
    """
    previous_umask = os.umask(0o022)
    try:
        runtime = PARADEE_RUNTIME if runtime is None else Path(runtime)
        wheelhouse = PARADEE_WHEELHOUSE if wheelhouse is None else Path(wheelhouse)
        python = PARADEE_PYTHON if python is None else Path(python)
        docs = ESPEAK_DOCS if docs is None else Path(docs)
        espeak_pin = load_espeak_pin() if espeak_pin is None else espeak_pin
        # Before any download: a symlinked runtime is refused, not filled.
        refuse_runtime_symlinks(runtime)
        lock = load_wheel_lock()
        archive = resolve_paradee(paradee)
        need_spacy = resolve_spacy(spacy) is None
        need_wheels = not python.is_file() and not wheelhouse.is_dir()
        with tempfile.TemporaryDirectory(prefix='plebian-paradee-download-') as scratch:
            if offline or (archive is not None and not need_spacy and not need_wheels):
                if archive is None:
                    raise ValueError('the installation media did not supply the Paradee model')
            else:
                try:
                    fetched, downloaded = fetch_paradee_media(
                        paradee_pin, spacy_pin, lock, scratch,
                        paradee=archive is None, spacy=need_spacy, wheels=need_wheels)
                except (OSError, ValueError) as error:
                    print(f'Paradee and en_core_web_sm were not installed ({error}); '
                          'the next upgrade tries again.', file=sys.stderr)
                    return False
                archive = fetched or archive
                wheelhouse = downloaded or wheelhouse
            stage_paradee_runtime(archive, paradee_pin, runtime)
            install_paradee_venv(wheelhouse, lock, python)
            # libespeak-ng is now on the machine; so are its licence and source.
            install_espeak_notices(docs, espeak_pin, scratch, offline=offline)
        publish_paradee_runtime(runtime)
        if len(python.parents) >= 2:
            publish_paradee_venv(python.parents[1])
        if runtime.parent == PARADEE_RUNTIME.parent:
            _chmod_owned(runtime.parent, 0o755)
        print('Paradee runtime files verified: ' + str(runtime))
        return True
    finally:
        os.umask(previous_umask)


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


def resolve_pp_ocr(explicit, asset_id):
    return _resolve_shared_archive(explicit, asset_id + '.tar')


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


def fetch_default(kilix, asset_id, label, manifest_digest, pinned_by='the Playalong inventory'):
    """Download one Playalong default or page OCR model from its pinned source; False if that failed.

    The catalogued asset must be the one this release pinned, and the licence
    gate is the same as the image's: the standard distribution policy or
    nothing. Only the download may fail without stopping the caller.
    """
    cm, defaults = _load(kilix)
    api, lic, spec, records, store = _catalog_spec(cm, asset_id)
    if spec.asset_id != asset_id or spec.manifest_digest != manifest_digest:
        raise ValueError(label + ' catalog differs from ' + pinned_by)
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


def _skip_without_archive(label):
    """An online run whose root step could not download the archive: try again next upgrade."""
    print(f'{label} was not installed: this machine has no {label} archive and the download '
          'before this step did not supply one; the next upgrade tries again.', file=sys.stderr)


def install_paradee(kilix, archive, pin, *, offline):
    """Paradee from the image archive. The runtime files are checked and never rewritten here.

    This never downloads. On an upgrade the archive is the one the root step
    built from the pinned files (see fetch_paradee_media).
    """
    if archive is None and not offline:
        try:
            verify_paradee_runtime(pin)
        except ValueError as error:
            print(f'Paradee was not installed ({error}); the next upgrade tries again.',
                  file=sys.stderr)
            return
    else:
        verify_paradee_runtime(pin)
    cm, _defaults = _load(kilix)
    if _playalong_installed(cm, pin['asset_id']):
        print('Paradee already verified; no bundle install needed.')
        return
    if archive is None:
        if offline:
            raise ValueError('the installation media did not supply the Paradee model')
        _skip_without_archive('Paradee')
        return
    _install_from_image(kilix, archive, pin, 'Paradee', materialize_paradee)


def install_spacy(kilix, archive, pin, *, offline):
    """en_core_web_sm from the image archive. This never downloads the wheel."""
    cm, _defaults = _load(kilix)
    if _playalong_installed(cm, pin['asset_id']):
        print('en_core_web_sm already verified; no bundle install needed.')
        return
    if archive is None:
        if offline:
            raise ValueError('the installation media did not supply the en_core_web_sm model')
        _skip_without_archive('en_core_web_sm')
        return
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


def install_pp_ocr(kilix, archive, pin, *, offline):
    """A page OCR model from the image archive when this machine has it, else from its revision.

    PDF Conversion reads it from the content root and never downloads it.
    """
    asset_id = pin['asset_id']
    if archive is not None:
        _install_from_image(kilix, archive, pin, asset_id, materialize_pp_ocr)
        return
    cm, _defaults = _load(kilix)
    if _playalong_installed(cm, asset_id):
        print(asset_id + ' already verified; no download needed.')
    elif offline:
        print(asset_id + ': the installation media did not supply its archive; '
              'the first online upgrade downloads it.')
    else:
        fetch_default(kilix, asset_id, asset_id, pin['manifest_digest'], pinned_by='its image pin')


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
    for asset_id in PP_OCR_MODELS:
        parser.add_argument('--' + asset_id, type=Path, dest=asset_id.replace('-', '_'),
                            help=f'the {asset_id} image archive (default: the copy the image installed, if any)')
    parser.add_argument('--build-pp-ocr-archive', nargs=2, metavar=('ASSET_ID', 'OUTPUT'),
                        help='write one page OCR image archive from --pp-ocr-files and exit')
    parser.add_argument('--pp-ocr-files', type=Path, metavar='DIR',
                        help='the pinned upstream files of the page OCR model, at their member paths')
    parser.add_argument('--install-paradee-runtime', action='store_true',
                        help='as root, copy a missing Paradee ONNX and config.json into the runtime directory; '
                             'without --offline, first download what the image did not supply')
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
    pp_ocr_pins = {asset_id: _load_pin(asset_id + '-model.json') for asset_id in PP_OCR_MODELS}
    validate_basic_pitch_pin(basic_pin)
    validate_command_pin(command_pin)
    validate_demucs_pin(demucs_pin)
    validate_paradee_pin(paradee_pin)
    validate_spacy_pin(spacy_pin)
    for asset_id, pin in pp_ocr_pins.items():
        validate_pp_ocr_pin(pin, asset_id)
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
    if args.build_pp_ocr_archive is not None:
        asset_id, output = args.build_pp_ocr_archive[0], Path(args.build_pp_ocr_archive[1])
        if asset_id not in pp_ocr_pins:
            parser.error('--build-pp-ocr-archive names no page OCR model: ' + asset_id)
        if args.pp_ocr_files is None:
            parser.error('--build-pp-ocr-archive needs --pp-ocr-files')
        build_pp_ocr_archive(args.pp_ocr_files, output, pp_ocr_pins[asset_id])
        return 0
    if args.install_paradee_runtime:
        install_paradee_runtime(
            paradee_pin, spacy_pin, paradee=args.paradee, spacy=args.spacy,
            runtime=args.paradee_runtime, wheelhouse=args.paradee_wheels,
            python=args.paradee_python, offline=args.offline)
        return 0
    archive = resolve_basic_pitch(args.basic_pitch)
    verify_archive(archive, basic_pin)
    if args.demucs is not None:
        verify_demucs_archive(args.demucs, demucs_pin)
    if args.paradee is not None:
        verify_paradee_archive(args.paradee, paradee_pin)
    if args.spacy is not None:
        verify_spacy_archive(args.spacy, spacy_pin)
    pp_ocr_archives = {asset_id: getattr(args, asset_id.replace('-', '_')) for asset_id in PP_OCR_MODELS}
    for asset_id, path in pp_ocr_archives.items():
        if path is not None:
            verify_pp_ocr_archive(path, pp_ocr_pins[asset_id])
    if args.verify_only:
        return 0
    if args.kilix is None:
        parser.error('--kilix is required')
    # --offline is the fresh-install call: it downloads nothing. Basic Pitch,
    # Demucs, Paradee, en_core_web_sm, page OCR and the command model come from the image.
    if args.offline and not archive.is_file():
        raise ValueError('the installation media did not supply the Basic Pitch model')
    declined = playalong_declined(args.kilix)
    if declined is None:
        install_basic_pitch(args.kilix, archive, basic_pin)
        install_demucs(args.kilix, resolve_demucs(args.demucs), demucs_pin, offline=args.offline)
    else:
        print("Playalong's default models skipped: " + declined)
    install_paradee(args.kilix, resolve_paradee(args.paradee), paradee_pin, offline=args.offline)
    install_spacy(args.kilix, resolve_spacy(args.spacy), spacy_pin, offline=args.offline)
    install_command_model(args.kilix, command_pin, args.command_cache)
    for asset_id, pin in pp_ocr_pins.items():
        install_pp_ocr(args.kilix, resolve_pp_ocr(pp_ocr_archives[asset_id], asset_id), pin,
                       offline=args.offline)
    # The one large download comes last, after everything the image supplies.
    if declined is None:
        install_whisper_medium(args.kilix, playalong['assets'][WHISPER_MEDIUM]['manifest_digest'],
                               offline=args.offline)
    if not args.offline:
        return install_neuronte_for_an_older_updater()
    return 0


def install_neuronte_for_an_older_updater(closure=None, environ=None, run=subprocess.run):
    """Install the selected Neuronte pin when the updater running this step
    does not know about Neuronte.

    An RC8 machine moves to RC9 with `pleb update --to 0.2.3 --release-tag ...`,
    which runs the RC8 updater. That process deploys the RC9 updater but keeps
    executing its own steps, and it has none for Neuronte; it does run this
    file from the RC9 checkout, as the desktop user. An updater that installs
    Neuronte itself passes NEURONTE_REF, and then this does nothing; so does a
    closure that pins no Neuronte. Otherwise the pin is read from the selected
    closure and install-neuronte.py runs exactly as the RC9 updater runs it.
    """
    environ = os.environ if environ is None else environ
    if 'NEURONTE_REF' in environ:
        return 0
    closure = SELECTED_CLOSURE if closure is None else Path(closure)
    try:
        lines = closure.read_text().splitlines()
    except FileNotFoundError:
        return 0
    values = {}
    for line in lines:
        key, sep, value = line.partition('=')
        if sep and key in ('NEURONTE_REF', 'NEURONTE_REPO'):
            values[key] = value.strip().strip("'\"")
    ref = values.get('NEURONTE_REF', '')
    if not ref:
        return 0
    if not re.fullmatch(r'[0-9a-f]{40}', ref) or values.get('NEURONTE_REPO') != NEURONTE_REPO:
        raise ValueError('the selected closure names an invalid Neuronte pin')
    sources = Path(environ.get('GPU_TERMINAL_SOURCE_HOME')
                   or Path(environ.get('HOME', '~')).expanduser() / '.local/gpu_terminal/sources')
    print('Neuronte %s: installing the selected pin for an updater that predates it' % ref[:12])
    result = run([sys.executable, str(NEURONTE_INSTALLER), 'install',
                  '--manifest', str(NEURONTE_MANIFEST), '--ref', ref, '--repo', NEURONTE_REPO,
                  '--destination', str(sources / 'neuronte'),
                  '--archive', str(SHARED_BASIC_PITCH / ('neuronte-%s.tar.xz' % ref)),
                  '--fetch-failure', 'warn'])
    if result.returncode != 0:
        raise ValueError('Neuronte installation failed (see above)')
    desktop = Path(environ.get('KILIX95_DIR') or sources / 'kilix-desktops/kilix-95') / 'main.py'
    if desktop.is_file():
        result = run([sys.executable, str(desktop), '--prepare-cache'])
        if result.returncode != 0:
            print('Kilix 95 cache preparation failed; the desktop will retry at launch', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
