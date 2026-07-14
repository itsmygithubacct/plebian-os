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
import os
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PRESEED_TEMPLATE = REPO / "preseed" / "preseed.cfg"
REMASTER = REPO / "build" / "remaster-iso.sh"


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
    seen: set[str] = set()
    for raw in manifest.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            die(f"invalid release manifest line: {raw}")
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip().strip('"')
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            die(f"invalid release manifest key: {key}")
        if key in seen:
            die(f"duplicate release manifest key: {key}")
        seen.add(key)
        if val == "REPLACE_ME":
            die(f"release {release}: {key} is still REPLACE_ME in "
                f"releases/{release}.env — fill it before building (see RELEASING.md)")
        os.environ[key] = val
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


def validate_identity(*, name: str, username: str, fullname: str,
                      password: str, hostname: str) -> None:
    """Reject values that Debian preseed or VirtualBox would reinterpret."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name):
        die("VM/image name must use 1-64 letters, digits, dots, underscores, or hyphens")
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
        die("username must match [a-z_][a-z0-9_-]{0,31}")
    reserved = {
        "root", "daemon", "bin", "sys", "sync", "games", "man", "lp",
        "mail", "news", "uucp", "proxy", "www-data", "backup", "list",
        "irc", "gnats", "nobody", "_apt", "messagebus", "polkitd",
        "sshd", "lightdm", "systemd-network", "systemd-timesync",
    }
    if username.startswith("_") or username in reserved:
        die(f"username {username!r} is reserved for a system account")
    if (not 1 <= len(fullname) <= 128 or any(ord(ch) < 32 for ch in fullname)
            or ":" in fullname or "\\" in fullname):
        die("full name must be 1-128 printable characters with no colon or backslash")
    if not password or any(ch in password for ch in "\r\n\0"):
        die("password must be nonempty and contain no newline or NUL")
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
    disk_gb: int
    desktop: bool          # PLEB_DESKTOP: boot into `kilix desktop`
    kiosk: bool            # PLEBIAN_OS_KIOSK: autologin straight into Pleb
    nopasswd_sudo: bool    # PLEBIAN_OS_NOPASSWD_SUDO: passwordless sudo for the user
    ssh_port: int
    gui: bool              # start with a window vs headless
    wait: bool             # block until provisioning finishes

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


def gather_config(args) -> Config:
    p = Prompter(args.yes)
    print(c("1", "\nPlebian-OS → VirtualBox image builder\n"))
    if not args.yes:
        print("Answer the prompts (Enter accepts the [default]).\n")

    name     = args.name     or p.ask("VM name", "plebian")
    username = args.username or p.ask("username", "pleb")
    fullname = args.fullname or p.ask("full name", "Plebian User")
    if args.password is not None:
        password = args.password
    elif args.yes:
        password = generated_password()
        warn(f"--yes without --password: generated one-time password for {username}: "
             f"{password}")
    else:
        # VM images always enable sshd for the provisioning waiter, so unlike the
        # offline USB default they require an operator-chosen nonempty secret.
        password = p.ask_password("")
    hostname = args.hostname or p.ask("hostname", name)
    ram_mb   = args.ram      or p.ask("RAM (MB)", default_ram_mb(),
                                      cast=int, validate=lambda v: v >= 512)
    cpus     = args.cpus     or p.ask("vCPUs", default_cpus(),
                                      cast=int, validate=lambda v: v >= 1)
    vram_mb  = args.vram if args.vram is not None else 128
    if vram_mb > 256:
        warn(f"VirtualBox rejects VRAM above 256 MB on this host; requested {vram_mb}, using 256")
        vram_mb = 256
    disk_gb  = args.disk     or p.ask("disk (GB, sparse)", 200,
                                      cast=int, validate=lambda v: v >= 8)
    if args.session:
        desktop = args.session == "desktop"
    else:
        desktop = p.ask_bool("boot into the configured kilix desktop (vs plain shell)", True)
    kiosk    = args.kiosk if args.kiosk is not None \
                          else p.ask_bool("autologin (kiosk) instead of a login screen", True)
    nopasswd = args.nopasswd_sudo if args.nopasswd_sudo is not None \
                          else p.ask_bool(f"passwordless sudo for {username}", True)
    ssh_port = args.port     or p.ask("SSH host port (forwarded to guest 22)", free_port(),
                                      cast=int, validate=lambda v: 1 <= v <= 65535)

    validate_identity(name=name, username=username, fullname=fullname,
                      password=password, hostname=hostname)
    if ram_mb < 512 or cpus < 1 or vram_mb < 1 or disk_gb < 8:
        die("resources must be RAM >= 512 MB, CPUs >= 1, VRAM >= 1 MB, disk >= 8 GB")
    if ram_mb < 4096:
        warn(f"RAM {ram_mb} MB is below the 4096 MB release-tested build baseline; "
             "firstboot fork compilation may exhaust memory")
    if not 1 <= ssh_port <= 65535:
        die("SSH host port must be between 1 and 65535")
    return Config(name=name, username=username, fullname=fullname, password=password,
                  hostname=hostname, ram_mb=ram_mb, cpus=cpus,
                  vram_mb=vram_mb, accelerate_3d=args.accelerate_3d,
                  disk_gb=disk_gb,
                  desktop=desktop, kiosk=kiosk, nopasswd_sudo=nopasswd, ssh_port=ssh_port,
                  gui=args.gui, wait=not args.no_wait)


def confirm_summary(cfg: Config, assume_yes: bool) -> None:
    print(c("1", "\nAbout to build:"))
    rows = [
        ("VM name", cfg.name), ("username", cfg.username), ("hostname", cfg.hostname),
        ("RAM", f"{cfg.ram_mb} MB"), ("vCPUs", cfg.cpus),
        ("VRAM", f"{cfg.vram_mb} MB"),
        ("3D accel", "on" if cfg.accelerate_3d else "off"),
        ("disk", f"{cfg.disk_gb} GB (sparse)"),
        ("session", "kilix desktop" if cfg.desktop else "plain kilix shell"),
        ("login", "autologin (kiosk)" if cfg.kiosk else "greeter"),
        ("sudo", "passwordless" if cfg.nopasswd_sudo else "password required"),
        ("SSH", f"ssh -p {cfg.ssh_port} {cfg.username}@127.0.0.1"),
        ("display", "GUI window" if cfg.gui else "headless"),
    ]
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

    sub(r"^(d-i passwd/username string ).*$",      r"\g<1>" + cfg.username)
    sub(r"^(d-i passwd/user-fullname string ).*$", r"\g<1>" + cfg.fullname)
    sub(r"^(d-i netcfg/get_hostname string ).*$",  r"\g<1>" + cfg.hostname)

    # Replace the template's default 'plebian' password with the chosen one,
    # hashed with openssl (keeps the plaintext off the ISO). A
    # lambda repl keeps regex-special characters in the crypt hash literal.
    # The offline USB template may deliberately use 'plebian' (and its desktop
    # offers the one-time transition helper), but VM/SSH entry points reject it.
    secret, _crypted = crypt_password(cfg.password)
    sub(r"^d-i passwd/user-password password .*$",
        lambda _m: "d-i passwd/user-password-crypted password " + secret)
    sub(r"^d-i passwd/user-password-again password .*\n", "")

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
        "PLEBIAN_OS_TARGET_SOURCE_HOME", f"{home}/gpu_terminal")
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
         "--firmware", "bios",
         "--rtcuseutc", "on", "--nic1", "nat",
         "--natpf1", f"ssh,tcp,127.0.0.1,{cfg.ssh_port},,22",
         # audio out is OFF on a fresh VM — enable it so the desktop's system
         # sounds / media actually reach the host speakers.
         "--audio-driver", "default", "--audio-enabled", "on", "--audio-out", "on",
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
         "--port", 1, "--device", 0, "--type", "dvddrive", "--medium", str(iso)])

def vbox_start(cfg: Config) -> None:
    run(["VBoxManage", "startvm", cfg.name,
         "--type", "gui" if cfg.gui else "headless"])

def vbox_detach_iso(cfg: Config) -> None:
    subprocess.run(["VBoxManage", "storageattach", cfg.name, "--storagectl", "SATA",
                   "--port", "1", "--device", "0", "--type", "dvddrive", "--medium", "none"],
                  capture_output=True)

# ── SSH into the guest (password auth via SSH_ASKPASS; no sshpass needed) ─────
def _askpass_for(pw: str) -> str:
    session = storage_dir("session")
    session.mkdir(parents=True, exist_ok=True)
    d = tempfile.mkdtemp(prefix="plebian-askpass-", dir=session)
    f = os.path.join(d, "askpass.sh")
    with open(f, "w") as fh:
        fh.write("#!/bin/sh\nexec printf '%s\\n' \"$PLEBIAN_ASKPASS_PW\"\n")
    os.chmod(f, 0o700)
    atexit.register(lambda: shutil.rmtree(d, ignore_errors=True))
    return f

def ssh(cfg: Config, command: str, askpass: str, timeout: int = 15):
    env = {**os.environ, "SSH_ASKPASS": askpass, "SSH_ASKPASS_REQUIRE": "force",
           "DISPLAY": os.environ.get("DISPLAY", ":0"), "PLEBIAN_ASKPASS_PW": cfg.password}
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

def wait_for_provisioning(cfg: Config, timeout_s: int) -> None:
    askpass = _askpass_for(cfg.password)
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

# ── acceptance verification (post-provision, over SSH) ───────────────────────
def verify_provisioning(cfg: Config, askpass: str) -> None:
    """Prove the real installer→firstboot→session boundary: check the markers a
    correctly provisioned Plebian-OS leaves behind. Dies (nonzero) on any miss."""
    info("verifying the provisioned system (acceptance checks) …")
    # Resolve KILIX_DIR from the target's own session.env so an overridden
    # checkout location is honored (default ~/gpu_terminal/kilix).
    kdir = ('. /etc/pleb/session.env 2>/dev/null; '
            's="${GPU_TERMINAL_SOURCE_HOME:-$HOME/gpu_terminal}"; '
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
    checks = [
        ("provisioned marker",   "test -f /var/lib/plebian-os/provisioned"),
        ("build provenance",     "test -s /etc/plebian-os/build-info.env"),
        ("package provenance",   "test -s /var/lib/plebian-os/packages.list"),
        ("source provenance",    "grep -Eq '^PLEBIAN_OS_COMMIT=[0-9a-f]{40}$' /var/lib/plebian-os/versions.env"),
        ("coordinated checkouts", kdir +
         ' o="${PLEBIAN_OS_DIR:-$s/plebian-os}";'
         ' p="${PLEB_DIR:-$s/pleb}";'
         ' test -d "$o/.git" && test -d "$p/.git" && test -d "$d/.git"'),
        ("private storage roots", private_storage),
        ("pleb recovery guide", "test -r /usr/local/share/doc/pleb/RECOVERY.md"),
        ("pleb xsession",        "test -f /usr/share/xsessions/pleb.desktop"),
        ("pleb-session binary",  "test -x /usr/local/bin/pleb-session"),
        ("session.env",          "test -f /etc/pleb/session.env"),
        ("lightdm pleb default", "grep -q user-session=pleb /etc/lightdm/lightdm.conf.d/50-plebian-os.conf"),
        ("update helper",        "test -x /usr/local/bin/plebian-os-update"),
        ("firstboot disabled",   "! systemctl is-enabled plebian-os-firstboot.service >/dev/null 2>&1"),
        ("temporary sudo gone",  "test ! -e /etc/sudoers.d/plebian-os-provision"),
    ]
    # The clickable fork engine only exists when fork-building is on (the default);
    # with it off, provisioning ships the prebuilt engine, so check that instead.
    fork_on = os.environ.get("PLEBIAN_OS_BUILD_KILIX_FORK", "1") not in ("0", "no", "false", "off")
    if fork_on:
        checks.append(("kilix fork engine", kdir +
                       ' s="${KILIX_STORAGE_HOME:-$HOME/.local/gpu_terminal/kilix}";'
                       ' test -x "$s/build/current/src/kitty/launcher/kitty"'))
    else:
        checks.append(("kilix engine", kdir + ' test -x "$d/kilix"'))
    failed = []
    for name, cmd in checks:
        r = ssh(cfg, cmd + " && echo OK || echo NO", askpass)
        ok = r is not None and r.returncode == 0 and "OK" in (r.stdout or "")
        info(f"  [{'ok' if ok else '!!'}] {name}")
        if not ok:
            failed.append(name)
    if failed:
        die("acceptance verification FAILED: " + ", ".join(failed))
    info(c("1;32", "acceptance verification passed."))

# ── summary ──────────────────────────────────────────────────────────────────
def final_summary(cfg: Config, iso: Path) -> None:
    print(c("1;32", "\n✓ Plebian-OS VirtualBox image is ready.\n"))
    print(f"  VM        : {cfg.name}")
    print(f"  login     : {cfg.username} / (the password you set)")
    print(f"  session   : {'kilix desktop' if cfg.desktop else 'kilix shell'}"
          f"{' (autologin)' if cfg.kiosk else ' (greeter)'}")
    print(f"  start GUI : VBoxManage startvm {cfg.name} --type gui")
    print(f"  ssh in    : ssh -p {cfg.ssh_port} {cfg.username}@127.0.0.1")
    print(f"  ISO       : {iso}")
    print()

# ── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="Build a Plebian-OS VM image from scratch.")
    ap.add_argument("--target", choices=["virtualbox", "vbox", "qemu", "docker"],
                    default="virtualbox", help="image type (only virtualbox today)")
    ap.add_argument("--name"); ap.add_argument("--username"); ap.add_argument("--fullname")
    ap.add_argument("--hostname"); ap.add_argument("--password")
    ap.add_argument("--ram", type=int, help="MB"); ap.add_argument("--cpus", type=int)
    ap.add_argument("--vram", type=int, default=None,
                    help="video RAM in MB (VirtualBox caps this at 256 on this host)")
    ap.add_argument("--accelerate-3d", action="store_true",
                    help="enable VirtualBox 3D acceleration")
    ap.add_argument("--disk", type=int, help="GB")
    ap.add_argument("--session", choices=["desktop", "shell"])
    ap.add_argument("--kiosk", dest="kiosk", action="store_true", default=None,
                    help="autologin straight into Pleb (default)")
    ap.add_argument("--no-kiosk", dest="kiosk", action="store_false",
                    help="show the login greeter instead of autologin")
    ap.add_argument("--sudo-nopasswd", dest="nopasswd_sudo", action="store_true",
                    default=None, help="passwordless sudo for the user (default)")
    ap.add_argument("--no-sudo-nopasswd", dest="nopasswd_sudo", action="store_false",
                    help="require a password for sudo")
    ap.add_argument("--port", type=int, help="SSH host port -> guest 22")
    ap.add_argument("--iso", type=Path, help="use this prebuilt ISO (skip building)")
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
                    help="delete and recreate an existing VM with the same name")
    ap.add_argument("--timeout", type=int, default=90, help="minutes to wait for provisioning")
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

    if args.iso:
        warn("using a prebuilt ISO: custom username/password/session are NOT applied "
             "(they live in the ISO's preseed). SSH waiting assumes the credentials "
             "entered here match that ISO.")
        if args.yes and args.password is None and not args.no_wait:
            die("--yes --iso needs --password for SSH waiting (or pass --no-wait)")
    cfg = gather_config(args)
    if not args.iso and cfg.password == "plebian":
        die("VM images enable sshd; choose a password other than the shipped 'plebian' default")
    confirm_summary(cfg, args.yes)

    if args.iso:
        iso = args.iso.resolve()
        if not iso.exists() and not args.dry_run:
            die(f"--iso not found: {iso}")
    else:
        out = (args.out or (storage_dir("artifacts") /
                            default_iso_filename(cfg.name))).resolve()
        preseed = None if args.dry_run else generate_preseed(cfg, enable_ssh=True)
        iso = build_iso(cfg, preseed, out, args.dry_run)

    if args.dry_run:
        info("dry run: would now create + boot the VM and wait for provisioning.")
        return

    vbox_create(cfg, iso, replace=args.replace, assume_yes=args.yes)
    vbox_start(cfg)

    if not cfg.wait:
        info(f"VM {cfg.name!r} started; not waiting (--no-wait).")
        final_summary(cfg, iso)
        return

    wait_for_provisioning(cfg, args.timeout * 60)
    vbox_detach_iso(cfg)
    if not args.no_verify:
        verify_provisioning(cfg, _askpass_for(cfg.password))
    final_summary(cfg, iso)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        die("interrupted.")
