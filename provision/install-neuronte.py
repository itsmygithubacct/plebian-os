#!/usr/bin/python3
"""Install the pinned Neuronte faces the Kilix 95 desktop reads.

Kilix 95 draws its desktop faces and flame with Neuronte when it finds a
Neuronte tree at NEURONTE_HOME or, by default, at
$GPU_TERMINAL_SOURCE_HOME/neuronte (owner decision, 2026-11-12: Neuronte
lives under ~/.local on an installed system, like the other sources). Without
one it keeps the DejaVu faces and the drawn flame.

The release pins one public Neuronte commit, NEURONTE_REF, and this checkout
carries neuronte-payload.json: the git blob id, mode and size of every file of
that commit the desktop opens, plus the C source, Makefile and notices. An
archive is accepted only when its members are exactly those paths and each
file's blob id matches, so the same check serves the image's archive and one
fetched from GitHub. The archive's own digest is not pinned: its bytes depend
on the git and xz that wrote it.

  write-manifest  Write neuronte-payload.json from a repository holding the
                  commit (release maintenance; the selection rule is below).
  fetch-archive   Fetch the pinned commit without blobs, check out only the
                  pinned paths, and write a tar of them (ISO build, upgrade).
  verify          Check an archive against the manifest.
  install         As the desktop user: verify, build build/libneuronte.so
                  in a staging tree, load it and open two weight files, write
                  the install record and swap the tree in.

install refuses a tree it did not write, or one whose files differ from its
record, the way install-kilix-llm.sh refuses a dirty or foreign checkout. A
NEURONTE_HOME that names the destination is the user's own and is left alone.
With --fetch-failure=warn (the update), a failed download leaves the existing
tree as it is and exits 0, and the next update tries again; any other failure
is an error.
"""
import argparse
import ctypes
import hashlib
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

SCHEMA = 'plebian.neuronte-payload/v1'
RECORD = '.plebian-os-neuronte.json'
RECORD_SCHEMA = 'plebian.neuronte-install/v1'
LIBRARY = 'build/libneuronte.so'
CANONICAL_REPO = 'https://github.com/itsmygithubacct/neuronte.git'
MAX_FILES = 512
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
# Two files the installed library must open before the tree is used.
PROBES = ('weights/neuronte-ui12-v0.nrt', 'weights/neuronte-flame-v0.nrt')
# Kilix 95 neuronte_face.py / neuronte_flame.py (af691fe, unchanged at
# 1e59c1e) open these. Small faces
# are binary files per em up to 32 with a header in font/ui-{em}[-italic].txt;
# from 33 the scalable ui-large file is used and no header is read.
SELECTION = (
    re.compile(r'weights/neuronte-ui([1-9]|[12][0-9]|3[0-2])(-italic)?-v0\.nrt'),
    re.compile(r'weights/neuronte-ui-large-v0\.nrt'),
    re.compile(r'weights/neuronte-flame-v0\.nrt'),
    re.compile(r'font/ui-([1-9]|[12][0-9]|3[0-2])(-italic)?\.txt'),
    re.compile(r'train/glyphs\.py'),
    re.compile(r'(src|include)/[^/]+\.[ch]'),
    re.compile(r'Makefile|LICENSE|THIRD_PARTY_NOTICES\.md|PROVENANCE\.md|README\.md'),
)
REQUIRED = {'Makefile', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'train/glyphs.py',
            'include/neuronte.h', *PROBES}


class Refusal(Exception):
    """The destination holds something this installer must not replace."""


class FetchUnavailable(Exception):
    """The pinned commit could not be downloaded."""


def blob_id(data):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def git(*args, cwd=None, check=True):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_ASKPASS='/bin/false',
               LC_ALL='C')
    env.pop('GIT_DIR', None)
    env.pop('GIT_WORK_TREE', None)
    return subprocess.run(['git', '-c', 'advice.detachedHead=false', *args], cwd=cwd,
                          env=env, check=check, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, timeout=1800)


def selected(path):
    return any(rule.fullmatch(path) for rule in SELECTION)


