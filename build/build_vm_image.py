#!/usr/bin/env python3
"""build_vm_image.py — build a Plebian-OS VM image from scratch.

Interactively asks a few questions (username, password, RAM, disk, …), builds a
customized Plebian-OS installer ISO with the repo's own tooling, then creates a
VirtualBox VM, runs the unattended install, and waits for first-boot
provisioning (pleb + kilix) to finish. The result is a ready-to-run VM.

    build/build_vm_image.py                 # interactive
    build/build_vm_image.py --yes           # accept all defaults, no prompts
    build/build_vm_image.py --dry-run       # show the plan; build nothing

Targets: only `virtualbox` is implemented today. `qemu` and `docker` are
planned — the ISO build below is target-agnostic and meant to be reused by them.
"""
from __future__ import annotations

import argparse
import atexit
import contextlib
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PRESEED_TEMPLATE = REPO / "preseed" / "preseed.cfg"
REMASTER = REPO / "build" / "remaster-iso.sh"
DEFAULT_PROVISION_TIMEOUT_MINUTES = 120
F120_ROOT_REPOS = {
    "KILIX_SYSTEM_MONITOR":
        "https://github.com/itsmygithubacct/kilix-system-monitor.git",
    "KILIX_DESKTOP_SDK":
        "https://github.com/itsmygithubacct/kilix-desktop-sdk.git",
    "KILIX_ICEWM": "https://github.com/itsmygithubacct/kilix-icewm.git",
    "KILIX_MEDIA_SDK":
        "https://github.com/itsmygithubacct/kilix-media-sdk.git",
    "KILIX_WAYDROID":
        "https://github.com/itsmygithubacct/kilix-waydroid.git",
}
F120_ROOT_KEYS = tuple(
    f"{root}_{suffix}"
    for root in F120_ROOT_REPOS
    for suffix in ("REF", "REPO", "BRANCH")
)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class AcceptanceRecorder:
    """Persist a password-free, checksummed account of one VM acceptance run."""

    def __init__(self, path: Path, initial: dict) -> None:
        self.path = path
        self.data = {
            "schema_version": 1,
            "status": "running",
            "started_utc": utc_now(),
            "completed_utc": None,
            "failure": None,
            "stages": [],
            "checks": [],
            **initial,
        }
        self.write()

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, raw_tmp = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        tmp = Path(raw_tmp)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2, sort_keys=True)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp, 0o644)
            os.replace(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)

        checksum = sha256_file(self.path)
        checksum_path = Path(str(self.path) + ".sha256")
        checksum_fd, raw_checksum_tmp = tempfile.mkstemp(
            prefix=f".{checksum_path.name}.", suffix=".tmp", dir=self.path.parent
        )
        checksum_tmp = Path(raw_checksum_tmp)
        try:
            with os.fdopen(checksum_fd, "w", encoding="utf-8") as fh:
                fh.write(f"{checksum}  {self.path.name}\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(checksum_tmp, 0o644)
            os.replace(checksum_tmp, checksum_path)
        finally:
            checksum_tmp.unlink(missing_ok=True)

    def stage(self, name: str, status: str = "passed", detail: str = "") -> None:
        item = {"name": name, "status": status, "at_utc": utc_now()}
        if detail:
            item["detail"] = detail
        self.data["stages"].append(item)
        self.write()

    def check(self, name: str, passed: bool, detail: str = "") -> None:
        item = {
            "name": name,
            "status": "passed" if passed else "failed",
            "at_utc": utc_now(),
        }
        if detail:
            item["detail"] = detail[-6000:]
        self.data["checks"].append(item)
        self.write()

    def set_iso(self, path: Path) -> None:
        self.data["iso"] = {
            "filename": path.name,
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        self.write()

    def complete(self, status: str = "passed") -> None:
        self.data["status"] = status
        self.data["completed_utc"] = utc_now()
        self.write()

    def fail(self, reason: str) -> None:
        if self.data.get("status") == "passed":
            return
        self.data["status"] = "failed"
        self.data["failure"] = reason
        self.data["completed_utc"] = utc_now()
        self.write()


_RECORDER: AcceptanceRecorder | None = None


def storage_dir(kind: str) -> Path:
    base = Path(os.environ.get(
        "GPU_TERMINAL_HOME", Path.home() / ".local" / "gpu_terminal"))
    root = Path(os.environ.get("PLEBIAN_OS_STORAGE_HOME", base / "plebian-os"))
    env_name = {
        "artifacts": "PLEBIAN_OS_ARTIFACTS",
        "session": "PLEBIAN_OS_SESSION_HOME",
    }.get(kind)
    return Path(os.environ.get(env_name, root / kind)) if env_name else root / kind


def repo_version() -> str:
    """The shared version; named releases always use the tracked VERSION."""
    if os.environ.get("PLEBIAN_OS_RELEASE"):
        try:
            return (REPO / "VERSION").read_text().strip()
        except OSError:
            return ""
    v = os.environ.get("PLEBIAN_OS_VERSION")
    if v:
        return v
    try:
        return (REPO / "VERSION").read_text().strip()
    except OSError:
        return ""


def default_iso_filename(name: str) -> str:
    """Use a publishable, versioned filename for strict release artifacts."""
    if os.environ.get("PLEBIAN_OS_RELEASE_MODE") == "1":
        version = repo_version()
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            die("release ISO filename requires a semantic PLEBIAN_OS_VERSION")
        return f"plebian-os-{version}-amd64.iso"
    return f"plebian-os-{name}.iso"


def apply_release_manifest(release: str | None = None) -> None:
    """If PLEBIAN_OS_RELEASE is set, load releases/<ver>.env into os.environ
    authoritatively, mirroring remaster-iso.sh. Ambient values never override a
    named release's mode, version, refs, or hashes."""
    release = release or os.environ.get("PLEBIAN_OS_RELEASE")
    if not release:
        return
    if not re.fullmatch(r"\d+\.\d+\.\d+", release):
        die(f"invalid release identifier: {release}")
    manifest = REPO / "releases" / f"{release}.env"
    if not manifest.exists():
        die(f"no release manifest: releases/{release}.env")
    os.environ["PLEBIAN_OS_RELEASE"] = release
    placeholders = {
        "REPLACE_ME", "REPLACE-ME", "TBD", "TODO", "FIXME", "XXX",
        "CHANGEME", "CHANGE_ME", "PLACEHOLDER", "UNSET", "NONE",
    }

    def read_assignments(path: Path, label: str) -> dict[str, str]:
        values: dict[str, str] = {}
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                die(f"invalid {label} line: {raw}")
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip().strip('"')
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                die(f"invalid {label} key: {key}")
            if key in values:
                die(f"duplicate {label} key: {key}")
            if val.upper() in placeholders or "<" in val or ">" in val:
                die(f"release {release}: {key} is still a placeholder in "
                    f"{path.relative_to(REPO)}")
            values[key] = val
        return values

    manifest_values = read_assignments(manifest, "release manifest")
    for key, val in manifest_values.items():
        os.environ[key] = val

    requirements = REPO / "releases" / f"{release}.requirements"
    if release in {"0.1.9", "0.2.1"} and not requirements.exists():
        die(f"release {release} is missing releases/{release}.requirements")
    if requirements.exists():
        for key, required in read_assignments(
                requirements, "release requirements").items():
            if key not in manifest_values:
                die(f"release {release} manifest must declare required key {key}")
            if manifest_values[key] != required:
                die(f"release {release} requires {key}={required} "
                    f"(manifest has {manifest_values[key]})")

    if release == "0.2.1":
        for root, expected_repo in F120_ROOT_REPOS.items():
            ref_key, repo_key, branch_key = (
                f"{root}_REF", f"{root}_REPO", f"{root}_BRANCH")
            ref = manifest_values.get(ref_key, "")
            if not re.fullmatch(r"[0-9a-f]{40}", ref):
                die(f"release {release} requires {ref_key} to be a full "
                    "40-character lowercase commit SHA")
            if manifest_values.get(repo_key) != expected_repo:
                die(f"release {release} requires canonical {repo_key}")
            if branch_key not in manifest_values or manifest_values[branch_key]:
                die(f"release {release} requires {branch_key} to be declared empty")
        max_bytes = manifest_values.get(
            "PLEBIAN_OS_UV_INSTALLER_MAX_BYTES", "")
        if not re.fullmatch(r"[1-9][0-9]*", max_bytes):
            die("release mode requires a positive "
                "PLEBIAN_OS_UV_INSTALLER_MAX_BYTES")
    tracked = (REPO / "VERSION").read_text().strip()
    if os.environ.get("PLEBIAN_OS_RELEASE_MODE") != "1":
        die(f"release {release} manifest must set PLEBIAN_OS_RELEASE_MODE=1")
    if os.environ.get("PLEBIAN_OS_VERSION") != release or tracked != release:
        die(f"release {release} must match the manifest and checkout VERSION")
    info(f"release {release}: applied pins from releases/{release}.env")

# ── little terminal helpers ──────────────────────────────────────────────────
def c(code: str, s: str) -> str:
    return s if not sys.stdout.isatty() else f"\033[{code}m{s}\033[0m"

def info(s: str) -> None: print(c("1;36", "[build-vm]"), s)
def warn(s: str) -> None: print(c("1;33", "[build-vm]"), s, file=sys.stderr)
def die(s: str) -> None:
    if _RECORDER is not None:
        _RECORDER.fail(s)
    print(c("1;31", "[build-vm] " + s), file=sys.stderr)
    sys.exit(1)

def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None

def run(argv, *, check=True, capture=False, **kw):
    """Run a command, echoing it. Returns CompletedProcess."""
    info("+ " + " ".join(shlex.quote(str(a)) for a in argv))
    return subprocess.run(
        [str(a) for a in argv],
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        **kw,
    )

# ── host-derived defaults ────────────────────────────────────────────────────
def host_ram_mb() -> int:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) // 1024
    except OSError:
        pass
    return 8192

def default_ram_mb() -> int:
    # A quarter of system RAM, rounded to 256 MB. The release acceptance build
    # uses 4 GiB because the pinned fork's generated Go packages can exceed
    # 2 GiB RSS even with serial package compilation.
    q = host_ram_mb() // 4
    return max(4096, (q // 256) * 256)

def default_cpus() -> int:
    return max(1, (os.cpu_count() or 2) // 2)

def free_port(start: int = 2222) -> int:
    for p in range(start, start + 200):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:  # nothing listening
                return p
    return start

def generated_password() -> str:
    return secrets.token_urlsafe(18)


def default_hostname(name: str) -> str:
    """Turn a VirtualBox-friendly name into one valid DNS hostname label."""
    hostname = re.sub(r"[^A-Za-z0-9-]+", "-", name).strip("-")
    hostname = hostname[:63].rstrip("-")
    return hostname or "plebian"


def validate_identity(*, name: str, username: str, fullname: str,
                      password: str, hostname: str,
                      password_hash: str = "") -> None:
    """Reject values that Debian preseed or VirtualBox would reinterpret."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name):
        die("VM/image name must use 1-64 letters, digits, dots, underscores, or hyphens")
    if not re.fullmatch(r"[a-z][-a-z0-9_]{0,31}", username):
        die("username must match [a-z][-a-z0-9_]{0,31}")
    reserved = {
        "root", "daemon", "bin", "sys", "sync", "games", "man", "lp",
        "mail", "news", "uucp", "proxy", "www-data", "backup", "list",
        "irc", "gnats", "nobody", "_apt", "messagebus", "polkitd",
        "sshd", "lightdm", "systemd-network", "systemd-timesync",
    }
    if username in reserved:
        die(f"username {username!r} is reserved for a system account")
    if (not 1 <= len(fullname) <= 128 or any(ord(ch) < 32 for ch in fullname)
            or ":" in fullname or "\\" in fullname):
        die("full name must be 1-128 printable characters with no colon or backslash")
    if bool(password) == bool(password_hash):
        die("automated identity requires exactly one plaintext or crypted credential")
    if password and any(ch in password for ch in "\r\n\0"):
        die("password must contain no newline or NUL")
    if password_hash and (len(password_hash) > 255 or not re.fullmatch(
            r"\$(?:6|y)\$[^\s:]{16,}", password_hash)):
        die("password hash must be one supported SHA-512-crypt or yescrypt value")
    if len(hostname) > 63 or not re.fullmatch(
            r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", hostname):
        die("hostname must be a single RFC-compatible label (letters, digits, hyphens)")

# ── config ───────────────────────────────────────────────────────────────────
@dataclass
class Config:
    name: str
    username: str
    fullname: str
    password: str
    hostname: str
    ram_mb: int
    cpus: int
    vram_mb: int
    accelerate_3d: bool
    firmware: str
    disk_gb: int
    desktop: bool          # PLEB_DESKTOP: run the provider in Kilix page 1
    kiosk: bool            # PLEBIAN_OS_KIOSK: autologin straight into Pleb
    nopasswd_sudo: bool    # PLEBIAN_OS_NOPASSWD_SUDO: passwordless sudo for the user
    ssh_port: int
    gui: bool              # start with a window vs headless
    wait: bool             # block until provisioning finishes
    password_hash: str = ""       # protected hash-file mode; never plaintext
    credential_generated: bool = False  # expire after harness verification
    interactive_installer: bool = False  # prebuilt media collects guest identity

# ── prompting ────────────────────────────────────────────────────────────────
class Prompter:
    def __init__(self, assume_yes: bool):
        self.yes = assume_yes

    def ask(self, label, default, cast=str, validate=None):
        while True:
            if self.yes:
                raw = ""
            else:
                try:
                    raw = input(f"  {label} [{default}]: ").strip()
                except EOFError:
                    raw = ""
            if raw == "":
                raw = str(default)
            try:
                val = cast(raw)
            except (ValueError, TypeError):
                print("    ↳ not a valid value, try again"); continue
            if validate and not validate(val):
                print("    ↳ out of range, try again"); continue
            return val

    def ask_bool(self, label, default: bool):
        if self.yes:
            return default
        d = "Y/n" if default else "y/N"
        try:
            raw = input(f"  {label} [{d}]: ").strip().lower()
        except EOFError:
            raw = ""
        if raw == "":
            return default
        return raw in ("y", "yes")

    def ask_password(self, default: str):
        if self.yes:
            return default
        import getpass
        while True:
            try:
                suffix = f" [{default}]" if default else ""
                pw = getpass.getpass(f"  password{suffix}: ")
            except EOFError:
                pw = ""
            if pw == "":
                if default:
                    return default
                print("    ↳ password cannot be empty"); continue
            again = getpass.getpass("  confirm password: ")
            if pw == again:
                return pw
            print("    ↳ passwords didn't match, try again")


def env_bool(name: str, default: bool) -> bool:
    """Read a shell-style boolean, treating an unset/empty value as default."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in ("1", "yes", "true", "on"):
        return True
    if value in ("0", "no", "false", "off"):
        return False
    die(f"{name} must be one of 1/0, yes/no, true/false, or on/off")
    raise AssertionError("unreachable")


def read_protected_credential(path: Path, *, label: str) -> str:
    """Read one credential from an owner-only regular file without symlinks."""
    try:
        before = path.lstat()
    except OSError as exc:
        die(f"could not inspect {label}: {exc}")
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        die(f"{label} must be a regular non-symlink file")
    if before.st_uid != os.geteuid() or stat.S_IMODE(before.st_mode) != 0o600:
        die(f"{label} must be owned by the current user and mode 0600")
    if before.st_nlink != 1:
        die(f"{label} must have exactly one hard link")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as fh:
            current = os.fstat(fh.fileno())
            if (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
                die(f"{label} changed during validation")
            data = fh.read(4097)
    except OSError as exc:
        die(f"could not read {label}: {exc}")
    if len(data) > 4096 or b"\0" in data:
        die(f"{label} is invalid or too large")
    try:
        value = data.decode("utf-8")
    except UnicodeDecodeError:
        die(f"{label} must be UTF-8 text")
    if value.endswith("\n"):
        value = value[:-1]
    if not value or "\n" in value or "\r" in value:
        die(f"{label} must contain exactly one nonempty line")
    return value


def resolve_automated_credential(args, prompter: Prompter) -> tuple[str, str, bool]:
    """Return plaintext, crypt hash, and whether the harness generated it."""
    for key in ("IMAGE_PASSWORD", "RANDOM_PASSWORD"):
        if key in os.environ:
            die(f"{key} is retired; use --password-file, --password-hash-file, "
                "or --generate-one-time-password")
    if getattr(args, "password", None) is not None:
        die("--password is retired because command-line secrets are process-list visible; "
            "use --password-file")
    password_file = getattr(args, "password_file", None)
    hash_file = getattr(args, "password_hash_file", None)
    generate = bool(getattr(args, "generate_one_time_password", False))
    selected = sum(value is not None for value in (password_file, hash_file)) + int(generate)
    if selected > 1:
        die("choose exactly one credential mode: password file, hash file, or generated")
    if password_file is not None:
        return read_protected_credential(password_file, label="password file"), "", False
    if hash_file is not None:
        return "", read_protected_credential(hash_file, label="password hash file"), False
    if generate:
        return generated_password(), "", True
    if prompter.yes:
        die("--yes requires --password-file, --password-hash-file, or "
            "--generate-one-time-password")
    return prompter.ask_password(""), "", False


def gather_config(args) -> Config:
    p = Prompter(args.yes)
    print(c("1", "\nPlebian-OS → VirtualBox image builder\n"))
    if not args.yes:
        print("Answer the prompts (Enter accepts the [default]).\n")

    name = args.name or p.ask("VM name", "plebian-ci")
    if args.interactive_installer:
        username = fullname = password = password_hash = hostname = ""
        credential_generated = False
    else:
        if args.yes and (not args.username or not args.hostname):
            die("--yes automated images require explicit --username and --hostname")
        username = args.username or p.ask("username", "operator")
        fullname = args.fullname or p.ask("full name", username)
        password, password_hash, credential_generated = resolve_automated_credential(args, p)
        expire_requested = bool(
            getattr(args, "expire_credential_after_verification", False))
        if expire_requested and (not password or credential_generated):
            die("--expire-credential-after-verification requires --password-file")
        credential_generated = credential_generated or expire_requested
        hostname = args.hostname or p.ask("hostname", default_hostname(name))
    ram_mb   = args.ram      or p.ask("RAM (MB)", default_ram_mb(),
                                      cast=int, validate=lambda v: v >= 512)
    cpus     = args.cpus     or p.ask("vCPUs", default_cpus(),
                                      cast=int, validate=lambda v: v >= 1)
    vram_mb  = args.vram if args.vram is not None else 128
    if vram_mb > 256:
        warn(f"VirtualBox rejects VRAM above 256 MB on this host; requested {vram_mb}, using 256")
        vram_mb = 256
    firmware = args.firmware or os.environ.get("PLEBIAN_OS_VM_FIRMWARE", "bios")
    disk_gb  = args.disk     or p.ask("disk (GB, sparse)", 200,
                                      cast=int, validate=lambda v: v >= 8)
    if args.interactive_installer:
        desktop = kiosk = nopasswd = False
    else:
        desktop_default = env_bool("PLEBIAN_OS_DESKTOP", True)
        kiosk_default = env_bool("PLEBIAN_OS_KIOSK", False)
        nopasswd_default = env_bool("PLEBIAN_OS_NOPASSWD_SUDO", False)
        if args.session:
            desktop = args.session == "desktop"
        else:
            desktop = p.ask_bool(
                "load the configured desktop provider in the first kilix page",
                desktop_default,
            )
        kiosk = args.kiosk if args.kiosk is not None \
            else p.ask_bool("autologin (kiosk) instead of a login screen",
                            kiosk_default)
        nopasswd = args.nopasswd_sudo if args.nopasswd_sudo is not None \
            else p.ask_bool(f"passwordless sudo for {username}",
                            nopasswd_default)
    if args.interactive_installer:
        ssh_port = args.port or free_port()
    else:
        ssh_port = args.port or p.ask(
            "SSH host port (forwarded to guest 22)", free_port(),
            cast=int, validate=lambda v: 1 <= v <= 65535)

    if args.interactive_installer:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name):
            die("VM/image name must use 1-64 letters, digits, dots, underscores, or hyphens")
    else:
        validate_identity(name=name, username=username, fullname=fullname,
                          password=password, password_hash=password_hash,
                          hostname=hostname)
    if firmware not in ("bios", "efi"):
        die("firmware must be bios or efi")
    if ram_mb < 512 or cpus < 1 or vram_mb < 1 or disk_gb < 8:
        die("resources must be RAM >= 512 MB, CPUs >= 1, VRAM >= 1 MB, disk >= 8 GB")
    if ram_mb < 4096:
        warn(f"RAM {ram_mb} MB is below the 4096 MB release-tested build baseline; "
             "firstboot fork compilation may exhaust memory")
    if not 1 <= ssh_port <= 65535:
        die("SSH host port must be between 1 and 65535")
    if password_hash and not args.no_wait:
        die("--password-hash-file cannot authenticate the SSH waiter; pass --no-wait")
    if credential_generated and (args.no_wait or not nopasswd):
        die("generated one-time credentials require waiting and --sudo-nopasswd "
            "so the harness can expire them")
    return Config(name=name, username=username, fullname=fullname, password=password,
                  hostname=hostname, ram_mb=ram_mb, cpus=cpus,
                  vram_mb=vram_mb, accelerate_3d=args.accelerate_3d,
                  firmware=firmware,
                  disk_gb=disk_gb,
                  desktop=desktop, kiosk=kiosk, nopasswd_sudo=nopasswd, ssh_port=ssh_port,
                  gui=args.gui, wait=not args.no_wait,
                  password_hash=password_hash,
                  credential_generated=credential_generated,
                  interactive_installer=args.interactive_installer)


def confirm_summary(cfg: Config, assume_yes: bool) -> None:
    print(c("1", "\nAbout to build:"))
    rows = [("VM name", cfg.name)]
    if cfg.interactive_installer:
        rows.append(("identity", "chosen in Debian Installer; no credential supplied"))
    else:
        rows.extend([
            ("username", cfg.username), ("hostname", cfg.hostname),
        ])
    rows.extend([
        ("RAM", f"{cfg.ram_mb} MB"), ("vCPUs", cfg.cpus),
        ("VRAM", f"{cfg.vram_mb} MB"),
        ("3D accel", "on" if cfg.accelerate_3d else "off"),
        ("firmware", cfg.firmware.upper()),
        ("disk", f"{cfg.disk_gb} GB (sparse)"),
    ])
    if not cfg.interactive_installer:
        rows.extend([
            ("session", "desktop provider in Kilix page 1" if cfg.desktop
                        else "Kilix shell in page 1"),
            ("login", "autologin (kiosk)" if cfg.kiosk else "greeter"),
            ("sudo", "passwordless" if cfg.nopasswd_sudo else "password required"),
            ("SSH", f"ssh -p {cfg.ssh_port} {cfg.username}@127.0.0.1"),
        ])
    rows.append(("display", "GUI window" if cfg.gui else "headless"))
    for k, v in rows:
        print(f"  {k:<9}: {v}")
    print()
    if assume_yes:
        return
    try:
        if input("Proceed? [Y/n]: ").strip().lower() in ("n", "no"):
            die("aborted.")
    except EOFError:
        pass

# ── password hashing (keep the plaintext off the ISO) ────────────────────────
def crypt_password(pw: str) -> tuple[str, bool]:
    """Return (secret, is_crypted). Prefer a SHA-512 crypt hash via openssl."""
    if have("openssl"):
        r = subprocess.run(["openssl", "passwd", "-6", "-stdin"],
                           input=pw, text=True, capture_output=True)
        if r.returncode == 0 and r.stdout.strip().startswith("$6$"):
            return r.stdout.strip(), True
    die("openssl is required to hash installer passwords; refusing a plaintext preseed")
    raise AssertionError("unreachable")

# ── preseed generation ───────────────────────────────────────────────────────
def generate_preseed(cfg: Config, enable_ssh: bool = False) -> Path:
    text = PRESEED_TEMPLATE.read_text()

    def sub(pattern, repl):
        nonlocal text
        new, n = re.subn(pattern, repl, text, flags=re.MULTILINE)
        if n == 0:
            warn(f"preseed: pattern not found, skipped: {pattern!r}")
        text = new

    # The tracked template is the normal interactive persona and contains no
    # identity answers. Build a separate automated persona by inserting one
    # validated identity block with a crypt hash only.
    secret = cfg.password_hash or crypt_password(cfg.password)[0]
    marker = "d-i passwd/root-login boolean false\n"
    if text.count(marker) != 1:
        die("normal preseed must contain exactly one root-login policy marker")
    identity = (
        "\n### Automated identity profile (generated; not publishable release media)\n"
        f"d-i netcfg/get_hostname string {cfg.hostname}\n"
        f"d-i passwd/user-fullname string {cfg.fullname}\n"
        f"d-i passwd/username string {cfg.username}\n"
        f"d-i passwd/user-password-crypted password {secret}\n"
    )
    text = text.replace(marker, marker + identity, 1)

    # The VM builder watches provisioning over SSH, so its image needs sshd; the
    # USB / raw paths do not and ship without an open sshd.
    if enable_ssh:
        sub(r"^(tasksel tasksel/first multiselect standard)$",
            lambda m: m.group(1) + ", ssh-server")

    # Runtime configuration is deliberately *not* injected here. The Python
    # builders pass these values to remaster-iso.sh, which writes the one
    # authoritative firstboot.env and matching build-info.env. Keeping a second
    # late_command writer here previously made installed state disagree with its
    # provenance manifest.

    session = storage_dir("session")
    session.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkstemp(prefix="plebian-preseed-", suffix=".cfg",
                               dir=session)[1])
    tmp.write_text(text)
    atexit.register(lambda: tmp.unlink(missing_ok=True))
    return tmp

# ── ISO build (target-agnostic; reuses the repo's remaster script) ───────────
def runtime_build_env(cfg: Config) -> dict[str, str]:
    """Map user choices to the single remaster/firstboot configuration path."""
    home = f"/home/{cfg.username}"
    source_root = os.environ.get(
        "PLEBIAN_OS_TARGET_SOURCE_HOME",
        f"{home}/.local/gpu_terminal/sources",
    )
    data_root = os.environ.get(
        "PLEBIAN_OS_TARGET_GPU_TERMINAL_HOME",
        f"{home}/.local/gpu_terminal",
    )
    return {
        "PLEBIAN_OS_DESKTOP": "1" if cfg.desktop else "0",
        "PLEBIAN_OS_KIOSK": "1" if cfg.kiosk else "0",
        "PLEBIAN_OS_USER": cfg.username,
        "PLEBIAN_OS_NOPASSWD_SUDO": "1" if cfg.nopasswd_sudo else "0",
        # Target-prefixed transport keys keep the builder's host-side cache and
        # scratch variables from becoming guest configuration. remaster-iso.sh
        # derives every coordinated checkout/data path from these two roots.
        "PLEBIAN_OS_TARGET_SOURCE_HOME": source_root,
        "PLEBIAN_OS_TARGET_GPU_TERMINAL_HOME": data_root,
    }


def build_iso(cfg: Config, preseed: Path | None, out_iso: Path, dry_run: bool) -> Path:
    info(f"building installer ISO via {REMASTER.name} (custom preseed baked in)")
    # AUTOBOOT makes the ISO's boot menu auto-select the install entry — a VM
    # build has no one to press a key at the menu.
    # remaster-iso.sh SRC OUT — an empty SRC makes it use the cached/downloaded
    # Debian netinst (honours PLEBIAN_OS_NETINST too).
    if dry_run:
        seed = preseed if preseed is not None else "<generated preseed>"
        info(f"+ PLEBIAN_OS_AUTOBOOT=1 PLEBIAN_OS_UNATTENDED_DISK=1 "
             f"PLEBIAN_OS_PRESEED={seed} {REMASTER} '' {out_iso}")
        return out_iso
    env = {**os.environ, **runtime_build_env(cfg),
           "PLEBIAN_OS_PRESEED": str(preseed),
           "PLEBIAN_OS_AUTOBOOT": "1", "PLEBIAN_OS_UNATTENDED_DISK": "1",
           "PLEBIAN_OS_SSH_ENABLED": "1"}
    env.pop("IMAGE_PASSWORD", None)
    env.pop("RANDOM_PASSWORD", None)
    run([REMASTER, "", str(out_iso)], env=env)
    if not out_iso.exists():
        die(f"ISO build did not produce {out_iso}")
    return out_iso

# ── VirtualBox ───────────────────────────────────────────────────────────────
def vbox_info(name: str) -> dict:
    r = subprocess.run(["VBoxManage", "showvminfo", name, "--machinereadable"],
                      capture_output=True, text=True)
    d = {}
    if r.returncode == 0:
        for line in r.stdout.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                d[k.strip('"')] = v.strip().strip('"')
    return d

def vbox_exists(name: str) -> bool:
    return subprocess.run(["VBoxManage", "showvminfo", name],
                        capture_output=True).returncode == 0

def vbox_create(cfg: Config, iso: Path, *, replace: bool = False,
                assume_yes: bool = False) -> None:
    if vbox_exists(cfg.name):
        warn(f"a VM named {cfg.name!r} already exists")
        if not replace:
            die("refusing to delete it; pass --replace explicitly to recreate it")
        if assume_yes:
            info("  --replace --yes: deleting and recreating it")
        else:
            try:
                ans = input(f"  type the VM name to delete it ({cfg.name}): ").strip()
            except EOFError:
                ans = ""
            if ans != cfg.name:
                die("confirmation did not match; existing VM was not changed")
        subprocess.run(["VBoxManage", "controlvm", cfg.name, "poweroff"],
                      capture_output=True)
        time.sleep(1)
        run(["VBoxManage", "unregistervm", cfg.name, "--delete"])

    run(["VBoxManage", "createvm", "--name", cfg.name, "--ostype", "Debian_64", "--register"])
    run(["VBoxManage", "modifyvm", cfg.name,
         "--memory", cfg.ram_mb, "--cpus", cfg.cpus, "--ioapic", "on",
         "--vram", cfg.vram_mb, "--graphicscontroller", "vmsvga",
         "--accelerate-3d", "on" if cfg.accelerate_3d else "off",
         "--firmware", cfg.firmware,
         "--rtcuseutc", "on", "--nic1", "nat",
         "--natpf1", f"ssh,tcp,127.0.0.1,{cfg.ssh_port},,22",
         # Fresh VMs do not expose host audio automatically. Enable output for
         # read-aloud and input for the click-to-talk dictation control.
         "--audio-driver", "default", "--audio-enabled", "on",
         "--audio-in", "on", "--audio-out", "on",
         "--boot1", "disk", "--boot2", "dvd", "--boot3", "none", "--boot4", "none"])

    vmdir = Path(vbox_info(cfg.name)["CfgFile"]).parent
    vdi = vmdir / f"{cfg.name}.vdi"
    run(["VBoxManage", "createmedium", "disk", "--filename", str(vdi),
         "--size", cfg.disk_gb * 1024, "--variant", "Standard"])  # Standard = sparse/dynamic
    run(["VBoxManage", "storagectl", cfg.name, "--name", "SATA",
         "--add", "sata", "--controller", "IntelAhci", "--portcount", 2, "--bootable", "on"])
    run(["VBoxManage", "storageattach", cfg.name, "--storagectl", "SATA",
         "--port", 0, "--device", 0, "--type", "hdd", "--medium", str(vdi)])
    run(["VBoxManage", "storageattach", cfg.name, "--storagectl", "SATA",
         "--port", 1, "--device", 0, "--type", "dvddrive", "--medium", str(iso),
         "--hotpluggable", "on"])

def vbox_start(cfg: Config) -> None:
    run(["VBoxManage", "startvm", cfg.name,
         "--type", "gui" if cfg.gui else "headless"])

def vbox_detach_iso(cfg: Config) -> None:
    # Debian's installer normally ejects the medium before it reboots.  In that
    # state VirtualBox reports an existing, empty DVD drive; asking it to
    # detach the drive itself is a hot-plug operation, not a second eject, and
    # older VM definitions reject it.  Treat an already empty drive as the
    # successful end state and only issue storageattach when a medium is still
    # present.  Newly created acceptance VMs also mark this slot hot-pluggable
    # so the fallback path works when an installer leaves its medium mounted.
    if vbox_info(cfg.name).get("SATA-1-0") == "emptydrive":
        info("installer ISO is already ejected")
        return
    result = subprocess.run(
        ["VBoxManage", "storageattach", cfg.name, "--storagectl", "SATA",
         "--port", "1", "--device", "0", "--type", "dvddrive",
         "--medium", "none"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown VirtualBox error").strip()
        die(f"could not detach the installer ISO: {detail}")

# ── SSH into the guest (password auth via SSH_ASKPASS; no sshpass needed) ─────
@contextlib.contextmanager
def _askpass_for(pw: str):
    """Yield an askpass program plus owner-only secret file, then remove both.

    The password is never placed in argv or the process environment. The child
    receives only a private pathname which its tiny askpass helper reads.
    """
    if not pw:
        die("SSH waiting requires a plaintext credential from --password-file "
            "or --generate-one-time-password")
    session = storage_dir("session")
    session.mkdir(parents=True, exist_ok=True)
    d = tempfile.mkdtemp(prefix="plebian-askpass-", dir=session)
    os.chmod(d, 0o700)
    script = Path(d) / "askpass.sh"
    secret = Path(d) / "credential"
    fd = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(pw + "\n")
    script.write_text(
        "#!/bin/sh\n"
        "IFS= read -r credential < \"$PLEBIAN_ASKPASS_FILE\" || exit 1\n"
        "exec printf '%s\\n' \"$credential\"\n",
        encoding="utf-8",
    )
    script.chmod(0o700)
    try:
        yield str(script), str(secret)
    finally:
        shutil.rmtree(d, ignore_errors=True)

def ssh(cfg: Config, command: str, askpass: tuple[str, str], timeout: int = 15):
    script, secret = askpass
    env = {**os.environ, "SSH_ASKPASS": script, "SSH_ASKPASS_REQUIRE": "force",
           "DISPLAY": os.environ.get("DISPLAY", ":0"),
           "PLEBIAN_ASKPASS_FILE": secret}
    argv = ["ssh", "-p", str(cfg.ssh_port),
            "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=8", "-o", "PreferredAuthentications=password",
            "-o", "NumberOfPasswordPrompts=1", "-o", "LogLevel=ERROR",
            f"{cfg.username}@127.0.0.1", command]
    try:
        return subprocess.run(argv, env=env, capture_output=True, text=True,
                            timeout=timeout, start_new_session=True)
    except subprocess.TimeoutExpired:
        return None

def wait_for_provisioning(cfg: Config, timeout_s: int,
                          askpass: tuple[str, str]) -> None:
    info("waiting for the unattended install + first-boot provisioning …")
    info("  (installs Debian, reboots, then pulls pleb + kilix from GitHub)")
    # Always exits 0 so we can read stdout even while provisioning is mid-flight.
    status_cmd = (
        "s=$(systemctl is-active plebian-os-firstboot.service 2>/dev/null); "
        "if [ -f /var/lib/plebian-os/provisioned ]; then echo DONE; "
        "elif [ \"$s\" = failed ]; then echo FAILED; "
        "elif [ \"$s\" = inactive ] && "
        "[ -s /var/lib/plebian-os/firstboot-attempts ]; then echo FAILED; "
        "else echo RUNNING; fi")
    start = time.time()
    phase = "install"
    while time.time() - start < timeout_s:
        mm = int(time.time() - start) // 60
        ss = int(time.time() - start) % 60
        r = ssh(cfg, status_cmd, askpass)
        system_up = r is not None and r.returncode == 0
        if system_up:
            out = r.stdout or ""
            if "DONE" in out:
                print()
                info(c("1;32", f"provisioning complete after {mm:02d}:{ss:02d}."))
                return
            if "FAILED" in out:
                print()
                logs = ssh(cfg, "journalctl -u plebian-os-firstboot --no-pager | tail -30", askpass)
                die("first-boot provisioning FAILED:\n" + (logs.stdout if logs else ""))
            if phase == "install":
                phase = "provision"
                print()
                info("system is up; first-boot provisioning running …")
        line = "installing Debian (no SSH yet)" if phase == "install" else "provisioning pleb + kilix"
        print(f"\r  [{mm:02d}:{ss:02d}] {line} …", end="", flush=True)
        time.sleep(20)
    print()
    die(f"timed out after {timeout_s//60} min waiting for provisioning "
        f"(the VM is still running; check it with `VBoxManage startvm {cfg.name} --type gui`).")


def expire_generated_credential(cfg: Config, askpass: tuple[str, str]) -> None:
    """Force a generated harness password to change at the next real login."""
    result = ssh(
        cfg,
        f"sudo -n /usr/bin/chage -d 0 -- {shlex.quote(cfg.username)}",
        askpass,
    )
    ok = result is not None and result.returncode == 0
    detail = "" if ok else (
        "SSH command timed out" if result is None else
        "\n".join(part.strip() for part in (result.stdout, result.stderr)
                  if part.strip())
    )
    if _RECORDER is not None:
        _RECORDER.check("generated credential expired", ok, detail)
    if not ok:
        die("could not expire the generated one-time credential" +
            (f": {detail}" if detail else ""))
    info("generated harness credential expired; next login must replace it.")

# ── acceptance verification (post-provision, over SSH) ───────────────────────
def _catalog_build_script() -> str:
    """Guest-side clean-build program used by release acceptance."""
    return "\n".join((
        "import os",
        "import tempfile",
        "from pathlib import Path",
        "from kilix_content import Installer, default_catalog",
        "installable = tuple(spec for spec in default_catalog()",
        "                    if spec.source_type in ('git', 'archive'))",
        "if not installable:",
        "    raise RuntimeError('catalog contains no pinned installable content')",
        "with tempfile.TemporaryDirectory(prefix='plebian-content-acceptance-') as root:",
        "    for spec in installable:",
        "        kind = 'apps' if spec.kind == 'app' else 'games'",
        "        destination = Path(root) / kind",
        "        print(f'[content] {spec.content_id}', flush=True)",
        "        installer = Installer(str(destination))",
        "        executable = Path(installer.ensure(",
        "            spec, lambda message: print(message, flush=True)))",
        "        expected = Path(installer.executable(spec))",
        "        if executable != expected or installer.ready(spec) != str(executable):",
        "            raise RuntimeError(f'{spec.content_id}: installed executable is not selected')",
        "        if not executable.is_file() or not os.access(executable, os.X_OK):",
        "            raise RuntimeError(f'{spec.content_id}: final executable is not runnable')",
        "print(f'[content] verified {len(installable)} pinned clean builds', flush=True)",
    ))


def verify_catalog_builds(cfg: Config, askpass: str) -> None:
    """Clean-build every installable pinned catalog entry inside the guest."""
    script = _catalog_build_script()
    command = (
        'set -eu; . /etc/pleb/session.env; '
        's="${GPU_TERMINAL_SOURCE_HOME:-$HOME/.local/gpu_terminal/sources}"; '
        'd="${KILIX_DIR:-$s/kilix}"; '
        'export PYTHONPATH="$d/third_party/kilix-content/src"; '
        f'timeout 1750 python3 -c {shlex.quote(script)}'
    )
    info("clean-building every pinned catalog entry …")
    result = ssh(cfg, command, askpass, timeout=1800)
    if result is None:
        if _RECORDER is not None:
            _RECORDER.check("pinned catalog clean builds", False,
                            "timed out after 30 minutes")
        die("catalog clean-build verification timed out after 30 minutes")
    if result.returncode != 0:
        detail = "\n".join(
            output.strip()
            for output in (result.stdout, result.stderr)
            if output.strip()
        )[-6000:]
        if _RECORDER is not None:
            _RECORDER.check("pinned catalog clean builds", False, detail)
        die("catalog clean-build verification FAILED:\n" + detail)
    if _RECORDER is not None:
        _RECORDER.check("pinned catalog clean builds", True)
    info("  [ok] pinned catalog clean builds")


def verify_update_rollback(cfg: Config, askpass: str) -> None:
    """Induce a real OS-layer update failure and prove byte-exact rollback."""
    managed_paths = (
        "/usr/local/sbin/plebian-os-provision",
        "/usr/local/sbin/plebian-os-install-deps",
        "/usr/local/sbin/plebian-os-install-ollama-converter",
        "/usr/local/sbin/plebian-os-install-kilix-vulkan-tts",
        "/usr/local/sbin/plebian-os-install-kilix-ollama-runtime",
        "/usr/local/sbin/plebian-os-passwd",
        "/usr/local/bin/plebian-os-update",
        "/etc/systemd/system/plebian-os-firstboot.service",
        "/usr/local/sbin/plebian-os-firstboot-attempt",
        "/usr/local/share/plebian-os/VERSION",
        "/usr/local/share/plebian-os/wallpapers/plebian-os.png",
        "/usr/local/share/doc/plebian-os/installer/ATTRIBUTION.md",
        "/usr/local/share/doc/plebian-os/COPYING.GPL-2",
        "/etc/lightdm/lightdm-gtk-greeter.conf.d/50-plebian-os.conf",
        "/usr/local/bin/plebian-os-select-closure",
        "/etc/pleb/session.env",
        "/var/lib/plebian-os/packages.list",
        "/var/lib/plebian-os/versions.env",
        "/var/lib/plebian-os/apt-sources.list",
        "/usr/local/bin/uv",
        "/usr/local/bin/uvx",
    )
    quoted_paths = " ".join(shlex.quote(path) for path in managed_paths)
    command = f"""set -eu
. /etc/pleb/session.env
before="$(mktemp)"
after="$(mktemp)"
update_log="$(mktemp)"
cleanup_acceptance_update() {{ rm -f -- "$before" "$after" "$update_log"; }}
trap cleanup_acceptance_update EXIT HUP INT TERM
snapshot_acceptance_update() {{
    for path in {quoted_paths}; do
        if [ -L "$path" ]; then
            printf 'L\\t%s\\t%s\\t%s\\n' "$path" "$(readlink -- "$path")" "$(stat -c '%u:%g:%a:%h' -- "$path")"
        elif [ -f "$path" ]; then
            printf 'F\\t%s\\t%s\\t%s\\n' "$path" "$(sha256sum -- "$path" | awk '{{print $1}}')" "$(stat -c '%u:%g:%a:%h' -- "$path")"
        elif [ -e "$path" ]; then
            printf 'unexpected non-file acceptance path: %s\\n' "$path" >&2
            return 1
        else
            printf 'M\\t%s\\n' "$path"
        fi
    done
}}
snapshot_acceptance_update >"$before"
set +e
PLEBIAN_OS_UPDATE_TEST_FAIL_AFTER=os-layer timeout 900 /usr/local/bin/plebian-os-update >"$update_log" 2>&1
update_rc=$?
set -e
if [ "$update_rc" -eq 0 ] || [ "$update_rc" -eq 124 ] \
        || ! grep -Fq 'injected stack update failure after os-layer' "$update_log"; then
    cat "$update_log" >&2
    exit 1
fi
snapshot_acceptance_update >"$after"
if ! cmp -s "$before" "$after"; then
    diff -u "$before" "$after" >&2 || true
    cat "$update_log" >&2
    exit 1
fi
test -z "$(find /var/lib/plebian-os -maxdepth 1 -type d -name 'update-rollback.*' -print -quit)"
pleb_state="${{PLEB_STATE_HOME:-$HOME/.local/gpu_terminal/pleb/state}}"
test -z "$(find "$pleb_state" -maxdepth 1 -type d -name 'stack-rollback.*' -print -quit)"
"""
    info("inducing an OS-layer update failure and verifying rollback …")
    result = ssh(cfg, command, askpass, timeout=930)
    ok = result is not None and result.returncode == 0
    if result is None:
        detail = "update rollback verification timed out"
    elif ok:
        detail = ""
    else:
        detail = "\n".join(
            output.strip()
            for output in (result.stdout, result.stderr)
            if output.strip()
        ) or f"guest command exited {result.returncode}"
    if _RECORDER is not None:
        _RECORDER.check("induced OS-layer update rollback", ok, detail)
    if not ok:
        die("induced OS-layer update rollback FAILED:\n" + detail)
    info("  [ok] induced OS-layer update rollback")


def verify_successful_update(cfg: Config, askpass: str) -> None:
    """Run the installed same-closure updater and its LightDM restart path."""
    info("running the installed whole-stack updater and restart path …")
    before = ssh(
        cfg,
        "systemctl show -p InvocationID --value lightdm.service",
        askpass,
        timeout=30,
    )
    before_invocation = "" if before is None else before.stdout.strip()
    if before is None or before.returncode != 0 or not before_invocation:
        detail = "could not record the pre-update LightDM invocation"
        if _RECORDER is not None:
            _RECORDER.check("successful whole-stack update and restart", False, detail)
        die("whole-stack update/restart verification FAILED:\n" + detail)
    command = "timeout 3500 /usr/local/bin/plebian-os-update --restart"
    result = ssh(cfg, command, askpass, timeout=3600)
    ok = result is not None and result.returncode == 0
    if result is None:
        detail = "whole-stack update timed out after 60 minutes"
    elif ok:
        detail = ""
    else:
        detail = "\n".join(
            output.strip()
            for output in (result.stdout, result.stderr)
            if output.strip()
        )[-6000:] or f"guest command exited {result.returncode}"
    if ok:
        # --restart deliberately schedules a detached transient unit: a GUI
        # terminal may disappear while LightDM is stopped, but the committed
        # update must still finish restarting the display manager.  Therefore
        # the updater can return while LightDM is briefly inactive.  Require a
        # new service invocation and wait boundedly for it to become active;
        # merely observing the old still-active invocation would be a false
        # positive, while sampling the restart gap once is a false negative.
        old = shlex.quote(before_invocation)
        closure_receipt_keys = (*F120_ROOT_KEYS,
                                "PLEBIAN_OS_UV_INSTALLER_MAX_BYTES")
        capture_release_roots = " ".join(
            f'selected_{key.lower()}="${{{key}:-}}";'
            for key in closure_receipt_keys
        )
        compare_release_roots = " && ".join(
            f'test "${{{key}:-}}" = "$selected_{key.lower()}"'
            for key in closure_receipt_keys
        )
        post = ssh(
            cfg,
            f"old={old}; "
            "timeout 45 sh -c '"
            "while :; do "
            "current=\"$(systemctl show -p InvocationID --value "
            "lightdm.service 2>/dev/null || true)\"; "
            "if [ -n \"$current\" ] && [ \"$current\" != \"$1\" ] && "
            "systemctl is-active --quiet lightdm.service; then exit 0; fi; "
            "if systemctl is-failed --quiet lightdm.service; then exit 1; fi; "
            "sleep 1; done' sh \"$old\" && "
            "test -f /var/lib/plebian-os/provisioned && "
            "! systemctl is-enabled plebian-os-firstboot.service >/dev/null 2>&1 && "
            "test -z \"$(find /var/lib/plebian-os -maxdepth 1 -type d "
            "-name 'update-rollback.*' -print -quit)\" && "
            "test -s /var/lib/plebian-os/packages.list && "
            "test -s /var/lib/plebian-os/apt-sources.list && "
            ". /etc/pleb/session.env && "
            "selected_version=\"$PLEBIAN_OS_VERSION\" && "
            "selected_os=\"$PLEBIAN_OS_REF\" && selected_pleb=\"$PLEB_REF\" && "
            "selected_kilix=\"$KILIX_REF\" && selected_kilix95=\"$KILIX95_REF\" && "
            "selected_uv=\"${PLEBIAN_OS_INSTALL_UV:-0}\" && "
            "selected_uv_version=\"${PLEBIAN_OS_UV_VERSION:-}\" && "
            f"{capture_release_roots} "
            ". /var/lib/plebian-os/versions.env && "
            "test \"$PLEBIAN_OS_VERSION\" = \"$selected_version\" && "
            "test \"$PLEBIAN_OS_COMMIT\" = \"$selected_os\" && "
            "test \"$PLEB_COMMIT\" = \"$selected_pleb\" && "
            "test \"$KILIX_COMMIT\" = \"$selected_kilix\" && "
            "test \"$KILIX95_COMMIT\" = \"$selected_kilix95\" && "
            "test \"$PLEBIAN_OS_INSTALL_UV\" = \"$selected_uv\" && "
            "test \"$PLEBIAN_OS_UV_VERSION\" = \"$selected_uv_version\" && "
            f"{compare_release_roots} && "
            "if [ \"$selected_uv\" = 1 ]; then "
            "test -x /usr/local/bin/uv && test -x /usr/local/bin/uvx && "
            "case \"$(/usr/local/bin/uv --version)\" in "
            "\"uv $selected_uv_version\"|\"uv $selected_uv_version (\"*\\)) true ;; "
            "*) false ;; esac; fi",
            askpass,
            timeout=60,
        )
        ok = post is not None and post.returncode == 0
        if not ok:
            if post is None:
                detail = "post-update health check timed out"
            else:
                detail = "\n".join(
                    output.strip()
                    for output in (post.stdout, post.stderr)
                    if output.strip()
                ) or f"post-update health check exited {post.returncode}"
    if _RECORDER is not None:
        _RECORDER.check("successful whole-stack update and restart", ok, detail)
    if not ok:
        die("whole-stack update/restart verification FAILED:\n" + detail)
    info("  [ok] whole-stack update and restart")


def _voice_functional_smoke_script() -> str:
    """Exercise real espeak synthesis and Vosk recognition without a device."""
    return """\
import os

from voicelib.stt import VoskStt
from voicelib.tts import EspeakTts

pcm, rate = EspeakTts(voice="en-us", rate=135).synth("kilix voice is working")
if not pcm or rate <= 0:
    raise SystemExit("espeak produced no PCM")
data_home = os.environ["KILIX_DATA_HOME"]
library_path = os.path.join(data_home, "voice/lib/current/libvosk.so")
model_path = os.path.join(data_home, "voice/models/small-en-us")
recognizer = VoskStt(
    rate=rate, lib_path=library_path, model_path=model_path
)
try:
    if recognizer.lib_path != os.path.abspath(library_path):
        raise SystemExit("Vosk did not open the pinned library path")
    if recognizer.model_path != os.path.abspath(model_path):
        raise SystemExit("Vosk did not open the pinned model path")
    recognizer.start_utterance()
    for offset in range(0, len(pcm), 4096):
        recognizer.feed(pcm[offset:offset + 4096])
    recognized = recognizer.end_utterance().strip()
    if not recognized:
        raise SystemExit("Vosk recognized no text from synthesized speech")
finally:
    recognizer.close()
"""


def _voice_model_catalog_validation_script() -> str:
    """Validate the download-free speech control-plane document in the guest."""
    return """\
import json
import os
import sys

document = json.load(sys.stdin)
expected = [
    (
        "small-en-us", "vosk", True, 41205931, "39.3 MiB",
        ("conf/model.conf", "am/final.mdl"),
    ),
    (
        "lgraph-en-us", "vosk", True, 130557655, "124.5 MiB",
        ("conf/model.conf", "am/final.mdl"),
    ),
    (
        "vibevoice-asr-bitnet", "vibevoice", False, 1705771590, "1.6 GiB",
        (
            "vibeasr-lm-i2_s-embed-q6_k.gguf",
            "vibeasr-vae-encoder-i8_s.gguf",
        ),
    ),
]
if type(document) is not dict:
    raise SystemExit("unknown speech-model catalog schema")
records = document.get("models")
if (document.get("schema") != "kilix.speech.models/v1"
        or type(records) is not list or len(records) != len(expected)):
    raise SystemExit("unknown speech-model catalog schema")
selected = []
for record, contract in zip(records, expected):
    if type(record) is not dict:
        raise SystemExit("speech-model catalog record is invalid")
    model, engine, supported, size, human_size, required_files = contract
    if record.get("id") != model or record.get("engine") != engine:
        raise SystemExit("speech-model catalog entries differ from the release contract")
    if (type(record.get("runtime_supported")) is not bool
            or record["runtime_supported"] is not supported):
        raise SystemExit("speech-model runtime support differs from the release contract")
    if type(record.get("download_bytes")) is not int or record["download_bytes"] != size:
        raise SystemExit("speech-model download size differs from the release contract")
    if record.get("download_size") != human_size:
        raise SystemExit("speech-model human download size differs from the release contract")
    if type(record.get("installed")) is not bool:
        raise SystemExit("speech-model installed state is invalid")
    if type(record.get("selected")) is not bool:
        raise SystemExit("speech-model selected state is invalid")
    if record["selected"]:
        selected.append(model)
    path = record.get("path")
    if type(path) is not str or not os.path.isabs(path):
        raise SystemExit("speech-model path is invalid")
    try:
        present = os.path.isdir(path) and all(
            os.path.isfile(os.path.join(path, relative))
            and os.path.getsize(os.path.join(path, relative)) > 0
            for relative in required_files
        )
    except OSError:
        present = False
    if record["installed"] is not present:
        raise SystemExit("speech-model installed state disagrees with its files")
    summary = record.get("summary")
    if type(summary) is not str or not summary.strip():
        raise SystemExit("speech-model summary is invalid")
    if record.get("install_and_default_argv") != [
        "kilix", "stt", "--install", model, "--default", model
    ]:
        raise SystemExit("speech-model install action differs from the shared contract")
default = document.get("default_model")
if default not in {item[0] for item in expected} or selected != [default]:
    raise SystemExit("speech-model default and selected record disagree")
"""


def _voice_acceptance_command(expected_policy: str) -> str:
    """Return a guest check for the declared read-aloud/dictation closure."""
    if expected_policy not in ("0", "1"):
        raise ValueError("voice policy must be 0 or 1")
    functional_smoke = (
        'KILIX_DATA_HOME="$d" '
        'PYTHONPATH="$d/voice/runtime/current/lib/kilix-voice" '
        f'timeout 180 python3 -c {shlex.quote(_voice_functional_smoke_script())}'
    )
    catalog_validation = shlex.quote(
        _voice_model_catalog_validation_script())
    command = (
        '. /etc/pleb/session.env 2>/dev/null; '
        'g="${GPU_TERMINAL_HOME:-$HOME/.local/gpu_terminal}"; '
        'k="${KILIX_STORAGE_HOME:-$g/kilix}"; '
        's="${KILIX_STATE_DIRECTORY:-$k/state}"; '
        'd="${KILIX_DATA_HOME:-$k/data}"; '
        'r="$s/kilix-voice-install.refs"; '
        'l="$d/voice/lib/current"; '
        'm="$d/voice/models/small-en-us"; '
        f'test "${{PLEBIAN_OS_INSTALL_VOICE_MODEL:-0}}" = {expected_policy} && '
        'for tool in kilix-tts kilix-stt kilix-voiced; do '
        'p="$HOME/.local/bin/$tool"; test -x "$p" || exit 1; '
        'version="$(timeout 15 "$p" --version)" || exit 1; '
        'printf \'%s\\n\' "$version" | '
        'grep -Eq "^$tool [0-9]+\\.[0-9]+\\.[0-9]+$" || exit 1; '
        'done && '
        'timeout 15 "$HOME/.local/bin/kilix-tts" --print >/dev/null && '
        'stt_report="$(timeout 15 "$HOME/.local/bin/kilix-stt" --print)" && '
        'model_catalog="$(timeout 15 "$HOME/.local/bin/kilix-stt" '
        '--models --json)" && '
        'printf \'%s\\n\' "$model_catalog" | timeout 15 python3 -c '
        f'{catalog_validation} && '
        'test -f "$r" && test ! -L "$r" && '
        'test "$(stat -c \'%u:%a:%h\' "$r")" = "$(id -u):600:1" && '
    )
    if expected_policy == "0":
        return command + (
            "grep -Fqx 'libvosk=skipped' \"$r\" && "
            "grep -Fqx 'model-small-en-us=skipped' \"$r\""
        )
    return command + (
        'printf \'%s\\n\' "$KILIX_VOICE_REF" | grep -Eq \'^[0-9a-f]{40}$\' && '
        'vsrc="${GPU_TERMINAL_SOURCE_HOME:-$g/sources}/.kilix-voice-sources/'
        'kilix-voice-$KILIX_VOICE_REF"; '
        'test -d "$vsrc/.git" && test ! -L "$vsrc" && '
        'test "$(git -C "$vsrc" rev-parse --verify HEAD)" = '
        '"$KILIX_VOICE_REF" && '
        'voice_version="$(git -C "$vsrc" show '
        '"${KILIX_VOICE_REF}:VERSION")" && '
        'printf \'%s\\n\' "$voice_version" | '
        "grep -Eq '^[0-9]+\\.[0-9]+\\.[0-9]+$' && "
        'test "$(cat "$vsrc/VERSION")" = "$voice_version" && '
        'for tool in kilix-tts kilix-stt kilix-voiced; do '
        'test "$(timeout 15 "$HOME/.local/bin/$tool" --version)" = '
        '"$tool $voice_version" || exit 1; done && '
        'printf \'%s\\n\' "$KILIX_VOICE_LIB_VERSION" | '
        "grep -Eq '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$' && "
        'case "$KILIX_VOICE_LIB_URL" in https://*) true ;; *) false ;; esac && '
        'printf \'%s\\n\' "$KILIX_VOICE_LIB_SHA256" | grep -Eq \'^[0-9a-f]{64}$\' && '
        'case "$KILIX_VOICE_MODEL_URL" in https://*) true ;; *) false ;; esac && '
        'printf \'%s\\n\' "$KILIX_VOICE_MODEL_SHA256" | grep -Eq \'^[0-9a-f]{64}$\' && '
        'test -L "$l" && '
        'library_generation="vosk-$KILIX_VOICE_LIB_VERSION-'
        '$KILIX_VOICE_LIB_SHA256" && '
        'test "$(readlink -- "$l")" = "$library_generation" && '
        'test -d "$d/voice/lib/$library_generation" && '
        'test ! -L "$d/voice/lib/$library_generation" && '
        'test -L "$m" && '
        'model_generation="vosk-model-small-en-us-0.15-'
        '$KILIX_VOICE_MODEL_SHA256" && '
        'test "$(readlink -- "$m")" = "$model_generation" && '
        'test -d "$d/voice/models/$model_generation" && '
        'test ! -L "$d/voice/models/$model_generation" && '
        'test -f "$l/libvosk.so" && test ! -L "$l/libvosk.so" && '
        'test -d "$m" && '
        'for artifact in "$l/README.kilix-provenance" '
        '"$l/LICENSE.Apache-2.0" "$m/README.kilix-provenance" '
        '"$m/LICENSE.Apache-2.0"; do '
        'test -f "$artifact" && test ! -L "$artifact" || exit 1; done && '
        'cmp -s /usr/share/common-licenses/Apache-2.0 '
        '"$l/LICENSE.Apache-2.0" && '
        'cmp -s /usr/share/common-licenses/Apache-2.0 '
        '"$m/LICENSE.Apache-2.0" && '
        "printf '%s\\n' "
        "'Kilix Voice native speech-recognition library' "
        "'Upstream: https://github.com/alphacep/vosk-api' "
        '"Version: $KILIX_VOICE_LIB_VERSION" '
        '"Wheel: $KILIX_VOICE_LIB_URL" '
        '"Wheel SHA-256: $KILIX_VOICE_LIB_SHA256" '
        "'Extracted member: vosk/libvosk.so' "
        "'License: Apache-2.0 (see LICENSE.Apache-2.0)' "
        '| cmp -s - "$l/README.kilix-provenance" && '
        "printf '%s\\n' "
        "'Vosk small US English acoustic model' "
        "'Upstream catalog: https://alphacephei.com/vosk/models' "
        '"Archive: $KILIX_VOICE_MODEL_URL" '
        '"Archive SHA-256: $KILIX_VOICE_MODEL_SHA256" '
        "'Archive directory: vosk-model-small-en-us-0.15' "
        "'License: Apache-2.0 (see LICENSE.Apache-2.0)' "
        '| cmp -s - "$m/README.kilix-provenance" && '
        "printf '%s\\n' "
        '"kilix-voice=$KILIX_VOICE_REF" '
        '"libvosk=$KILIX_VOICE_LIB_VERSION+$KILIX_VOICE_LIB_SHA256" '
        '"model-small-en-us=$KILIX_VOICE_MODEL_SHA256" '
        '| cmp -s - "$r" && '
        'grep -Fqx "KILIX_VOICE_REF=$KILIX_VOICE_REF" '
        '/etc/plebian-os/build-info.env && '
        'grep -Fqx "KILIX_VOICE_LIB_VERSION=$KILIX_VOICE_LIB_VERSION" '
        '/etc/plebian-os/build-info.env && '
        'grep -Fqx "KILIX_VOICE_LIB_URL=$KILIX_VOICE_LIB_URL" '
        '/etc/plebian-os/build-info.env && '
        'grep -Fqx "KILIX_VOICE_LIB_SHA256=$KILIX_VOICE_LIB_SHA256" '
        '/etc/plebian-os/build-info.env && '
        'grep -Fqx "KILIX_VOICE_MODEL_URL=$KILIX_VOICE_MODEL_URL" '
        '/etc/plebian-os/build-info.env && '
        'grep -Fqx "KILIX_VOICE_MODEL_SHA256=$KILIX_VOICE_MODEL_SHA256" '
        '/etc/plebian-os/build-info.env && '
        'printf \'%s\\n\' "$stt_report" | grep -Fqx \'dictation=ready\''
    ) + " && " + functional_smoke


def _transcript_acceptance_command() -> str:
    """Require the disk-safe fresh-install transcript budgets."""
    return (
        '. /etc/pleb/session.env 2>/dev/null; '
        'g="${GPU_TERMINAL_HOME:-$HOME/.local/gpu_terminal}"; '
        'f="${GPU_TERMINAL_SETTINGS_FILE:-$g/settings.conf}"; '
        'test -f "$f" && test ! -L "$f" && '
        "grep -Fqx 'KILIX_TRANSCRIPT_MAX_TOTAL=5G' \"$f\" && "
        "grep -Fqx 'KILIX_TRANSCRIPT_ARCHIVE_MAX_TOTAL=1G' \"$f\""
    )


def verify_provisioning(cfg: Config, askpass: str) -> None:
    """Prove the real installer→firstboot→session boundary: check the markers a
    correctly provisioned Plebian-OS leaves behind. Dies (nonzero) on any miss."""
    info("verifying the provisioned system (acceptance checks) …")
    # Resolve KILIX_DIR from the target's own session.env so an overridden
    # checkout location is honored (default ~/.local/gpu_terminal/sources/kilix).
    kdir = ('. /etc/pleb/session.env 2>/dev/null; '
            's="${GPU_TERMINAL_SOURCE_HOME:-$HOME/.local/gpu_terminal/sources}"; '
            'd="${KILIX_DIR:-$s/kilix}";')
    private_storage = (
        '. /etc/pleb/session.env 2>/dev/null; '
        'g="${GPU_TERMINAL_HOME:-$HOME/.local/gpu_terminal}";'
        'p="${PLEB_STORAGE_HOME:-$g/pleb}";'
        'k="${KILIX_STORAGE_HOME:-$g/kilix}";'
        'n="${KILIX95_STORAGE_HOME:-$g/kilix-95}";'
        'o="${PLEBIAN_OS_STORAGE_HOME:-$g/plebian-os}";'
        'pc="${PLEB_CONFIG_HOME:-$p/config}";'
        'ps="${PLEB_STATE_HOME:-$p/state}";'
        'px="${PLEB_CACHE_HOME:-$p/cache}";'
        'pr="${PLEB_SESSION_HOME:-$p/session}";'
        'pd="${PLEB_DATA_HOME:-$p/data}";'
        'kc="${KILIX_CONFIG_HOME:-$k/config}";'
        'ks="${KILIX_STATE_DIRECTORY:-$k/state}";'
        'kx="${KILIX_CACHE_HOME:-$k/cache}";'
        'kr="${KILIX_SESSION_HOME:-$k/session}";'
        'kb="${KILIX_BUILD_DIRECTORY:-$k/build}";'
        'kd="${KILIX_DATA_HOME:-$k/data}";'
        'kp="${KILIX_PREBUILT_HOME:-$k/prebuilt/kitty.app}";'
        'nc="${KILIX95_CONFIG_HOME:-$n/config}";'
        'ns="${KILIX95_STATE_HOME:-$n/state}";'
        'nx="${KILIX95_CACHE_HOME:-$n/cache}";'
        'nr="${KILIX95_SESSION_HOME:-$n/session}";'
        'nd="${KILIX95_DATA_HOME:-$n/data}";'
        'or="${PLEBIAN_OS_SESSION_HOME:-$o/session}";'
        'w="${KILIX_DESKTOP_DIR:-$pd/desktop}";'
        'private_dir() { anchor="$1"; d="$2"; '
        'case "$d" in "$anchor"/*) ;; *) return 1;; esac; '
        '[ -d "$d" ] && [ ! -L "$d" ] && '
        '[ "$(readlink -m -- "$d")" = "$d" ] && '
        '[ "$(stat -c \'%u\' -- "$d")" = "$(id -u)" ] && '
        '[ "$(stat -c \'%a\' -- "$d")" = 700 ]; };'
        'private_tree() { tree_root="$1"; tree_target="$2"; '
        'case "$tree_target" in "$tree_root"/*) ;; *) return 1;; esac; '
        'tree_current="$tree_root"; '
        'tree_remaining="${tree_target#"$tree_root"/}"; '
        'while [ -n "$tree_remaining" ]; do '
        'tree_component="${tree_remaining%%/*}"; '
        'tree_current="$tree_current/$tree_component"; '
        'private_dir "$tree_root" "$tree_current" || return 1; '
        'case "$tree_remaining" in */*) tree_remaining="${tree_remaining#*/}" ;; '
        '*) tree_remaining= ;; esac; done; };'
        'private_dir "$HOME" "$g" && '
        'private_dir "$g" "$p" && private_dir "$g" "$k" && '
        'private_dir "$g" "$n" && private_dir "$g" "$o" && '
        'private_dir "$p" "$pc" && private_dir "$p" "$ps" && '
        'private_dir "$p" "$px" && private_dir "$p" "$pr" && '
        'private_dir "$p" "$pd" && '
        'private_dir "$k" "$kc" && private_dir "$k" "$ks" && '
        'private_dir "$k" "$kx" && private_dir "$k" "$kr" && '
        'private_dir "$k" "$kb" && private_dir "$k" "$kd" && '
        'private_tree "$k" "$kp" && '
        'private_dir "$n" "$nc" && private_dir "$n" "$ns" && '
        'private_dir "$n" "$nx" && private_dir "$n" "$nr" && '
        'private_dir "$n" "$nd" && private_dir "$o" "$or" && '
        'case "$w" in "$pd") true ;; "$pd"/*) private_dir "$pd" "$w" ;; '
        '*) true ;; esac')
    expected_desktop = "1" if cfg.desktop else "0"
    expected_kiosk = "1" if cfg.kiosk else "0"
    expected_provider = os.environ.get("KILIX_DESKTOP_PROVIDER", "auto")
    expected_flavor = os.environ.get("KILIX_DESKTOP_FLAVOR", "95") or "95"
    expected_run_aliases = (
        "1" if env_bool("KILIX_RUN_ALIASES", True) else "0")
    expected_voice_policy = (
        "1" if env_bool("PLEBIAN_OS_INSTALL_VOICE_MODEL", False) else "0")
    expected_uv_policy = (
        "1" if env_bool("PLEBIAN_OS_INSTALL_UV", False) else "0")
    expected_uv_version = os.environ.get("PLEBIAN_OS_UV_VERSION", "")
    expected_version = os.environ.get("PLEBIAN_OS_VERSION", "")
    expected_kilix95_ref = os.environ.get("KILIX95_REF", "")
    expected_os_commit = os.environ.get(
        "PLEBIAN_OS_ACCEPTANCE_COMMIT", os.environ.get("PLEBIAN_OS_REF", ""))
    build_values = {
        "PLEBIAN_OS_VERSION": expected_version,
        "PLEBIAN_OS_COMMIT": expected_os_commit,
        "PLEBIAN_OS_DIRTY": "0",
        "PLEBIAN_OS_RELEASE_MODE": os.environ.get("PLEBIAN_OS_RELEASE_MODE", "0"),
        "PLEBIAN_OS_NETINST_SHA256": os.environ.get("PLEBIAN_OS_NETINST_SHA256", ""),
        "PLEBIAN_OS_APT_SNAPSHOT": os.environ.get("PLEBIAN_OS_APT_SNAPSHOT", ""),
        "PLEBIAN_OS_REF": os.environ.get("PLEBIAN_OS_REF", ""),
        "PLEB_REF": os.environ.get("PLEB_REF", ""),
        "KILIX_REF": os.environ.get("KILIX_REF", ""),
        "KILIX95_REF": expected_kilix95_ref,
        **{key: os.environ.get(key, "") for key in F120_ROOT_KEYS},
        "PLEBIAN_OS_UV_INSTALLER_MAX_BYTES": os.environ.get(
            "PLEBIAN_OS_UV_INSTALLER_MAX_BYTES", ""),
        "PLEBIAN_OS_SSH_ENABLED": "1",
        "PLEBIAN_OS_AUTOBOOT": "1",
        "PLEBIAN_OS_UNATTENDED_DISK": "1",
    }
    exact_build_provenance = ". /etc/plebian-os/build-info.env; " + " && ".join(
        f'test "${key}" = {shlex.quote(value)}'
        for key, value in build_values.items()
    )
    selector_contract = (
        'test -x /usr/local/bin/plebian-os-select-closure && '
        'selected="$(timeout 30 /usr/local/bin/plebian-os-select-closure --show)" && '
        f'printf \'%s\\n\' "$selected" | grep -Fqx '
        f'{shlex.quote("  PLEBIAN_OS_VERSION=" + expected_version)} && '
        f'printf \'%s\\n\' "$selected" | grep -Fqx '
        f'{shlex.quote("  PLEBIAN_OS_REF=" + expected_os_commit)}'
    )
    if expected_version == "0.2.1":
        for key in (*F120_ROOT_KEYS, "PLEBIAN_OS_UV_INSTALLER_MAX_BYTES"):
            selector_contract += (
                ' && printf \'%s\\n\' "$selected" | grep -Fqx '
                + shlex.quote("  " + key + "=" + os.environ.get(key, ""))
            )
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", expected_version):
        provision_version = (
            'test "$(/usr/local/sbin/plebian-os-provision --version)" = '
            + shlex.quote("plebian-os-provision " + expected_version)
        )
        component_versions = (
            '. /etc/pleb/session.env 2>/dev/null; '
            'test "$(/usr/local/bin/pleb --version)" = '
            + shlex.quote("pleb " + expected_version)
            + ' && test "$("$KILIX_DIR/kilix" --kilix-version)" = '
            + shlex.quote(expected_version)
        )
        if expected_kilix95_ref:
            component_versions += (
                ' && test "$(python3 "$KILIX95_DIR/main.py" --version)" = '
                + shlex.quote("kilix-95 " + expected_version)
            )
    else:
        provision_version = (
            "/usr/local/sbin/plebian-os-provision --version | "
            "grep -Eq '^plebian-os-provision [0-9]+\\.[0-9]+\\.[0-9]+$'"
        )
        component_versions = (
            '. /etc/pleb/session.env 2>/dev/null; '
            "/usr/local/bin/pleb --version | "
            "grep -Eq '^pleb [0-9]+\\.[0-9]+\\.[0-9]+$' && "
            '"$KILIX_DIR/kilix" --kilix-version | '
            "grep -Eq '^[0-9]+\\.[0-9]+\\.[0-9]+$'"
        )
        if expected_kilix95_ref:
            component_versions += (
                ' && python3 "$KILIX95_DIR/main.py" --version | '
                "grep -Eq '^kilix-95 [0-9]+\\.[0-9]+\\.[0-9]+$'"
            )
    session_contract = (
        '. /etc/pleb/session.env 2>/dev/null; '
        f'test "${{PLEB_DESKTOP:-0}}" = {shlex.quote(expected_desktop)} && '
        f'test "${{PLEB_RESPAWN:-0}}" = {shlex.quote(expected_kiosk)} && '
        f'test "${{KILIX_DESKTOP_PROVIDER:-auto}}" = {shlex.quote(expected_provider)} && '
        f'test "${{KILIX_DESKTOP_FLAVOR:-95}}" = {shlex.quote(expected_flavor)} && '
        f'test "${{KILIX_RUN_ALIASES:-1}}" = {shlex.quote(expected_run_aliases)}'
    )
    session_exports = (
        '. /etc/pleb/session.env 2>/dev/null; '
        f'env | grep -Fqx {shlex.quote("KILIX_DESKTOP_PROVIDER=" + expected_provider)} && '
        f'env | grep -Fqx {shlex.quote("KILIX_DESKTOP_FLAVOR=" + expected_flavor)} && '
        f'env | grep -Fqx {shlex.quote("KILIX95_REF=" + expected_kilix95_ref)} && '
        f'env | grep -Fqx {shlex.quote("KILIX_RUN_ALIASES=" + expected_run_aliases)}'
    )
    build_session_contract = (
        '. /etc/plebian-os/build-info.env 2>/dev/null; '
        f'test "$PLEBIAN_OS_DESKTOP" = {shlex.quote(expected_desktop)} && '
        f'test "$PLEBIAN_OS_KIOSK" = {shlex.quote(expected_kiosk)} && '
        f'test "$KILIX_DESKTOP_PROVIDER" = {shlex.quote(expected_provider)} && '
        f'test "$KILIX_DESKTOP_FLAVOR" = {shlex.quote(expected_flavor)} && '
        f'test "$KILIX_RUN_ALIASES" = {shlex.quote(expected_run_aliases)}'
    )
    chromium_alias_script = (
        'test "$(type -t chromium)" = alias && '
        "alias chromium | grep -Fq ' run chromium'")
    gui_routing_environment = (
        '. /etc/pleb/session.env 2>/dev/null; '
        'export KILIX_RUN_ALIASES XDG_SESSION_DESKTOP=pleb; ')
    gui_routing_contract = (
        gui_routing_environment +
        'bash --rcfile "$KILIX_DIR/config/kilix.bashrc" -ic '
        + shlex.quote(chromium_alias_script))
    kilix_bashrc_routing_contract = (
        gui_routing_environment +
        'python3 "$KILIX_DIR/tests/test_kilix_bashrc.py"')
    kilix_desktop_routing_contract = (
        gui_routing_environment +
        'python3 "$KILIX_DIR/desktop/tests/test_shell_xpane.py"')
    kilix95_routing_contract = (
        gui_routing_environment +
        # Use the provider's supported isolated runner. It prepares a pinned
        # temporary libkilix-state exactly as a direct test launch requires;
        # the raw test module only inherits that library inside `kilix desktop`.
        'python3 "$KILIX95_DIR/tests/run.py" shell_xpane')
    visible_kilix_chrome = (
        "grep -Fq 'KILIX_ARGV=(--start-as=maximized -o hide_window_decorations=yes)' "
        "/usr/local/bin/pleb-session && "
        "! grep -Fq 'KILIX_ARGV=(--start-as=fullscreen)' "
        "/usr/local/bin/pleb-session"
    )
    first_page_desktop = (
        "grep -Fq 'DESKTOP_ARGS=(env KILIX_IN_OVERLAY=1' "
        "/usr/local/bin/pleb-session && "
        "grep -Fq '\"$KILIX\" desktop)' /usr/local/bin/pleb-session"
    )
    coordinated_checkouts = (kdir +
        ' o="${PLEBIAN_OS_DIR:-$s/plebian-os}";'
        ' p="${PLEB_DIR:-$s/pleb}";'
        ' n="${KILIX95_DIR:-$s/kilix-desktops/kilix-95}";'
        ' test -d "$o/.git" && test -d "$p/.git" &&'
        ' test -d "$d/.git" && test -d "$n/.git"')
    for ref_key, dir_var in (
            ("PLEBIAN_OS_REF", "o"), ("PLEB_REF", "p"),
            ("KILIX_REF", "d"), ("KILIX95_REF", "n")):
        ref = os.environ.get(ref_key, "")
        if re.fullmatch(r"[0-9a-fA-F]{40}", ref):
            coordinated_checkouts += (
                f' && test "$(git -C "${dir_var}" rev-parse HEAD)" = '
                f'{shlex.quote(ref.lower())}'
            )
    provenance_values = {
        "PLEBIAN_OS_VERSION": expected_version,
        "PLEBIAN_OS_COMMIT": expected_os_commit,
        "PLEB_COMMIT": os.environ.get("PLEB_REF", ""),
        "KILIX_COMMIT": os.environ.get("KILIX_REF", ""),
        "KILIX95_COMMIT": expected_kilix95_ref,
        "PLEBIAN_OS_INSTALL_UV": expected_uv_policy,
        "PLEBIAN_OS_UV_VERSION": expected_uv_version,
        "PLEBIAN_OS_UV_INSTALLER_MAX_BYTES": os.environ.get(
            "PLEBIAN_OS_UV_INSTALLER_MAX_BYTES", ""),
        **{key: os.environ.get(key, "") for key in F120_ROOT_KEYS},
    }
    exact_source_provenance = " && ".join(
        f"grep -Fqx {shlex.quote(key + '=' + value)} "
        "/var/lib/plebian-os/versions.env"
        for key, value in provenance_values.items()
    )
    uv_contract = (
        f'test {shlex.quote(expected_uv_policy)} = 0 || ('
        'test -x /usr/local/bin/uv && test -x /usr/local/bin/uvx && '
        f'case "$(/usr/local/bin/uv --version)" in '
        f'{shlex.quote("uv " + expected_uv_version)}|'
        f'{shlex.quote("uv " + expected_uv_version + " (")}*\\)) true ;; '
        '*) false ;; esac)'
    )
    checks = [
        ("provisioned marker",   "test -f /var/lib/plebian-os/provisioned"),
        ("exact build provenance", exact_build_provenance),
        ("provision version",    provision_version),
        ("component versions",   component_versions),
        ("package provenance",   "test -s /var/lib/plebian-os/packages.list"),
        ("source provenance",    exact_source_provenance),
        ("apt provenance",       "test -s /var/lib/plebian-os/apt-sources.list"),
        ("uv closure",           uv_contract),
        ("coordinated checkouts", coordinated_checkouts),
        ("private storage roots", private_storage),
        ("pleb recovery guide", "test -r /usr/local/share/doc/pleb/RECOVERY.md"),
        ("pleb xsession",        "test -f /usr/share/xsessions/pleb.desktop"),
        ("pleb-session binary",  "test -x /usr/local/bin/pleb-session"),
        ("session.env",          "test -f /etc/pleb/session.env"),
        ("session selection",    session_contract),
        ("session exports",      session_exports),
        ("session provenance",   build_session_contract),
        ("GUI routes in Kilix", gui_routing_contract),
        ("Kilix shell GUI routing tests", kilix_bashrc_routing_contract),
        ("Kilix desktop GUI routing tests", kilix_desktop_routing_contract),
        ("Kilix-95 GUI routing tests", kilix95_routing_contract),
        ("voice closure policy", _voice_acceptance_command(expected_voice_policy)),
        ("transcript disk budget", _transcript_acceptance_command()),
        ("visible kilix chrome", visible_kilix_chrome),
        ("lightdm pleb default", "grep -q user-session=pleb /etc/lightdm/lightdm.conf.d/50-plebian-os.conf"),
        ("update helper",        "test -x /usr/local/bin/plebian-os-update"),
        ("closure selector",     selector_contract),
        (
            "optional Ollama converter installer",
            "test -x /usr/local/sbin/plebian-os-install-ollama-converter && "
            "timeout 30 /usr/local/sbin/plebian-os-install-ollama-converter "
            "--dry-run | grep -Fqx '  sha256: "
            "8759ab3d3a92d86ba3ba24fab7e6adde08eaf2f941e6c79118373e4f41e0af8c'",
        ),
        (
            "optional Kilix Vulkan TTS installer",
            "test -x /usr/local/sbin/plebian-os-install-kilix-vulkan-tts && "
            "timeout 30 /usr/local/sbin/plebian-os-install-kilix-vulkan-tts "
            "--dry-run | grep -Fqx '  worker source sha256: "
            "e8c7ecd2d2458962666fdc560b40f5ed754e3e7c126400dd1f914a4bb50dc964'",
        ),
        (
            "optional Kilix Ollama runtime installer",
            "test -x /usr/local/sbin/plebian-os-install-kilix-ollama-runtime && "
            "timeout 30 /usr/local/sbin/plebian-os-install-kilix-ollama-runtime "
            "--dry-run | grep -Fqx '  Unix listener patch sha256: "
            "ad1ba7475946a22e371156c06cbb8dba58d8fd23f916a3bcffa8d937bf35ccde'",
        ),
        ("firstboot disabled",   "! systemctl is-enabled plebian-os-firstboot.service >/dev/null 2>&1"),
        ("temporary sudo gone",  "test ! -e /etc/sudoers.d/plebian-os-provision"),
    ]
    if cfg.desktop:
        checks.append(("first-page Kilix desktop", first_page_desktop))
    # The clickable fork engine only exists when fork-building is on (the default);
    # with it off, provisioning ships the prebuilt engine, so check that instead.
    fork_on = os.environ.get("PLEBIAN_OS_BUILD_KILIX_FORK", "1") not in ("0", "no", "false", "off")
    if fork_on:
        checks.append(("kilix fork generation", kdir +
                       ' k="${KILIX_STORAGE_HOME:-$HOME/.local/gpu_terminal/kilix}";'
                       ' ks="${KILIX_STATE_DIRECTORY:-$k/state}";'
                       ' kb="${KILIX_BUILD_DIRECTORY:-$k/build}";'
                       ' ps="${PLEB_STATE_HOME:-$HOME/.local/gpu_terminal/pleb/state}";'
                       ' test -L "$kb/current" &&'
                       ' g="$(readlink -- "$kb/current")" &&'
                       ' printf \'%s\\n\' "$g" | grep -Eq \'^generations/build\\.[A-Za-z0-9]+$\' &&'
                       ' test -d "$kb/$g" && test ! -L "$kb/$g" &&'
                       ' br="$(cd "$kb" && pwd -P)" &&'
                       ' gr="$(cd "$kb/$g" && pwd -P)" &&'
                       ' test "$gr" = "$br/$g" &&'
                       ' test "$(stat -c \'%u\' "$kb/$g")" = "$(id -u)" &&'
                       ' f="$kb/current/src/kitty/launcher/kitty";'
                       ' t="$kb/current/src/kitty/launcher/kitten";'
                       ' r="$(cd "$d" && pwd -P)" &&'
                       ' h="$(git -C "$d/src" rev-parse --verify HEAD)" &&'
                       ' test -n "$h" &&'
                       ' test -f "$f" && test ! -L "$f" && test -x "$f" &&'
                       ' test -f "$t" && test ! -L "$t" && test -x "$t" &&'
                       ' timeout 15 "$t" --version >/dev/null 2>&1 &&'
                       ' test -f "$kb/current/source-id" &&'
                       ' test ! -L "$kb/current/source-id" &&'
                       ' printf \'%s\\n\' "$h" | cmp -s - "$kb/current/source-id" &&'
                       ' test -f "$ks/fork-built-ref" &&'
                       ' test ! -L "$ks/fork-built-ref" &&'
                       ' test "$(stat -c \'%u\' "$ks/fork-built-ref")" = "$(id -u)" &&'
                       ' test "$(stat -c \'%a\' "$ks/fork-built-ref")" = 600 &&'
                       ' test "$(stat -c \'%h\' "$ks/fork-built-ref")" = 1 &&'
                       ' printf \'%s\\t%s\\n\' "$r" "$h" | cmp -s - "$ks/fork-built-ref" &&'
                       ' test ! -e "$ps/kilix-fork-built-ref" &&'
                       ' test ! -L "$ps/kilix-fork-built-ref" &&'
                       ' q="$("$d/kilix" --which 2>/dev/null)" &&'
                       ' e="$(printf \'%s\\n\' "$q" | sed -n \'1p\')" &&'
                       ' test "$e" = "$f"'))
    else:
        checks.append(("kilix engine", kdir + ' test -x "$d/kilix"'))
    failed = []
    check_timeouts = {"Kilix-95 GUI routing tests": 60}
    for name, cmd in checks:
        r = ssh(cfg, cmd, askpass,
                timeout=check_timeouts.get(name, 15))
        ok = r is not None and r.returncode == 0
        detail = ""
        if not ok:
            if r is None:
                detail = "SSH check timed out"
            else:
                detail = "\n".join(
                    output.strip()
                    for output in (r.stdout, r.stderr)
                    if output.strip()
                ) or f"guest command exited {r.returncode}"
        if _RECORDER is not None:
            _RECORDER.check(name, ok, detail)
        info(f"  [{'ok' if ok else '!!'}] {name}")
        if not ok:
            failed.append(name)
    if failed:
        die("acceptance verification FAILED: " + ", ".join(failed))
    if env_bool("PLEBIAN_OS_VERIFY_UPDATE_ROLLBACK", False):
        verify_update_rollback(cfg, askpass)
    if env_bool("PLEBIAN_OS_VERIFY_SUCCESSFUL_UPDATE", False):
        verify_successful_update(cfg, askpass)
    if env_bool("PLEBIAN_OS_VERIFY_CATALOG_BUILDS", False):
        verify_catalog_builds(cfg, askpass)
    info(c("1;32", "acceptance verification passed."))

# ── summary ──────────────────────────────────────────────────────────────────
def final_summary(cfg: Config, iso: Path) -> None:
    print(c("1;32", "\n✓ Plebian-OS VirtualBox image is ready.\n"))
    print(f"  VM        : {cfg.name}")
    if cfg.interactive_installer:
        print("  login     : chosen interactively in Debian Installer")
    elif cfg.credential_generated:
        print(f"  login     : {cfg.username} / (harness credential expired; change at next login)")
    elif cfg.password_hash:
        print(f"  login     : {cfg.username} / (credential supplied as a protected crypt hash)")
    else:
        print(f"  login     : {cfg.username} / (credential supplied privately)")
    if not cfg.interactive_installer:
        print(f"  session   : {'desktop provider in Kilix page 1' if cfg.desktop else 'Kilix shell in page 1'}"
              f"{' (autologin)' if cfg.kiosk else ' (greeter)'}")
    print(f"  firmware  : {cfg.firmware.upper()}")
    print(f"  start GUI : VBoxManage startvm {cfg.name} --type gui")
    if cfg.wait:
        print(f"  ssh in    : ssh -p {cfg.ssh_port} {cfg.username}@127.0.0.1")
    print(f"  ISO       : {iso}")
    if _RECORDER is not None:
        print(f"  report    : {_RECORDER.path}")
        print(f"  report sha: {_RECORDER.path}.sha256")
    print()


def acceptance_report_initial(cfg: Config, args) -> dict:
    pin_keys = (
        "PLEBIAN_OS_ACCEPTANCE_RELEASE",
        "PLEBIAN_OS_ACCEPTANCE_COMMIT",
        "PLEBIAN_OS_ACCEPTANCE_MANIFEST_SHA256",
        "PLEBIAN_OS_VERSION",
        "PLEBIAN_OS_RELEASE",
        "PLEBIAN_OS_RELEASE_MODE",
        "PLEBIAN_OS_REF",
        "PLEB_REF",
        "KILIX_REF",
        "KILIX95_REF",
        *F120_ROOT_KEYS,
        "PLEBIAN_OS_NETINST_URL",
        "PLEBIAN_OS_NETINST_SHA256",
        "PLEBIAN_OS_APT_SNAPSHOT",
        "PLEBIAN_OS_INSTALL_UV",
        "PLEBIAN_OS_UV_VERSION",
        "PLEBIAN_OS_UV_INSTALLER_SHA256",
        "PLEBIAN_OS_UV_INSTALLER_MAX_BYTES",
        "KILIX_PREBUILT_VERSION",
        "KILIX_PREBUILT_SHA256",
        "PLEBIAN_OS_KILIX_GO_VERSION",
        "PLEBIAN_OS_KILIX_GO_SHA256_AMD64",
        "PLEBIAN_OS_KILIX_GO_SHA256_ARM64",
        "KILIX_VOICE_REF",
        "KILIX_VOICE_LIB_VERSION",
        "KILIX_VOICE_LIB_SHA256",
        "KILIX_VOICE_MODEL_SHA256",
    )
    vbox_version = run(["VBoxManage", "--version"], capture=True).stdout.strip()
    try:
        repo_commit = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        repo_dirty = bool(subprocess.run(
            ["git", "-C", str(REPO), "status", "--porcelain",
             "--untracked-files=normal"],
            check=True, capture_output=True, text=True,
        ).stdout.strip())
    except subprocess.CalledProcessError:
        repo_commit, repo_dirty = "", None
    return {
        "kind": "prebuilt-iso" if args.iso else "instrumented-acceptance-derivative",
        "repository": {"commit": repo_commit, "dirty": repo_dirty},
        "release_inputs": {
            key: os.environ.get(key, "") for key in pin_keys
        },
        "host": {
            "virtualbox_version": vbox_version,
            "python_version": sys.version.split()[0],
        },
        "vm": {
            "name": cfg.name,
            "identity_profile": (
                "interactive-installer" if cfg.interactive_installer else "automated"),
            "username": cfg.username,
            "hostname": cfg.hostname,
            "ram_mb": cfg.ram_mb,
            "cpus": cfg.cpus,
            "vram_mb": cfg.vram_mb,
            "accelerate_3d": cfg.accelerate_3d,
            "firmware": cfg.firmware,
            "disk_gb": cfg.disk_gb,
            "desktop": cfg.desktop,
            "kiosk": cfg.kiosk,
            "nopasswd_sudo": cfg.nopasswd_sudo,
            "ssh_host_port": cfg.ssh_port,
            "headless": not cfg.gui,
            "wait": cfg.wait,
        },
        "enabled_gates": {
            "post_provision": not args.no_verify,
            "catalog_clean_builds": env_bool(
                "PLEBIAN_OS_VERIFY_CATALOG_BUILDS", False),
            "induced_update_rollback": env_bool(
                "PLEBIAN_OS_VERIFY_UPDATE_ROLLBACK", False),
            "successful_update_restart": env_bool(
                "PLEBIAN_OS_VERIFY_SUCCESSFUL_UPDATE", False),
        },
    }

# ── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    global _RECORDER
    ap = argparse.ArgumentParser(description="Build a Plebian-OS VM image from scratch.")
    ap.add_argument("--target", choices=["virtualbox", "vbox", "qemu", "docker"],
                    default="virtualbox", help="image type (only virtualbox today)")
    ap.add_argument("--name"); ap.add_argument("--username"); ap.add_argument("--fullname")
    ap.add_argument("--hostname")
    ap.add_argument("--password", help=argparse.SUPPRESS)
    ap.add_argument("--password-file", type=Path,
                    help="read the automated login password from an owner-mode-0600 file")
    ap.add_argument("--password-hash-file", type=Path,
                    help="read a crypt hash from an owner-mode-0600 file (requires --no-wait)")
    ap.add_argument("--generate-one-time-password", action="store_true",
                    help="generate a harness-only password and expire it after verification")
    ap.add_argument("--expire-credential-after-verification", action="store_true",
                    help="treat --password-file as one-time and expire it after verification")
    ap.add_argument("--ram", type=int, help="MB"); ap.add_argument("--cpus", type=int)
    ap.add_argument("--vram", type=int, default=None,
                    help="video RAM in MB (VirtualBox caps this at 256 on this host)")
    ap.add_argument("--accelerate-3d", action="store_true",
                    help="enable VirtualBox 3D acceleration")
    ap.add_argument("--firmware", choices=["bios", "efi"], default=None,
                    help="guest firmware (default: bios)")
    ap.add_argument("--disk", type=int, help="GB")
    ap.add_argument("--session", choices=["desktop", "shell"])
    ap.add_argument("--kiosk", dest="kiosk", action="store_true", default=None,
                    help="autologin straight into Pleb and respawn Kilix on exit")
    ap.add_argument("--no-kiosk", dest="kiosk", action="store_false",
                    help="show the login greeter instead of autologin")
    ap.add_argument("--sudo-nopasswd", dest="nopasswd_sudo", action="store_true",
                    default=None, help="passwordless sudo for the automated user")
    ap.add_argument("--no-sudo-nopasswd", dest="nopasswd_sudo", action="store_false",
                    help="require a password for sudo")
    ap.add_argument("--port", type=int, help="SSH host port -> guest 22")
    ap.add_argument("--iso", type=Path, help="use this prebuilt ISO (skip building)")
    ap.add_argument(
        "--interactive-installer", action="store_true",
        help=("prebuilt ISO collects guest identity itself; requires --iso, "
              "--no-wait, and --no-verify"))
    ap.add_argument(
        "--out", type=Path, default=None,
        help=("ISO output path when building (release default: "
              "plebian-os-<version>-amd64.iso; otherwise "
              "plebian-os-<name>.iso)"))
    ap.add_argument("--gui", action="store_true", help="start the VM with a window")
    ap.add_argument("--no-wait", action="store_true", help="don't block on provisioning")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the post-provision acceptance checks")
    ap.add_argument("--replace", action="store_true",
                    help="replace an existing VM and generated ISO/report outputs")
    ap.add_argument("--report", type=Path,
                    help="write a checksummed JSON acceptance report")
    ap.add_argument(
        "--timeout", type=int, default=DEFAULT_PROVISION_TIMEOUT_MINUTES,
        help=("combined minutes to wait for Debian installation and firstboot "
              f"(default: {DEFAULT_PROVISION_TIMEOUT_MINUTES})"))
    ap.add_argument("-y", "--yes", action="store_true", help="accept defaults, no prompts")
    ap.add_argument("--dry-run", action="store_true", help="show the plan; build nothing")
    args = ap.parse_args()

    target = "virtualbox" if args.target in ("virtualbox", "vbox") else args.target
    if target != "virtualbox":
        die(f"target {target!r} is not implemented yet — only 'virtualbox' for now.")

    # preflight
    if not args.dry_run:
        tools = ["VBoxManage"]
        if not args.iso:
            tools.extend(("xorriso", "openssl"))
        if not args.no_wait:
            tools.append("ssh")
        for tool in tools:
            if not have(tool):
                die(f"{tool} is required but not installed.")
    if not PRESEED_TEMPLATE.exists() or not REMASTER.exists():
        die("run this from a Plebian-OS checkout (preseed/ + build/ not found).")

    # PLEBIAN_OS_RELEASE=<ver> pins every moving component from releases/<ver>.env.
    apply_release_manifest()

    if args.interactive_installer:
        if not args.iso or not args.no_wait or not args.no_verify:
            die("--interactive-installer requires --iso, --no-wait, and --no-verify")
        identity_options = (
            args.username, args.fullname, args.hostname, args.password,
            args.password_file, args.password_hash_file,
        )
        if (any(value is not None for value in identity_options)
                or args.generate_one_time_password
                or args.expire_credential_after_verification
                or args.session is not None or args.kiosk is not None
                or args.nopasswd_sudo is not None):
            die("--interactive-installer refuses automated identity, credential, session, and sudo options")
        for key in ("IMAGE_PASSWORD", "RANDOM_PASSWORD"):
            if key in os.environ:
                die(f"--interactive-installer refuses retired {key}")

    if args.iso:
        if args.interactive_installer:
            warn("using a prebuilt interactive ISO: Debian Installer collects the "
                 "guest identity; no credential is supplied by this harness")
        else:
            warn("using a prebuilt automated ISO: builder identity options are NOT "
                 "applied; protected credentials entered here must match that ISO")
    cfg = gather_config(args)
    if args.iso and cfg.credential_generated:
        die("--generate-one-time-password cannot match a prebuilt ISO; use its protected password file")
    confirm_summary(cfg, args.yes)

    if args.timeout <= 0:
        die("--timeout must be greater than zero")

    out: Path | None = None
    if args.iso:
        iso = args.iso.resolve()
        if not iso.exists() and not args.dry_run:
            die(f"--iso not found: {iso}")
    else:
        out = (args.out or (storage_dir("artifacts") /
                            default_iso_filename(cfg.name))).resolve()
        iso = out

    if args.dry_run:
        if not args.iso:
            build_iso(cfg, None, iso, True)
        info("dry run: would now create + boot the VM and wait for provisioning.")
        return

    # Refuse before spending an hour rebuilding an ISO. Replacement is one
    # explicit operation covering the VM and generated evidence for this run.
    if vbox_exists(cfg.name) and not args.replace:
        die(f"a VM named {cfg.name!r} already exists; pass --replace explicitly")
    if out is not None and out.exists() and not args.replace:
        die(f"ISO output already exists: {out}; pass --replace explicitly")
    report_path = args.report.resolve() if args.report else None
    if report_path is not None and not args.replace:
        existing_report_outputs = [
            path for path in (report_path, Path(str(report_path) + ".sha256"))
            if path.exists()
        ]
        if existing_report_outputs:
            die("acceptance report output already exists: "
                f"{existing_report_outputs[0]}; pass --replace explicitly")

    if report_path is not None:
        _RECORDER = AcceptanceRecorder(
            report_path, acceptance_report_initial(cfg, args))
        _RECORDER.stage("preflight")

    if out is not None:
        preseed = generate_preseed(cfg, enable_ssh=True)
        iso = build_iso(cfg, preseed, out, False)
        if _RECORDER is not None:
            _RECORDER.stage("instrumented ISO built")
    if _RECORDER is not None:
        _RECORDER.set_iso(iso)

    vbox_create(cfg, iso, replace=args.replace, assume_yes=args.yes)
    if _RECORDER is not None:
        _RECORDER.stage("VirtualBox VM created")
    vbox_start(cfg)
    if _RECORDER is not None:
        _RECORDER.stage("VirtualBox VM started")

    if not cfg.wait:
        info(f"VM {cfg.name!r} started; not waiting (--no-wait).")
        if _RECORDER is not None:
            _RECORDER.complete("vm-started-no-verification")
        final_summary(cfg, iso)
        return

    with _askpass_for(cfg.password) as askpass:
        provisioning_ready = False
        try:
            wait_for_provisioning(cfg, args.timeout * 60, askpass)
            provisioning_ready = True
            if _RECORDER is not None:
                _RECORDER.stage("installer and firstboot completed")
            vbox_detach_iso(cfg)
            if _RECORDER is not None:
                _RECORDER.stage("installer ISO detached")
            if not args.no_verify:
                verify_provisioning(cfg, askpass)
                if _RECORDER is not None:
                    _RECORDER.stage("post-provision acceptance completed")
        finally:
            # Verification can fail after the guest is ready. Do not leave a
            # harness-owned credential usable merely because a later gate did.
            if cfg.credential_generated and provisioning_ready:
                expire_generated_credential(cfg, askpass)
                if _RECORDER is not None:
                    _RECORDER.stage("generated harness credential expired")
    if _RECORDER is not None:
        _RECORDER.complete(
            "passed" if not args.no_verify else "completed-without-verification"
        )
    final_summary(cfg, iso)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        die("interrupted.")
    except subprocess.CalledProcessError as exc:
        command = " ".join(shlex.quote(str(part)) for part in exc.cmd)
        die(f"command failed with status {exc.returncode}: {command}")
    except Exception as exc:
        if _RECORDER is not None:
            _RECORDER.fail(f"unexpected {type(exc).__name__}: {exc}")
        raise
