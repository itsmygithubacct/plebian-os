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
    # a quarter of system RAM, rounded to 256 MB, never below 1 GB
    q = host_ram_mb() // 4
    return max(1024, (q // 256) * 256)

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
                pw = getpass.getpass(f"  password [{default}]: ")
            except EOFError:
                pw = ""
            if pw == "":
                return default
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
        warn(f"--yes without --password: generated password for {username}: {password}")
    else:
        password = p.ask_password("plebian")
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
    warn("openssl unavailable — falling back to a plaintext password in the preseed")
    return pw, False

# ── preseed generation ───────────────────────────────────────────────────────
def generate_preseed(cfg: Config) -> Path:
    text = PRESEED_TEMPLATE.read_text()

    def sub(pattern, repl):
        nonlocal text
        new, n = re.subn(pattern, repl, text, flags=re.MULTILINE)
        if n == 0:
            warn(f"preseed: pattern not found, skipped: {pattern!r}")
        text = new

    def envfile_quote(value: str) -> str:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    sub(r"^(d-i passwd/username string ).*$",      r"\g<1>" + cfg.username)
    sub(r"^(d-i passwd/user-fullname string ).*$", r"\g<1>" + cfg.fullname)
    sub(r"^(d-i netcfg/get_hostname string ).*$",  r"\g<1>" + cfg.hostname)

    secret, crypted = crypt_password(cfg.password)
    if crypted:
        # replace the two plaintext lines with a single crypted line
        sub(r"^d-i passwd/user-password password .*$",
            "d-i passwd/user-password-crypted password " + secret)
        sub(r"^d-i passwd/user-password-again password .*\n", "")
    else:
        sub(r"^(d-i passwd/user-password password ).*$",       r"\g<1>" + secret)
        sub(r"^(d-i passwd/user-password-again password ).*$", r"\g<1>" + secret)

    # Inject the build-time provisioning options the first-boot unit reads via
    # EnvironmentFile=-/etc/default/plebian-os, right before the unit is enabled.
    user_home = f"/home/{cfg.username}"
    env_vars = [
        ("PLEBIAN_OS_DESKTOP", "1" if cfg.desktop else "0"),
        ("PLEBIAN_OS_KIOSK", "1" if cfg.kiosk else "0"),
        ("PLEBIAN_OS_USER", cfg.username),
        ("PLEBIAN_OS_NOPASSWD_SUDO", "1" if cfg.nopasswd_sudo else "0"),
        ("PLEBIAN_OS_INSTALL_UV", os.environ.get("PLEBIAN_OS_INSTALL_UV", "0")),
        ("PLEB_REPO", os.environ.get("PLEB_REPO", "https://github.com/itsmygithubacct/pleb.git")),
        ("KILIX_REPO", os.environ.get("KILIX_REPO", "https://github.com/itsmygithubacct/kilix.git")),
        ("KILIX95_REPO", os.environ.get("KILIX95_REPO", "https://github.com/itsmygithubacct/kilix-95.git")),
        ("PLEB_BRANCH", os.environ.get("PLEB_BRANCH", "")),
        ("PLEB_REF", os.environ.get("PLEB_REF", "")),
        ("KILIX_BRANCH", os.environ.get("KILIX_BRANCH", "")),
        ("KILIX_REF", os.environ.get("KILIX_REF", "")),
        ("KILIX_PREBUILT_VERSION", os.environ.get("KILIX_PREBUILT_VERSION", "")),
        ("KILIX_PREBUILT_SHA256", os.environ.get("KILIX_PREBUILT_SHA256", "")),
        ("KILIX_DESKTOP_PROVIDER", os.environ.get("KILIX_DESKTOP_PROVIDER", "external")),
        ("KILIX_DESKTOP_COMMAND", os.environ.get("KILIX_DESKTOP_COMMAND", "")),
        ("KILIX_DESKTOP_NAME", os.environ.get("KILIX_DESKTOP_NAME", "desktop")),
        ("KILIX95_AUTO_INSTALL", os.environ.get("KILIX95_AUTO_INSTALL", "1")),
        ("KILIX95_BRANCH", os.environ.get("KILIX95_BRANCH", "")),
        ("KILIX95_REF", os.environ.get("KILIX95_REF", "")),
        ("KILIX_DIR", os.environ.get("KILIX_DIR", f"{user_home}/kilix")),
        ("KILIX95_DIR", os.environ.get("KILIX95_DIR", f"{user_home}/kilix-95")),
    ]
    env_fmt = "".join(f"{k}=%s\\n" for k, _ in env_vars)
    env_args = " ".join(shlex.quote(envfile_quote(v)) for _, v in env_vars)
    env_line = (
        "    mkdir -p /target/etc/default; "
        f"printf '{env_fmt}' {env_args} > /target/etc/default/plebian-os; \\\n"
    )
    anchor = "    in-target systemctl enable plebian-os-firstboot.service; \\\n"
    if anchor in text:
        text = text.replace(anchor, env_line + anchor)
    else:
        warn("preseed: late_command anchor not found; session options not injected")

    tmp = Path(tempfile.mkstemp(prefix="plebian-preseed-", suffix=".cfg")[1])
    tmp.write_text(text)
    atexit.register(lambda: tmp.unlink(missing_ok=True))
    return tmp

# ── ISO build (target-agnostic; reuses the repo's remaster script) ───────────
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
    env = {**os.environ, "PLEBIAN_OS_PRESEED": str(preseed),
           "PLEBIAN_OS_AUTOBOOT": "1", "PLEBIAN_OS_UNATTENDED_DISK": "1"}
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

def vbox_create(cfg: Config, iso: Path, assume_yes: bool = False) -> None:
    if vbox_exists(cfg.name):
        warn(f"a VM named {cfg.name!r} already exists")
        if assume_yes:
            info("  --yes: deleting and recreating it")
        else:
            try:
                ans = input("  delete and recreate it? [y/N]: ").strip().lower()
            except EOFError:
                ans = ""
            if ans not in ("y", "yes"):
                die("aborted (pick another --name).")
        subprocess.run(["VBoxManage", "controlvm", cfg.name, "poweroff"],
                      capture_output=True)
        time.sleep(1)
        run(["VBoxManage", "unregistervm", cfg.name, "--delete"], check=False)

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
    d = tempfile.mkdtemp(prefix="plebian-askpass-")
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
        "elif [ \"$s\" = failed ]; then echo FAILED; else echo RUNNING; fi")
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
    ap.add_argument("--out", type=Path, default=None,
                    help="ISO output path when building (default: plebian-os-<name>.iso)")
    ap.add_argument("--gui", action="store_true", help="start the VM with a window")
    ap.add_argument("--no-wait", action="store_true", help="don't block on provisioning")
    ap.add_argument("--timeout", type=int, default=60, help="minutes to wait for provisioning")
    ap.add_argument("-y", "--yes", action="store_true", help="accept defaults, no prompts")
    ap.add_argument("--dry-run", action="store_true", help="show the plan; build nothing")
    args = ap.parse_args()

    target = "virtualbox" if args.target in ("virtualbox", "vbox") else args.target
    if target != "virtualbox":
        die(f"target {target!r} is not implemented yet — only 'virtualbox' for now.")

    # preflight
    if not args.dry_run:
        for tool in ("VBoxManage", "xorriso"):
            if not have(tool):
                die(f"{tool} is required but not installed.")
    if not PRESEED_TEMPLATE.exists() or not REMASTER.exists():
        die("run this from a Plebian-OS checkout (preseed/ + build/ not found).")

    if args.iso:
        warn("using a prebuilt ISO: custom username/password/session are NOT applied "
             "(they live in the ISO's preseed). SSH waiting assumes the credentials "
             "entered here match that ISO.")
    cfg = gather_config(args)
    confirm_summary(cfg, args.yes)

    if args.iso:
        iso = args.iso.resolve()
        if not iso.exists() and not args.dry_run:
            die(f"--iso not found: {iso}")
    else:
        out = (args.out or (REPO / f"plebian-os-{cfg.name}.iso")).resolve()
        preseed = None if args.dry_run else generate_preseed(cfg)
        iso = build_iso(cfg, preseed, out, args.dry_run)

    if args.dry_run:
        info("dry run: would now create + boot the VM and wait for provisioning.")
        return

    vbox_create(cfg, iso, args.yes)
    vbox_start(cfg)

    if not cfg.wait:
        info(f"VM {cfg.name!r} started; not waiting (--no-wait).")
        final_summary(cfg, iso)
        return

    wait_for_provisioning(cfg, args.timeout * 60)
    vbox_detach_iso(cfg)
    final_summary(cfg, iso)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        die("interrupted.")