def load_manifest(path, ref):
    manifest = json.loads(Path(path).read_text())
    if manifest.get('schema') != SCHEMA:
        raise ValueError('unsupported Neuronte payload manifest')
    if not re.fullmatch(r'[0-9a-f]{40}', ref or ''):
        raise ValueError('NEURONTE_REF must be a full 40-character commit')
    if manifest.get('commit') != ref:
        raise ValueError('the payload manifest pins %s, not NEURONTE_REF %s'
                         % (manifest.get('commit'), ref))
    files = manifest.get('files')
    if not isinstance(files, dict) or not REQUIRED <= files.keys() or len(files) > MAX_FILES:
        raise ValueError('the payload manifest is incomplete')
    for name, entry in files.items():
        safe_path(name)
        if (not isinstance(entry, dict) or set(entry) != {'blob', 'mode', 'bytes'}
                or not re.fullmatch(r'[0-9a-f]{40}', str(entry['blob']))
                or entry['mode'] not in ('100644', '100755')
                or not isinstance(entry['bytes'], int)
                or not 0 <= entry['bytes'] <= MAX_FILE_BYTES):
            raise ValueError('invalid payload manifest entry: ' + name)
    if name_is_reserved(files):
        raise ValueError('the payload manifest names an installer-owned path')
    return manifest


def name_is_reserved(files):
    return any(name == RECORD or name == LIBRARY or name.startswith('build/') for name in files)


def safe_path(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or str(path) != name
            or any(part in ('', '.', '..') for part in path.parts)):
        raise ValueError('unsafe path: ' + repr(name))
    return path


def manifest_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ── write-manifest ─────────────────────────────────────────────────────────
def write_manifest(repo_dir, commit, out, repository):
    resolved = git('rev-parse', '--verify', commit + '^{commit}', cwd=repo_dir).stdout.strip()
    if resolved != commit:
        raise ValueError('commit is not a full commit id: ' + commit)
    files = {}
    for line in git('ls-tree', '-r', '-l', '-z', commit, cwd=repo_dir).stdout.split('\0'):
        if not line:
            continue
        meta, name = line.split('\t', 1)
        mode, kind, blob, size = meta.split()
        if kind == 'blob' and selected(name):
            if mode not in ('100644', '100755'):
                raise ValueError('selected path is not a regular file: ' + name)
            files[name] = {'blob': blob, 'mode': mode, 'bytes': int(size)}
    missing = REQUIRED - files.keys()
    if missing:
        raise ValueError('commit lacks required paths: ' + ', '.join(sorted(missing)))
    tree = git('rev-parse', commit + '^{tree}', cwd=repo_dir).stdout.strip()
    manifest = {
        'schema': SCHEMA,
        'repository': repository,
        'commit': commit,
        'tree': tree,
        'reader': 'Kilix 95 neuronte_face.py and neuronte_flame.py (af691fe; unchanged at 1e59c1e)',
        'license': 'MIT; LICENSE and THIRD_PARTY_NOTICES.md are carried with the files',
        'files': dict(sorted(files.items())),
    }
    Path(out).write_text(json.dumps(manifest, indent=1) + '\n')
    total = sum(entry['bytes'] for entry in files.values())
    print('Neuronte payload manifest: %d files, %d bytes, commit %s' % (len(files), total, commit))


# ── fetch-archive ──────────────────────────────────────────────────────────
def fetch_archive(repository, ref, manifest_path, out, compress=False):
    manifest = load_manifest(manifest_path, ref)
    out = Path(out)
    with tempfile.TemporaryDirectory(prefix='neuronte-fetch-') as temporary:
        repo = Path(temporary) / 'repo'
        git('init', '-q', str(repo))
        git('remote', 'add', 'origin', repository, cwd=repo)
        git('config', 'remote.origin.promisor', 'true', cwd=repo)
        git('config', 'remote.origin.partialclonefilter', 'blob:none', cwd=repo)
        try:
            git('fetch', '-q', '--depth=1', '--filter=blob:none', '--no-tags',
                'origin', ref, cwd=repo)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            detail = getattr(error, 'stderr', '') or ''
            raise FetchUnavailable('could not fetch Neuronte %s from %s: %s'
                                   % (ref, repository, detail.strip().splitlines()[-1:]))
        actual = git('rev-parse', '--verify', 'FETCH_HEAD^{commit}', cwd=repo).stdout.strip()
        if actual != ref:
            raise ValueError('fetched Neuronte commit %s, expected %s' % (actual, ref))
        names = sorted(manifest['files'])
        (repo / '.git' / 'info').mkdir(exist_ok=True)
        git('sparse-checkout', 'set', '--no-cone', *('/' + name for name in names), cwd=repo)
        try:
            # The checkout fetches exactly the pinned blobs in one batch.
            git('checkout', '-q', '--detach', actual, cwd=repo)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            detail = getattr(error, 'stderr', '') or ''
            raise FetchUnavailable('could not download the pinned Neuronte files: %s'
                                   % detail.strip().splitlines()[-1:])
        tar_path = Path(temporary) / 'payload.tar'
        with tar_path.open('wb') as stream:
            subprocess.run(['git', 'archive', '--format=tar', actual, '--', *names],
                           cwd=repo, check=True, stdout=stream, timeout=600)
        data = tar_path.read_bytes()
    if compress:
        data = lzma.compress(data, preset=6)
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name('.' + out.name + '.partial')
    partial.write_bytes(data)
    verify_archive(partial, manifest)
    os.replace(partial, out)
    out.chmod(0o644)


# ── verify ─────────────────────────────────────────────────────────────────
def open_tar(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('archive is missing or not a regular file: %s' % path)
    if path.stat().st_size > MAX_TOTAL_BYTES:
        raise ValueError('archive is too large')
    return tarfile.open(path, 'r:*')


def verify_archive(archive, manifest, extract_to=None):
    """Return {name: bytes} checked against the manifest; extract if asked."""
    files = manifest['files']
    seen = {}
    total = 0
    with open_tar(archive) as bundle:
        for member in bundle:
            if member.isdir():
                name = member.name.rstrip('/')
                safe_path(name)
                if not any(entry.startswith(name + '/') for entry in files):
                    raise ValueError('unexpected directory in the Neuronte archive: ' + name)
                continue
            if member.name == 'pax_global_header' or member.type in (tarfile.XGLTYPE,):
                continue
            if not member.isfile():
                raise ValueError('non-regular member in the Neuronte archive: ' + member.name)
            safe_path(member.name)
            if member.name in seen:
                raise ValueError('duplicate member in the Neuronte archive: ' + member.name)
            entry = files.get(member.name)
            if entry is None:
                raise ValueError('the Neuronte archive has an unpinned file: ' + member.name)
            if member.size != entry['bytes']:
                raise ValueError('size mismatch for ' + member.name)
            total += member.size
            if total > MAX_TOTAL_BYTES or len(seen) >= MAX_FILES:
                raise ValueError('the Neuronte archive exceeds its limits')
            data = bundle.extractfile(member).read()
            if blob_id(data) != entry['blob']:
                raise ValueError('content mismatch for ' + member.name)
            seen[member.name] = True
            if extract_to is not None:
                target = Path(extract_to).joinpath(*PurePosixPath(member.name).parts)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                with target.open('xb') as stream:
                    stream.write(data)
                target.chmod(0o755 if entry['mode'] == '100755' else 0o644)
    missing = files.keys() - seen.keys()
    if missing:
        raise ValueError('the Neuronte archive lacks %d pinned file(s), e.g. %s'
                         % (len(missing), sorted(missing)[0]))
    return total


# ── install ────────────────────────────────────────────────────────────────
def file_blob(path):
    return blob_id(Path(path).read_bytes())


def inspect(destination, manifest):
    """('absent'|'current'|'other', record) or raise Refusal."""
    if destination.is_symlink():
        raise Refusal('%s is a symlink; refusing to replace it' % destination)
    if not destination.exists():
        return 'absent', None
    if not destination.is_dir():
        raise Refusal('%s exists and is not a directory' % destination)
    record_path = destination / RECORD
    if not record_path.is_file() or record_path.is_symlink():
        raise Refusal('%s was not installed by Plebian-OS (no %s); move it aside, or set '
                      'NEURONTE_HOME to it to keep using it' % (destination, RECORD))
    try:
        record = json.loads(record_path.read_text())
        recorded = record['files']
        library_sha = record['library_sha256']
        if record.get('schema') != RECORD_SCHEMA or not isinstance(recorded, dict):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise Refusal('the Neuronte install record in %s cannot be read' % destination)
    changed = []
    present = set()
    for root, dirs, names in os.walk(destination):
        for name in dirs + names:
            full = Path(root) / name
            rel = full.relative_to(destination).as_posix()
            if full.is_symlink():
                changed.append(rel)
            elif full.is_file():
                present.add(rel)
    for rel in sorted(present):
        if rel == RECORD:
            continue
        if rel == LIBRARY:
            if hashlib.sha256((destination / rel).read_bytes()).hexdigest() != library_sha:
                changed.append(rel)
        elif rel not in recorded or file_blob(destination / rel) != recorded[rel]:
            changed.append(rel)
    for rel in recorded:
        if rel not in present:
            changed.append(rel)
    if LIBRARY not in present:
        changed.append(LIBRARY)
    if changed:
        raise Refusal('%s has local changes (%s%s); refusing to replace them'
                      % (destination, ', '.join(sorted(set(changed))[:5]),
                         ', ...' if len(set(changed)) > 5 else ''))
    if (record.get('commit') == manifest['commit']
            and recorded == {name: entry['blob'] for name, entry in manifest['files'].items()}):
        return 'current', record
    return 'other', record


def build_library(tree):
    env = {key: value for key, value in os.environ.items()
           if key not in ('CC', 'CFLAGS', 'CPPFLAGS', 'LDFLAGS', 'MAKEFLAGS', 'MFLAGS')}
    result = subprocess.run(['make', '-C', str(tree), LIBRARY], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            timeout=900)
    if result.returncode != 0:
        raise ValueError('could not build %s:\n%s' % (LIBRARY, result.stdout[-2000:]))
    build = tree / 'build'
    for entry in build.iterdir():
        if entry.name != 'libneuronte.so':
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink()
    library = tree / LIBRARY
    if library.is_symlink() or not library.is_file():
        raise ValueError('the build did not produce ' + LIBRARY)
    library.chmod(0o755)
    build.chmod(0o755)


def probe_library(tree):
    """Load the built library in a child, so a bad one cannot hurt this process."""
    code = (
        'import ctypes,sys\n'
        'lib=ctypes.CDLL(sys.argv[1])\n'
        'lib.neuronte_open_file.argtypes=[ctypes.c_char_p,ctypes.POINTER(ctypes.c_void_p)]\n'
        'lib.neuronte_open_file.restype=ctypes.c_int\n'
        'lib.neuronte_close.argtypes=[ctypes.c_void_p]\n'
        'lib.neuronte_close.restype=None\n'
        'for path in sys.argv[2:]:\n'
        '    handle=ctypes.c_void_p()\n'
        '    if lib.neuronte_open_file(path.encode(),ctypes.byref(handle))!=0 or not handle.value:\n'
        '        sys.exit("cannot open "+path)\n'
        '    lib.neuronte_close(handle)\n')
    result = subprocess.run([sys.executable, '-I', '-c', code, str(tree / LIBRARY),
                             *(str(tree / name) for name in PROBES)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            timeout=120)
    if result.returncode != 0:
        raise ValueError('the built Neuronte library failed its probe: '
                         + result.stdout.strip()[-500:])


def clean_stale(parent):
    for entry in parent.glob('.neuronte-stage-*'):
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry, ignore_errors=True)
    for entry in parent.glob('.neuronte-previous-*'):
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry, ignore_errors=True)


def install(args):
    manifest = load_manifest(args.manifest, args.ref)
    if manifest.get('repository') != args.repo:
        raise ValueError('the payload manifest names %s, not NEURONTE_REPO %s'
                         % (manifest.get('repository'), args.repo))
    if os.geteuid() == 0 and not args.allow_root:
        raise ValueError('install Neuronte as the desktop user, not root')
    destination = Path(os.path.abspath(args.destination))
    home = os.environ.get('NEURONTE_HOME', '')
    if home and os.path.realpath(os.path.expanduser(home)) == os.path.realpath(destination):
        print('Neuronte: NEURONTE_HOME names %s; leaving that tree to its owner' % destination)
        return 0
    state, _record = inspect(destination, manifest)
    if state == 'current':
        print('Neuronte %s is already installed in %s' % (args.ref[:12], destination))
        return 0
    archive = None
    for candidate in args.archive or ():
        if Path(candidate).is_file():
            archive = Path(candidate)
            break
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    clean_stale(parent)
    stage = Path(tempfile.mkdtemp(prefix='.neuronte-stage-', dir=parent))
    try:
        if archive is None:
            if args.no_fetch:
                raise ValueError('no Neuronte archive for %s and fetching is disabled'
                                 % args.ref[:12])
            archive = stage / '.download.tar'
            try:
                fetch_archive(args.repo, args.ref, args.manifest, archive)
            except FetchUnavailable as error:
                if args.fetch_failure == 'warn':
                    print('Neuronte: %s; the installed tree is unchanged and the next '
                          'update tries again' % error, file=sys.stderr)
                    return 0
                raise ValueError(str(error))
        tree = stage / 'neuronte'
        tree.mkdir(mode=0o755)
        verify_archive(archive, manifest, extract_to=tree)
        # Directories the extraction made follow the caller's umask; the
        # tree is world-readable like the image's other shared sources.
        for root, dirs, _names in os.walk(tree):
            for name in dirs:
                (Path(root) / name).chmod(0o755)
        if archive.parent == stage:
            archive.unlink()
        build_library(tree)
        probe_library(tree)
        record = {
            'schema': RECORD_SCHEMA,
            'repository': args.repo,
            'commit': args.ref,
            'manifest_sha256': manifest_digest(args.manifest),
            'files': {name: entry['blob'] for name, entry in manifest['files'].items()},
            'library_sha256': hashlib.sha256((tree / LIBRARY).read_bytes()).hexdigest(),
            'installed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        }
        (tree / RECORD).write_text(json.dumps(record, indent=1, sort_keys=True) + '\n')
        (tree / RECORD).chmod(0o644)
        tree.chmod(0o755)
        # Re-read the destination: nothing may have appeared while building.
        if inspect(destination, manifest)[0] != state:
            raise Refusal('%s changed during installation' % destination)
        previous = None
        if state != 'absent':
            previous = Path(tempfile.mkdtemp(prefix='.neuronte-previous-', dir=parent))
            os.rename(destination, previous / 'neuronte')
        try:
            os.rename(tree, destination)
        except BaseException:
            if previous is not None:
                os.rename(previous / 'neuronte', destination)
            raise
        if previous is not None:
            shutil.rmtree(previous, ignore_errors=True)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    print('Neuronte %s installed in %s' % (args.ref[:12], destination))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('write-manifest')
    p.add_argument('--repo-dir', type=Path, required=True)
    p.add_argument('--commit', required=True)
    p.add_argument('--repository', default=CANONICAL_REPO)
    p.add_argument('--out', type=Path, required=True)
    for name in ('fetch-archive', 'verify', 'install'):
        p = sub.add_parser(name)
        p.add_argument('--manifest', type=Path, required=True)
        p.add_argument('--ref', required=True)
        if name != 'verify':
            p.add_argument('--repo', default=CANONICAL_REPO)
        if name == 'fetch-archive':
            p.add_argument('--out', type=Path, required=True)
            p.add_argument('--xz', action='store_true')
        if name == 'verify':
            p.add_argument('--archive', type=Path, required=True)
        if name == 'install':
            p.add_argument('--destination', type=Path, required=True)
            p.add_argument('--archive', action='append',
                           help='a local archive to use if present (repeatable)')
            p.add_argument('--no-fetch', action='store_true')
            p.add_argument('--fetch-failure', choices=('error', 'warn'), default='error')
            p.add_argument('--allow-root', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.command == 'write-manifest':
            write_manifest(args.repo_dir, args.commit, args.out, args.repository)
        elif args.command == 'fetch-archive':
            fetch_archive(args.repo, args.ref, args.manifest, args.out, compress=args.xz)
            print('Neuronte %s archive written to %s' % (args.ref[:12], args.out))
        elif args.command == 'verify':
            total = verify_archive(args.archive, load_manifest(args.manifest, args.ref))
            print('Neuronte %s archive verified (%d bytes)' % (args.ref[:12], total))
        else:
            return install(args)
    except Refusal as error:
        parser.exit(1, 'Neuronte: refusing: %s\n' % error)
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, lzma.LZMAError,
            FetchUnavailable, subprocess.SubprocessError) as error:
        parser.exit(1, 'Neuronte: %s\n' % error)
    return 0


if __name__ == '__main__':
    sys.exit(main())
