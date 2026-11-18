"""Release-closure selection: the atomic mechanism used directly and by the
updater's default latest-release hop.

These tests validate a target release's complete closure and move all of its
release-controlled keys into /etc/pleb/session.env as one unit, without
touching a single operator-controlled choice.
"""

import fcntl
import hashlib
import os
import pty
import re
import shutil
import shlex
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# The fixtures model root-owned system configuration, which is world readable
# even when the suite is launched from a Kilix shell with umask 077.
os.umask(0o022)
SELECT = ROOT / "provision" / "plebian-os-select-closure.sh"
UPDATE = ROOT / "provision" / "plebian-os-update.sh"
MANIFEST = ROOT / "releases" / "0.1.8.env"
UPGRADING = ROOT / "UPGRADING.md"
RELEASING = ROOT / "RELEASING.md"
NOTES = ROOT / "releases" / "0.1.8-notes.md"
F120_ROOT_VALUES = {
    "KILIX_SYSTEM_MONITOR_REPO":
        "https://github.com/itsmygithubacct/kilix-system-monitor.git",
    "KILIX_SYSTEM_MONITOR_BRANCH": "",
    "KILIX_SYSTEM_MONITOR_REF": "1" * 40,
    "KILIX_DESKTOP_SDK_REPO":
        "https://github.com/itsmygithubacct/kilix-desktop-sdk.git",
    "KILIX_DESKTOP_SDK_BRANCH": "",
    "KILIX_DESKTOP_SDK_REF": "2" * 40,
    "KILIX_ICEWM_REPO":
        "https://github.com/itsmygithubacct/kilix-icewm.git",
    "KILIX_ICEWM_BRANCH": "",
    "KILIX_ICEWM_REF": "3" * 40,
    "KILIX_MEDIA_SDK_REPO":
        "https://github.com/itsmygithubacct/kilix-media-sdk.git",
    "KILIX_MEDIA_SDK_BRANCH": "",
    "KILIX_MEDIA_SDK_REF": "4" * 40,
    "KILIX_WAYDROID_REPO":
        "https://github.com/itsmygithubacct/kilix-waydroid.git",
    "KILIX_WAYDROID_BRANCH": "",
    "KILIX_WAYDROID_REF": "5" * 40,
}

# What a 0.1.7 image left in /etc/pleb/session.env. Every one of these is
# release-controlled and must move together.
INSTALLED_RELEASE_VALUES = [
    ("PLEB_REPO", "https://github.com/itsmygithubacct/pleb.git"),
    ("PLEB_BRANCH", ""),
    ("PLEB_REF", "0d860da201fbc0e75dfc1ed3eaebe3388e7fd570"),
    ("KILIX_REPO", "https://github.com/itsmygithubacct/kilix.git"),
    ("KILIX_BRANCH", ""),
    ("KILIX_REF", "6913364fe5f9eaa61258c0752b6ef12f55e49bc9"),
    ("KILIX_PREBUILT_VERSION", "0.47.4"),
    ("KILIX_PREBUILT_SHA256", "bc230142b2bd27f2a4bf1b1b67575f3d397a4ea2cc83f4ac2b912c306a939693"),
    ("KILIX_VOICE_REF", "f05b64a7b2bc25fa9a7e2c3ae1e0b848f04a23f6"),
    ("KILIX_VOICE_LIB_VERSION", "0.3.45"),
    ("KILIX_VOICE_LIB_URL", "https://files.pythonhosted.org/packages/fc/vosk.whl"),
    ("KILIX_VOICE_LIB_SHA256", "25e025093c4399d7278f543568ed8cc5460ac3a4bf48c23673ace1e25d26619f"),
    ("KILIX_VOICE_MODEL_URL", "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"),
    ("KILIX_VOICE_MODEL_SHA256", "30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498"),
    ("PLEBIAN_OS_INSTALL_VOICE_MODEL", "1"),
    ("PLEBIAN_OS_BUILD_KILIX_FORK", "1"),
    ("PLEBIAN_OS_KILIX_GO_MIN_VERSION", "1.26"),
    ("PLEBIAN_OS_KILIX_GO_VERSION", "go1.26.4"),
    ("PLEBIAN_OS_KILIX_GO_SHA256_AMD64", "a" * 64),
    ("PLEBIAN_OS_KILIX_GO_SHA256_ARM64", "b" * 64),
    ("KILIX95_REPO", "https://github.com/itsmygithubacct/kilix-95.git"),
    ("KILIX95_BRANCH", ""),
    ("KILIX95_REF", "cdc6d073d62e5929f14cd294f68a18eb1291b1da"),
    ("PLEBIAN_OS_VERSION", "0.1.7"),
    ("PLEBIAN_OS_RELEASE", "0.1.7"),
    ("PLEBIAN_OS_RELEASE_MODE", "1"),
    ("PLEBIAN_OS_REPO", "https://github.com/itsmygithubacct/plebian-os.git"),
    ("PLEBIAN_OS_BRANCH", ""),
    ("PLEBIAN_OS_REF", "1" * 40),
    ("PLEBIAN_OS_APT_SNAPSHOT", "20260712T000000Z"),
]

# Session, provider, storage, kiosk and layout choices. UPGRADING.md promises
# an upgrade preserves every one of them.
OPERATOR_VALUES = [
    ("PLEBIAN_OS_MANAGED_INSTALL", "1"),
    ("PLEB_DESKTOP", "1"),
    ("PLEB_WM", "none"),
    ("KILIX_RUN_ALIASES", "0"),
    ("KILIX_DESKTOP_PROVIDER", "cap"),
    ("KILIX_DESKTOP_FLAVOR", "xp"),
    ("KILIX95_AUTO_INSTALL", "0"),
    ("KILIX_CAP_AUTO_INSTALL", "1"),
]


def guarded(name: str, value: str) -> str:
    """The provisioner's exact write_session_default line shape."""
    return 'if [ -z "${%s+x}" ]; then %s=%s; fi' % (name, name, shlex.quote(value))


class ClosureSelectionTests(unittest.TestCase):
    # ── fixtures ────────────────────────────────────────────────────────────
    def _machine(self, base: Path, release=None, operator=None, extra_lines=()):
        """A provisioned machine: root-owned session config plus a data root."""
        release = INSTALLED_RELEASE_VALUES if release is None else release
        operator = OPERATOR_VALUES if operator is None else operator
        etc = base / "root" / "etc" / "pleb"
        etc.mkdir(parents=True)
        (base / "root" / "var" / "lib").mkdir(parents=True)
        (base / "root" / "usr" / "local" / "bin").mkdir(parents=True)
        # Every release this fixture installs still resolves apt from its Debian
        # install snapshot, as a machine does until a 0.2.2 update commits.
        snapshot = base / "root" / "etc" / "apt" / "sources.list.d"
        snapshot.mkdir(parents=True)
        (snapshot / "plebian-os-snapshot.sources").write_text("Types: deb\n")
        home = base / "home" / ".local" / "gpu_terminal" / "sources"
        lines = ["# Managed by plebian-os-provision — Plebian-OS Pleb session config."]
        lines.append(guarded("GPU_TERMINAL_SOURCE_HOME", str(home)))
        lines.append(guarded("PLEBIAN_OS_DIR", str(base / "src")))
        lines.append(guarded("PLEB_DIR", str(home / "pleb")))
        lines.append(guarded("KILIX_DIR", str(home / "kilix")))
        lines.append(guarded("KILIX95_DIR", str(home / "kilix-desktops" / "kilix-95")))
        for name, value in release:
            lines.append(guarded(name, value))
        for name, value in operator:
            lines.append(guarded(name, value))
        lines.append("export KILIX_DESKTOP_PROVIDER KILIX_DESKTOP_FLAVOR")
        lines.append("PLEB_RESPAWN=0   # operator note, deliberately unguarded")
        lines.extend(extra_lines)
        env = etc / "session.env"
        env.write_text("\n".join(lines) + "\n")
        env.chmod(0o644)
        return env

    def _manifest_text(self, drop=(), raw_lines=(), **changes) -> str:
        """The real 0.1.8 closure, optionally mutated key by key."""
        out, seen = [], set()
        for line in MANIFEST.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key = line.split("=", 1)[0]
                if key in drop:
                    continue
                if key in changes:
                    seen.add(key)
                    line = f"{key}={changes[key]}"
            out.append(line)
        for key, value in changes.items():
            if key not in seen:
                out.append(f"{key}={value}")
        out.extend(raw_lines)
        return "\n".join(out) + "\n"

    def _source(self, base: Path, manifest_text=None, version="0.1.8",
                release="0.1.8", tag="v0.1.8",
                requirements_text=None, selector_bytes=None,
                updater_bytes=None, arm64_manifest_text=None,
                arm64_requirements_text=None) -> str:
        """A Plebian-OS checkout, optionally carrying a release tag."""
        src = base / "src"
        (src / "releases").mkdir(parents=True)
        (src / "provision").mkdir(parents=True)
        (src / "VERSION").write_text(version + "\n")
        (src / "provision" / "plebian-os-select-closure.sh").write_bytes(
            SELECT.read_bytes() if selector_bytes is None else selector_bytes)
        (src / "provision" / "plebian-os-update.sh").write_bytes(
            UPDATE.read_bytes() if updater_bytes is None else updater_bytes)
        (src / "releases" / f"{release}.env").write_text(
            self._manifest_text() if manifest_text is None else manifest_text)
        if requirements_text is not None:
            (src / "releases" / f"{release}.requirements").write_text(
                requirements_text)
        if arm64_manifest_text is not None:
            (src / "releases" / f"{release}-arm64.env").write_text(arm64_manifest_text)
        if arm64_requirements_text is not None:
            (src / "releases" / f"{release}-arm64.requirements").write_text(
                arm64_requirements_text)
        git = ["git", "-C", str(src)]
        subprocess.run(git + ["init", "-q"], check=True)
        subprocess.run(git + ["config", "user.email", "t@example.invalid"], check=True)
        subprocess.run(git + ["config", "user.name", "t"], check=True)
        subprocess.run(
            git + ["remote", "add", "origin",
                   "https://github.com/itsmygithubacct/plebian-os.git"], check=True)
        subprocess.run(git + ["add", "-A"], check=True)
        subprocess.run(git + ["commit", "-qm", "release"], check=True)
        if tag is not None:
            subprocess.run(git + ["tag", "-a", tag, "-m", tag], check=True)
        return subprocess.run(
            git + ["rev-parse", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()

    def _f120_manifest_text(self, drop=(), **changes) -> str:
        values = {
            "PLEBIAN_OS_VERSION": "0.2.1",
            "PLEBIAN_OS_REF": "v0.2.1",
            "PLEBIAN_OS_NETINST_URL":
                "https://cdimage.debian.org/cdimage/archive/13.5.0/amd64/"
                "iso-cd/debian-13.5.0-amd64-netinst.iso",
            "PLEBIAN_OS_NETINST_SHA256":
                "95838884f5ea6c82421dfe6baaa5a639dbbe6756c1e380f9fe7a7cb0c1949d2a",
            "PLEBIAN_OS_NETINST_MAX_BYTES": "791674880",
            "PLEBIAN_OS_APT_SNAPSHOT": "20260727T000000Z",
            "PLEBIAN_OS_INSTALL_UV": "1",
            "PLEBIAN_OS_UV_VERSION": "0.12.5",
            "PLEBIAN_OS_UV_INSTALLER_SHA256":
                "504511fbbbd811aeaba6738abc79408956b6c7da0ca35437b3dcc24a41efc111",
            "PLEBIAN_OS_UV_INSTALLER_MAX_BYTES": "71225",
            "PLEBIAN_OS_INSTALL_WAYDROID": "1",
            "PLEBIAN_OS_WAYDROID_CLOSURE_SHA256":
                "4f2fef049ab669fc43d7873c2e1c55ad180fec13d730cad681645e60a8410a33",
            **F120_ROOT_VALUES,
            **changes,
        }
        text = self._manifest_text(**values)
        return "\n".join(
            line for line in text.splitlines()
            if not any(line.startswith(f"{key}=") for key in drop)
        ) + "\n"

    def _run(self, base: Path, *args, fail_after=None, check_ancestry=False,
             env_extra=None, trust_tag=True, pass_fds=(), popen=False,
             command=None, dead_tty=False):
        env = {
            "HOME": str(base / "home"),
            "PATH": os.environ["PATH"],
            "LANG": "C",
            "PLEBIAN_OS_CLOSURE_TEST_ROOT": str(base / "root"),
            "PLEBIAN_OS_COMPONENT_CACHE_HOME": str(base / "cache/components"),
        }
        if not check_ancestry:
            env["PLEBIAN_OS_SELECT_TEST_SKIP_COMPONENT_ANCESTRY"] = "1"
        if fail_after is not None:
            env["PLEBIAN_OS_SELECT_TEST_FAIL_AFTER"] = fail_after
        if env_extra:
            env.update(env_extra)
        target = next((arg for arg in args if re.fullmatch(r"\d+\.\d+\.\d+(?:\.[1-9][0-9]*)?", arg)), None)
        source = base / "src"
        if trust_tag and target is not None and (source / ".git").is_dir():
            tag = subprocess.run(
                ["git", "-C", str(source), "rev-parse", f"refs/tags/v{target}"],
                capture_output=True, text=True, check=False,
            )
            if tag.returncode == 0:
                env["PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA"] = tag.stdout.strip()
        argv = [str(SELECT), *args] if command is None else command
        if dead_tty:
            # The terminal hung up: every write to the descriptors fails with EIO.
            master, slave = pty.openpty()
            os.close(master)
            try:
                return subprocess.Popen(argv, env=env, stdin=slave, stdout=slave,
                                        stderr=slave, pass_fds=pass_fds)
            finally:
                os.close(slave)
        if popen:
            return subprocess.Popen(argv, env=env, text=True, pass_fds=pass_fds,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return subprocess.run(argv, env=env, text=True,
                              capture_output=True, check=False, pass_fds=pass_fds)

    @staticmethod
    def _component_history(path: Path, count=2):
        path.mkdir(parents=True)
        git = ["git", "-C", str(path)]
        subprocess.run(git + ["init", "-q"], check=True)
        subprocess.run(git + ["config", "user.email", "t@example.invalid"], check=True)
        subprocess.run(git + ["config", "user.name", "t"], check=True)
        commits = []
        for index in range(count):
            (path / "state").write_text(f"{index}\n")
            subprocess.run(git + ["add", "state"], check=True)
            subprocess.run(git + ["commit", "-qm", f"state {index}"], check=True)
            commits.append(subprocess.run(
                git + ["rev-parse", "HEAD"], capture_output=True,
                text=True, check=True,
            ).stdout.strip())
        return commits

    @staticmethod
    def _seed_public_cache(base: Path, name: str, repo: str, source: Path,
                           public_commit=None):
        """Populate the exact advertised-ref namespace used by offline proof."""
        cache = base / "cache/components" / f"{name}.git"
        cache.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", "--bare", str(cache)], check=True)
        subprocess.run(
            ["git", "-C", str(cache), "remote", "add", "origin", repo],
            check=True,
        )
        if public_commit is None:
            public_commit = subprocess.run(
                ["git", "-C", str(source), "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
        subprocess.run(
            ["git", "-C", str(cache), "fetch", "-q", str(source), public_commit],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(cache), "update-ref",
             "refs/plebian-os-public/heads/main", public_commit],
            check=True,
        )

    def _seed_core_public_caches(self, base: Path, pleb: Path,
                                 kilix: Path, kilix95: Path):
        values = dict(INSTALLED_RELEASE_VALUES)
        self._seed_public_cache(
            base, "plebian-os", values["PLEBIAN_OS_REPO"], base / "src")
        self._seed_public_cache(base, "pleb", values["PLEB_REPO"], pleb)
        self._seed_public_cache(base, "kilix", values["KILIX_REPO"], kilix)
        self._seed_public_cache(
            base, "kilix-95", values["KILIX95_REPO"], kilix95)

    @staticmethod
    def _values(env_path: Path) -> dict:
        """Read the file the way pleb-session does — by sourcing it."""
        script = (
            'set -e\n'
            'pre=" $(compgen -v | tr "\\n" " ") "\n'
            '. "$1"\n'
            '[ ! -f "$2" ] || . "$2"\n'
            'for n in $(compgen -v); do\n'
            '  case "$pre" in *" $n "*) continue ;; esac\n'
            '  case "$n" in pre|n) continue ;; esac\n'
            '  printf "%s=%s\\n" "$n" "${!n}"\n'
            'done\n'
        )
        out = subprocess.run(
            ["env", "-i", "bash", "--noprofile", "--norc", "-c", script,
             "bash", str(env_path), str(env_path.with_name("closure.env"))],
            capture_output=True, text=True, check=True).stdout
        return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)

    def _recovery_records(self, base: Path):
        recovery = base / "root" / "var" / "lib" / "plebian-os"
        if not recovery.is_dir():
            return []
        return sorted(p for p in recovery.iterdir()
                      if p.name.startswith("closure-rollback."))

    @staticmethod
    def _frozen_clock(base: Path, epoch: int) -> dict:
        """PATH for a selector whose every selection lands in one UTC second.

        `date` without an explicit time reports `epoch`; a date it is handed
        (-d, -r, -f, -s) is passed through, so a conversion still works. A
        recovery record made by `mktemp -d .../closure-rollback.*.XXXXXX`
        gets a descending suffix: a later record's random part sorts before an
        earlier one's, the order a real random suffix gave about half the
        time. Only that template is changed; every other mktemp is real.
        """
        bindir = base / "frozen-clock-bin"
        bindir.mkdir()
        date = shutil.which("date")
        mktemp = shutil.which("mktemp")
        (bindir / "date").write_text(
            "#!/bin/bash\n"
            'for arg in "$@"; do\n'
            '    case "$arg" in\n'
            "        -d*|--date|--date=*|-r*|--reference|--reference=*|-f*|--file|--file=*|-s*|--set|--set=*)\n"
            f'            exec {shlex.quote(date)} "$@" ;;\n'
            "    esac\n"
            "done\n"
            f'exec {shlex.quote(date)} -d @{int(epoch)} "$@"\n')
        counter = bindir / "record-count"
        (bindir / "mktemp").write_text(
            "#!/bin/bash\n"
            'if [ "$#" = 2 ] && [ "$1" = -d ]; then\n'
            '    case "$2" in\n'
            "        */closure-rollback.*.XXXXXX)\n"
            f"            n=$(cat {shlex.quote(str(counter))} 2>/dev/null || printf 0)\n"
            f"            printf '%s\\n' \"$((n + 1))\" >{shlex.quote(str(counter))}\n"
            "            dir=\"${2%XXXXXX}$(printf '%06d' \"$((999999 - n))\")\"\n"
            '            mkdir -m 0700 -- "$dir" || exit 1\n'
            "            printf '%s\\n' \"$dir\"\n"
            "            exit 0 ;;\n"
            "    esac\n"
            "fi\n"
            f'exec {shlex.quote(mktemp)} "$@"\n')
        for tool in ("date", "mktemp"):
            (bindir / tool).chmod(0o755)
        return {"PATH": f"{bindir}:{os.environ['PATH']}"}

    @staticmethod
    def _record_stamp(epoch: int) -> str:
        return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(epoch))

    @staticmethod
    def _last_in_glob_order(recovery: Path, locale="C") -> str:
        """The record every selector before 0.2.3 restores: the last
        unrestored name in the shell's glob order."""
        loop = ('for c in "$1"/closure-rollback.*; do '
                '[ -e "$c/restored" ] || r=${c##*/}; done; printf %s "$r"')
        env = dict(os.environ, LC_ALL=locale)
        return subprocess.run(["bash", "-c", loop, "bash", str(recovery)],
                              env=env, text=True, capture_output=True,
                              check=True).stdout

    # ── a complete closure selects ──────────────────────────────────────────
    def test_a_bare_repository_is_an_acceptable_source(self):
        """Pleb hands the selector a bare repo, so the selector must take one.

        `_pleb_release_cache_prepare` builds the release-hop cache with
        `git init --bare` and then validates that it *is* bare, and every hop
        passes that cache as `--source`. The guard here required a `.git`
        directory, which a bare repository never has, so `pleb update --to` and
        `--latest` died at "no Plebian-OS source checkout" on every machine --
        after fetching the target tag, before moving anything. Reproduced on a
        fresh 0.2.1 install: `pleb update --to 0.2.0` failed with
        "target closure selection failed with status 1".

        Nothing in resolve_closure_source needs a working tree; it reads the
        object store only, which is exactly what a bare repository serves.
        """
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            commit = self._source(base)
            bare = base / "hop" / "plebian-os.git"
            bare.parent.mkdir(parents=True)
            subprocess.run(["git", "clone", "-q", "--bare", str(base / "src"),
                            str(bare)], check=True)
            # `git clone --bare` already set origin to the local fixture path;
            # point it at the real remote the manifest names.
            subprocess.run(["git", "-C", str(bare), "remote", "set-url", "origin",
                            "https://github.com/itsmygithubacct/plebian-os.git"],
                           check=True)
            self.assertEqual(
                subprocess.run(["git", "-C", str(bare), "rev-parse",
                                "--is-bare-repository"], capture_output=True,
                               text=True, check=True).stdout.strip(),
                "true", "the fixture must actually be bare or this proves nothing")

            result = self._run(base, "0.1.8", "--offline", "--source", str(bare))
            self.assertEqual(result.returncode, 0,
                             "a bare source was rejected:\n" + result.stderr)
            self.assertNotIn("no Plebian-OS source checkout", result.stderr)
            self.assertEqual(self._values(env)["PLEBIAN_OS_REF"], commit)

    def test_a_directory_that_is_not_a_repository_is_still_refused(self):
        """Widening the guard must not turn it off."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base)
            empty = base / "not-a-repo"
            empty.mkdir()
            result = self._run(base, "0.1.8", "--offline", "--source", str(empty))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no Plebian-OS source checkout", result.stderr)

    DEBIAN_GO_FILES = {
        "PLEBIAN_OS_KILIX_GO_DEB_AMD64_FILE": "golang-1.27-go_1.27.3-1~bpo13+1_amd64.deb",
        "PLEBIAN_OS_KILIX_GO_DEB_AMD64_BYTES": "22655000",
        "PLEBIAN_OS_KILIX_GO_DEB_AMD64_SHA256": "c" * 64,
        "PLEBIAN_OS_KILIX_GO_DEB_SRC_FILE": "golang-1.27-src_1.27.3-1~bpo13+1_all.deb",
        "PLEBIAN_OS_KILIX_GO_DEB_SRC_BYTES": "25295000",
        "PLEBIAN_OS_KILIX_GO_DEB_SRC_SHA256": "d" * 64,
        "PLEBIAN_OS_KILIX_GO_DEB_SNAPSHOT": "20261110T000000Z",
        "PLEBIAN_OS_KILIX_GO_DEB_MIRROR_URL":
            "https://github.com/itsmygithubacct/plebian-os/releases/download/debian-go-test",
    }

    def _debian_go_manifest(self, drop=(), **changes):
        values = dict(
            PLEBIAN_OS_APT_SNAPSHOT="",
            PLEBIAN_OS_KILIX_GO_VERSION="go1.27.3",
            PLEBIAN_OS_KILIX_GO_DEBIAN_VERSION="1.27.3-1~bpo13+1",
            PLEBIAN_OS_KILIX_GO_SHA256_AMD64="",
            PLEBIAN_OS_KILIX_GO_SHA256_ARM64="",
            **self.DEBIAN_GO_FILES)
        values.update(changes)
        for key in drop:
            values.pop(key)
        return self._manifest_text(**values)

    def test_debian_go_selection_replaces_archive_pins(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            self._source(base, self._debian_go_manifest())
            result = self._run(base, "0.1.8", "--offline")
            self.assertEqual(result.returncode, 0, result.stderr)
            after = self._values(env)
            self.assertEqual(after["PLEBIAN_OS_KILIX_GO_DEBIAN_VERSION"],
                             "1.27.3-1~bpo13+1")
            self.assertEqual(after["PLEBIAN_OS_KILIX_GO_SHA256_AMD64"], "")
            for key, value in self.DEBIAN_GO_FILES.items():
                self.assertEqual(after[key], value, key)

    def test_release_0_2_3_debian_go_file_pins_are_selectable(self):
        release = dict(
            line.split("=", 1)
            for line in (ROOT / "releases" / "0.2.3.env").read_text().splitlines()
            if line.startswith("PLEBIAN_OS_KILIX_GO_"))
        pins = {key: value for key, value in release.items()
                if key.startswith("PLEBIAN_OS_KILIX_GO_DEB_")}
        self.assertEqual(sorted(pins), sorted(self.DEBIAN_GO_FILES))
        requirements = (ROOT / "releases" / "0.2.3.requirements").read_text()
        for key, value in pins.items():
            self.assertIn(f"\n{key}={value}\n", requirements)
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            self._source(base, self._manifest_text(PLEBIAN_OS_APT_SNAPSHOT="", **release))
            result = self._run(base, "0.1.8", "--offline")
            self.assertEqual(result.returncode, 0, result.stderr)
            after = self._values(env)
            for key, value in pins.items():
                self.assertEqual(after[key], value, key)

    def test_debian_go_without_file_pins_leaves_machine_unchanged(self):
        for dropped in (tuple(self.DEBIAN_GO_FILES), ("PLEBIAN_OS_KILIX_GO_DEB_SNAPSHOT",),
                        ("PLEBIAN_OS_KILIX_GO_DEB_MIRROR_URL",),
                        ("PLEBIAN_OS_KILIX_GO_DEB_SRC_SHA256",)):
            with self.subTest(dropped=dropped), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                env = self._machine(base)
                before = env.read_bytes()
                self._source(base, self._debian_go_manifest(drop=dropped))
                result = self._run(base, "0.1.8", "--offline")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Debian Go needs exact package file pins", result.stderr)
                self.assertEqual(env.read_bytes(), before)

    def test_debian_go_file_pin_defects_leave_machine_unchanged(self):
        for key, value, message in (
            ("PLEBIAN_OS_KILIX_GO_DEB_AMD64_FILE",
             "golang-1.27-go_1.27.4-1~bpo13+1_amd64.deb", "must be golang-1.27-go_1.27.3"),
            ("PLEBIAN_OS_KILIX_GO_DEB_AMD64_FILE",
             "golang-1.27-go_1.27.3-1~bpo13+1_arm64.deb", "must be golang-1.27-go_1.27.3"),
            ("PLEBIAN_OS_KILIX_GO_DEB_SRC_FILE",
             "../golang-1.27-src_1.27.3-1~bpo13+1_all.deb", "must be golang-1.27-src_1.27.3"),
            ("PLEBIAN_OS_KILIX_GO_DEB_AMD64_BYTES", "0", "exact byte count"),
            ("PLEBIAN_OS_KILIX_GO_DEB_SRC_BYTES", "25MB", "exact byte count"),
            ("PLEBIAN_OS_KILIX_GO_DEB_AMD64_SHA256", "C" * 64, "lowercase SHA-256"),
            ("PLEBIAN_OS_KILIX_GO_DEB_SRC_SHA256", "d" * 63, "lowercase SHA-256"),
            ("PLEBIAN_OS_KILIX_GO_DEB_SNAPSHOT", "20261110", "snapshot.debian.org timestamp"),
            ("PLEBIAN_OS_KILIX_GO_DEB_MIRROR_URL", "http://example.org/go", "https release-mirror"),
            ("PLEBIAN_OS_KILIX_GO_DEB_MIRROR_URL", "https://example.org/go/", "https release-mirror"),
            ("PLEBIAN_OS_KILIX_GO_DEB_MIRROR_URL", "https://example.org/go?x=1", "https release-mirror"),
        ):
            with self.subTest(key=key, value=value), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                env = self._machine(base)
                before = env.read_bytes()
                self._source(base, self._debian_go_manifest(**{key: value}))
                result = self._run(base, "0.1.8", "--offline")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertEqual(env.read_bytes(), before)

    def test_debian_go_file_pins_require_debian_go(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            before = env.read_bytes()
            self._source(base, self._manifest_text(
                PLEBIAN_OS_KILIX_GO_DEB_SNAPSHOT="20261110T000000Z"))
            result = self._run(base, "0.1.8", "--offline")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires PLEBIAN_OS_KILIX_GO_DEBIAN_VERSION", result.stderr)
            self.assertEqual(env.read_bytes(), before)

    def test_debian_go_mismatched_package_leaves_machine_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            before = env.read_bytes()
            manifest = self._manifest_text(
                PLEBIAN_OS_APT_SNAPSHOT="",
                PLEBIAN_OS_KILIX_GO_VERSION="go1.27.3",
                PLEBIAN_OS_KILIX_GO_DEBIAN_VERSION="1.27.2-1~bpo13+1")
            self._source(base, manifest)
            result = self._run(base, "0.1.8", "--offline")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("package and compiler versions differ", result.stderr)
            self.assertEqual(env.read_bytes(), before)

    def test_complete_closure_selects_every_release_controlled_key(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            commit = self._source(base)
            result = self._run(base, "0.1.8", "--offline")
            self.assertEqual(result.returncode, 0, result.stderr)
            after = self._values(env)
            manifest = dict(
                line.split("=", 1) for line in MANIFEST.read_text().splitlines()
                if "=" in line and not line.lstrip().startswith("#"))
            for key in ("PLEB_REF", "KILIX_REF", "KILIX95_REF", "KILIX_VOICE_REF",
                        "PLEBIAN_OS_APT_SNAPSHOT", "KILIX_PREBUILT_VERSION",
                        "KILIX_PREBUILT_SHA256", "PLEBIAN_OS_KILIX_GO_VERSION",
                        "PLEBIAN_OS_KILIX_GO_SHA256_AMD64",
                        "PLEBIAN_OS_KILIX_GO_SHA256_ARM64",
                        "KILIX_VOICE_LIB_URL", "KILIX_VOICE_MODEL_SHA256",
                        "PLEBIAN_OS_INSTALL_VOICE_MODEL"):
                self.assertEqual(after[key], manifest[key], key)
            self.assertEqual(after["PLEBIAN_OS_VERSION"], "0.1.8")
            self.assertEqual(after["PLEBIAN_OS_RELEASE"], "0.1.8")
            # The manifest names the movable tag; the machine keeps the commit.
            self.assertEqual(manifest["PLEBIAN_OS_REF"], "v0.1.8")
            self.assertEqual(after["PLEBIAN_OS_REF"], commit)
            self.assertIn("plebian-os-update --restart", result.stdout)
            self.assertIn("Do not run plebian-os-provision", result.stdout)
            meta = (self._recovery_records(base)[0] / "meta").read_text()
            self.assertNotIn("selection_kind=development-commit", meta)

    def test_maintenance_selector_bootstraps_old_tools_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            before = env.read_bytes()
            text = (ROOT / 'releases/0.2.2.env').read_text().replace(
                'PLEBIAN_OS_VERSION=0.2.2\n', 'PLEBIAN_OS_VERSION=0.2.2.1\n').replace(
                'PLEBIAN_OS_REF=v0.2.2\n', 'PLEBIAN_OS_REF=v0.2.2.1\n')
            self._source(base, text, version='0.2.2.1', release='0.2.2.1', tag='v0.2.2.1')
            dry = self._run(base, '0.2.2.1', '--offline', '--dry-run')
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertEqual(env.read_bytes(), before)
            selected = self._run(base, '0.2.2.1', '--offline')
            self.assertEqual(selected.returncode, 0, selected.stderr)
            tools = base / 'root/usr/local/bin'
            self.assertEqual((tools / 'plebian-os-update').read_bytes(), UPDATE.read_bytes())
            self.assertEqual((tools / 'plebian-os-select-closure').read_bytes(), SELECT.read_bytes())
            self.assertEqual(self._values(env)['PLEBIAN_OS_VERSION'], '0.2.2.1')
            rolled_back = self._run(base, '--rollback')
            self.assertEqual(rolled_back.returncode, 0, rolled_back.stderr)
            self.assertEqual(env.read_bytes(), before)

    def test_development_commit_selects_untagged_source_and_restores_old_tools(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            before = env.read_bytes()
            values_before = self._values(env)
            commit = self._source(base, tag=None)
            tools = base / "root" / "usr" / "local" / "bin"
            originals = {}
            for name in ("plebian-os-select-closure", "plebian-os-update"):
                path = tools / name
                originals[name] = f"#!/bin/sh\necho old-{name}\n".encode()
                path.write_bytes(originals[name])
                path.chmod(0o710)
            default = self._run(base, "0.1.8", "--offline")
            self.assertNotEqual(default.returncode, 0)
            self.assertIn("release tag v0.1.8 is not in", default.stderr)
            selected = self._run(base, "0.1.8", "--offline",
                                 "--development-commit", commit)
            self.assertEqual(selected.returncode, 0, selected.stderr)
            self.assertIn("DEVELOPMENT source selection", selected.stderr)
            self.assertIn("plebian-os-update --revalidate-current --restart",
                          selected.stdout)
            values = self._values(env)
            self.assertEqual(values["PLEBIAN_OS_REF"], commit)
            self.assertEqual(values["PLEBIAN_OS_VERSION"], "0.1.8")
            for key, value in OPERATOR_VALUES:
                self.assertEqual(values[key], value)
            self.assertEqual(values["PLEB_RESPAWN"], values_before["PLEB_RESPAWN"])
            self.assertIn(b"PLEB_RESPAWN=0   # operator note, deliberately unguarded", env.read_bytes())
            self.assertEqual((tools / "plebian-os-select-closure").read_bytes(), SELECT.read_bytes())
            self.assertEqual((tools / "plebian-os-update").read_bytes(), UPDATE.read_bytes())
            meta = (self._recovery_records(base)[0] / "meta").read_text()
            self.assertIn("selection_kind=development-commit\n", meta)
            self.assertIn("release_acceptance=not-claimed\n", meta)
            self.assertIn(f"os_commit={commit}\n", meta)
            git = ["git", "-C", str(base / "src")]
            self.assertEqual(subprocess.check_output(git + ["tag", "--list"]), b"")
            self.assertEqual(subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(), commit)
            rolled_back = self._run(base, "--rollback")
            self.assertEqual(rolled_back.returncode, 0, rolled_back.stderr)
            self.assertEqual(env.read_bytes(), before)
            for name, content in originals.items():
                self.assertEqual((tools / name).read_bytes(), content)
                self.assertEqual((tools / name).stat().st_mode & 0o777, 0o710)

    def test_development_commit_fetches_exact_object_without_fetching_tags(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            commit = self._source(base)
            cache = base / "cache.git"
            git = ["git", "-C", str(cache)]
            subprocess.run(["git", "init", "--bare", "-q", str(cache)], check=True)
            origin = "https://github.com/itsmygithubacct/plebian-os.git"
            subprocess.run(git + ["remote", "add", "origin", origin], check=True)
            # This private repository rewrites only its fixture origin. No
            # global config, public network or product ancestry bypass changes.
            subprocess.run(git + ["config", f"url.{base / 'src'}.insteadOf", origin], check=True)
            missing = self._run(base, "0.1.8", "--source", str(cache), "--offline",
                                "--development-commit", commit)
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("--offline forbids fetching", missing.stderr)
            selected = self._run(base, "0.1.8", "--source", str(cache),
                                 "--development-commit", commit)
            self.assertEqual(selected.returncode, 0, selected.stderr)
            self.assertEqual(self._values(env)["PLEBIAN_OS_REF"], commit)
            self.assertEqual(subprocess.check_output(git + ["tag", "--list"]), b"")
            self.assertNotEqual(subprocess.run(git + ["rev-parse", "--verify", "HEAD"],
                                              capture_output=True).returncode, 0)

    def test_development_commit_refuses_bad_identifiers_and_noncommit_objects(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            before = env.read_bytes()
            commit = self._source(base)
            git = ["git", "-C", str(base / "src")]
            tag = subprocess.check_output(git + ["rev-parse", "refs/tags/v0.1.8"], text=True).strip()
            tree = subprocess.check_output(git + ["rev-parse", "HEAD^{tree}"], text=True).strip()
            for value in ("", "main", commit[:12], commit.upper(), "g" * 40,
                          f"$(touch {shlex.quote(str(base / 'invalid-source-marker'))})",
                          "0" * 40, tag, tree):
                with self.subTest(value=value):
                    result = self._run(base, "0.1.8", "--offline", "--development-commit", value)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(env.read_bytes(), before)
                    self.assertEqual(self._recovery_records(base), [])
            self.assertFalse((base / "invalid-source-marker").exists())
            self.assertNotEqual(self._run(base, "0.1.8", "--development-commit").returncode, 0)
            self.assertNotEqual(self._run(base, "0.1.8", "--development-commit", commit,
                                          "--development-commit", commit).returncode, 0)
            for mode in ("--show", "--rollback"):
                result = self._run(base, mode, "--development-commit", commit)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("requires a target selection", result.stderr)

    def test_development_commit_failed_fetch_does_not_use_a_local_object(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            before = env.read_bytes()
            commit = self._source(base, tag=None)
            empty = base / "unpublished.git"
            subprocess.run(["git", "init", "--bare", "-q", str(empty)], check=True)
            origin = "https://github.com/itsmygithubacct/plebian-os.git"
            subprocess.run(["git", "-C", str(base / "src"), "config",
                            f"url.{empty}.insteadOf", origin], check=True)
            result = self._run(base, "0.1.8", "--development-commit", commit)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("could not fetch development commit", result.stderr)
            self.assertEqual(env.read_bytes(), before)
            self.assertEqual(self._recovery_records(base), [])

    def test_development_commit_preserves_origin_manifest_and_tool_guards(self):
        for kind in ("origin", "manifest", "selector", "updater", "version"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                env = self._machine(base)
                before = env.read_bytes()
                options = {"tag": None}
                if kind == "manifest":
                    options["manifest_text"] = self._manifest_text(drop=("KILIX_REF",))
                elif kind == "selector":
                    options["selector_bytes"] = SELECT.read_bytes() + b"\n# different target\n"
                elif kind == "updater":
                    options["updater_bytes"] = b"#!/bin/bash\nif then\n"
                elif kind == "version":
                    options["version"] = "0.1.7"
                commit = self._source(base, **options)
                if kind == "origin":
                    subprocess.run(["git", "-C", str(base / "src"), "remote", "set-url", "origin",
                                    "https://example.invalid/foreign.git"], check=True)
                result = self._run(base, "0.1.8", "--offline", "--development-commit", commit)
                self.assertNotEqual(result.returncode, 0)
                expected = {"origin": "expected", "manifest": "KILIX_REF",
                            "selector": "running selector does not match",
                            "updater": "invalid target updater", "version": "VERSION reads"}
                self.assertIn(expected[kind], result.stderr)
                self.assertEqual(env.read_bytes(), before)
                self.assertEqual(self._recovery_records(base), [])

    def test_development_commit_still_checks_real_component_histories(self):
        for missing in (False, True):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                sources = base / "home" / ".local" / "gpu_terminal" / "sources"
                pleb = self._component_history(sources / "pleb")
                kilix = self._component_history(sources / "kilix")
                kilix95 = self._component_history(sources / "kilix-desktops" / "kilix-95")
                manifest = self._manifest_text(PLEB_REF="f" * 40 if missing else pleb[0],
                                               KILIX_REF=kilix[1], KILIX95_REF=kilix95[1])
                commit = self._source(base, manifest, tag=None)
                installed = dict(INSTALLED_RELEASE_VALUES, PLEBIAN_OS_REF=commit,
                                 PLEB_REF=pleb[1], KILIX_REF=kilix[0], KILIX95_REF=kilix95[0])
                env = self._machine(base, release=list(installed.items()))
                before = env.read_bytes()
                result = self._run(base, "0.1.8", "--offline", "--dry-run",
                                   "--development-commit", commit, check_ancestry=True)
                self.assertEqual(env.read_bytes(), before)
                self.assertEqual(self._recovery_records(base), [])
                if missing:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("--offline forbids fetching", result.stderr)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(f"component Pleb: {pleb[1][:12]} -> {pleb[0][:12]} (DOWNGRADE;", result.stderr)
                    self.assertIn(f"component Kilix: {kilix[0][:12]} -> {kilix[1][:12]} (forward;", result.stdout)

    def test_development_commit_dry_run_and_failed_transaction_preserve_state(self):
        for boundary in (None, "render", "verify", "backup", "stage", "selector", "updater"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                env = self._machine(base)
                before = env.read_bytes()
                commit = self._source(base, tag=None)
                tools = base / "root" / "usr" / "local" / "bin"
                originals = {}
                for name in ("plebian-os-select-closure", "plebian-os-update"):
                    originals[name] = f"#!/bin/sh\necho {name}\n".encode()
                    (tools / name).write_bytes(originals[name])
                    (tools / name).chmod(0o710)
                args = ("--dry-run",) if boundary is None else ()
                result = self._run(base, "0.1.8", "--offline", "--development-commit", commit,
                                   *args, fail_after=boundary)
                if boundary is None:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("nothing was written", result.stdout)
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("injected", result.stderr)
                self.assertEqual(env.read_bytes(), before)
                self.assertEqual(self._recovery_records(base), [])
                for name, content in originals.items():
                    self.assertEqual((tools / name).read_bytes(), content)
                    self.assertEqual((tools / name).stat().st_mode & 0o777, 0o710)

    def test_0_2_1_selects_every_f120_root_tuple_and_bound_input(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            commit = self._source(
                base,
                self._f120_manifest_text(),
                version="0.2.1",
                release="0.2.1",
                tag="v0.2.1",
                requirements_text=(
                    ROOT / "releases" / "0.2.1.requirements"
                ).read_text(),
            )
            result = self._run(base, "0.2.1", "--offline")
            self.assertEqual(result.returncode, 0, result.stderr)
            after = self._values(env)
            for key, expected in F120_ROOT_VALUES.items():
                with self.subTest(key=key):
                    self.assertEqual(after[key], expected)
            self.assertEqual(
                after["PLEBIAN_OS_UV_INSTALLER_MAX_BYTES"], "71225")
            self.assertEqual(after["PLEBIAN_OS_INSTALL_WAYDROID"], "1")
            self.assertEqual(
                after["PLEBIAN_OS_WAYDROID_CLOSURE_SHA256"],
                "4f2fef049ab669fc43d7873c2e1c55ad180fec13d730cad681645e60a8410a33",
            )
            self.assertNotIn("PLEBIAN_OS_NETINST_MAX_BYTES", after)
            self.assertIn(
                "PLEBIAN_OS_NETINST_MAX_BYTES: validated, image-build input only",
                result.stdout,
            )
            self.assertEqual(after["PLEBIAN_OS_REF"], commit)
            closure = env.with_name("closure.env")
            self.assertTrue(closure.is_file())
            self.assertEqual(closure.stat().st_mode & 0o777, 0o644)
            self.assertIn("hand editing is unsupported", closure.read_text())
            session_text = env.read_text()
            self.assertNotIn("${PLEB_REF+x}", session_text)
            self.assertNotIn("${KILIX_REF+x}", session_text)
            self.assertIn(
                "PLEB_RESPAWN=0   # operator note, deliberately unguarded",
                session_text,
            )
            pair_before = (env.read_bytes(), closure.read_bytes())
            repeated = self._run(base, "0.2.1", "--offline")
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertEqual((env.read_bytes(), closure.read_bytes()), pair_before)

    def test_0_2_1_proves_all_nine_component_public_refs(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sources = base / "home/.local/gpu_terminal/sources"
            pleb_dir = sources / "pleb"
            kilix_dir = sources / "kilix"
            kilix95_dir = sources / "kilix-desktops/kilix-95"
            pleb = self._component_history(pleb_dir, count=1)
            kilix = self._component_history(kilix_dir, count=1)
            kilix95 = self._component_history(kilix95_dir, count=1)
            root_specs = (
                ("kilix-system-monitor", "KILIX_SYSTEM_MONITOR", "Kilix System Monitor"),
                ("kilix-desktop-sdk", "KILIX_DESKTOP_SDK", "Kilix Desktop SDK"),
                ("kilix-icewm", "KILIX_ICEWM", "Kilix IceWM"),
                ("kilix-media-sdk", "KILIX_MEDIA_SDK", "Kilix Media SDK"),
                ("kilix-waydroid", "KILIX_WAYDROID", "Kilix Waydroid"),
            )
            changes = {
                "PLEB_REF": pleb[0],
                "KILIX_REF": kilix[0],
                "KILIX95_REF": kilix95[0],
            }
            root_sources = {}
            for cache_name, prefix, _ in root_specs:
                source = base / "component-sources" / cache_name
                commit = self._component_history(source, count=1)[0]
                changes[f"{prefix}_REF"] = commit
                root_sources[cache_name] = source
            os_commit = self._source(
                base,
                self._f120_manifest_text(**changes),
                version="0.2.1",
                release="0.2.1",
                tag="v0.2.1",
                requirements_text=(
                    ROOT / "releases/0.2.1.requirements"
                ).read_text(),
            )
            self._seed_core_public_caches(
                base, pleb_dir, kilix_dir, kilix95_dir)
            for cache_name, prefix, _ in root_specs:
                self._seed_public_cache(
                    base, cache_name, F120_ROOT_VALUES[f"{prefix}_REPO"],
                    root_sources[cache_name],
                )
            installed = dict(INSTALLED_RELEASE_VALUES)
            installed.update({
                "PLEBIAN_OS_REF": os_commit,
                "PLEB_REF": pleb[0],
                "KILIX_REF": kilix[0],
                "KILIX95_REF": kilix95[0],
            })
            self._machine(base, release=list(installed.items()))

            result = self._run(
                base, "0.2.1", "--offline", "--dry-run", check_ancestry=True)

            self.assertEqual(result.returncode, 0, result.stderr)
            report = result.stdout + result.stderr
            labels = (
                "Plebian-OS", "Pleb", "Kilix", "Kilix 95",
                *(item[2] for item in root_specs),
            )
            for label in labels:
                self.assertIn(f"component {label}:", report)
            self.assertEqual(report.count("component "), 9)

    def test_0_2_1_requirements_refuse_different_debian_inputs(self):
        mutations = {
            "PLEBIAN_OS_NETINST_URL": "https://example.invalid/netinst.iso",
            "PLEBIAN_OS_NETINST_SHA256": "0" * 64,
            "PLEBIAN_OS_NETINST_MAX_BYTES": "791674881",
            "PLEBIAN_OS_APT_SNAPSHOT": "20260824T000000Z",
        }
        for key, value in mutations.items():
            with self.subTest(key=key), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                self._machine(base)
                self._source(
                    base,
                    self._f120_manifest_text(**{key: value}),
                    version="0.2.1",
                    release="0.2.1",
                    tag="v0.2.1",
                    requirements_text=(
                        ROOT / "releases" / "0.2.1.requirements"
                    ).read_text(),
                )
                self._refuses(
                    base,
                    f"release requirements demand {key}=",
                    target="0.2.1",
                )

    def test_0_2_1_refuses_an_incomplete_f120_root_tuple(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(
                base,
                self._f120_manifest_text(drop=("KILIX_MEDIA_SDK_REF",)),
                version="0.2.1",
                release="0.2.1",
                tag="v0.2.1",
                requirements_text=(
                    ROOT / "releases" / "0.2.1.requirements"
                ).read_text(),
            )
            result = self._refuses(
                base, "KILIX_MEDIA_SDK_REF", target="0.2.1")
            self.assertIn("incomplete closure", result.stderr)

    def test_0_2_1_requirements_refuse_to_disable_waydroid(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(
                base,
                self._f120_manifest_text(
                    PLEBIAN_OS_INSTALL_WAYDROID="0",
                ),
                version="0.2.1",
                release="0.2.1",
                tag="v0.2.1",
                requirements_text=(
                    ROOT / "releases" / "0.2.1.requirements"
                ).read_text(),
            )
            self._refuses(
                base,
                "release requirements demand PLEBIAN_OS_INSTALL_WAYDROID=1",
                target="0.2.1",
            )

    def test_0_2_1_selector_independently_requires_waydroid(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            requirements = "\n".join(
                line for line in (
                    ROOT / "releases" / "0.2.1.requirements"
                ).read_text().splitlines()
                if not line.startswith("PLEBIAN_OS_INSTALL_WAYDROID=")
                and not line.startswith(
                    "PLEBIAN_OS_WAYDROID_CLOSURE_SHA256="
                )
            ) + "\n"
            self._source(
                base,
                self._f120_manifest_text(
                    PLEBIAN_OS_INSTALL_WAYDROID="0",
                    PLEBIAN_OS_WAYDROID_CLOSURE_SHA256="",
                ),
                version="0.2.1",
                release="0.2.1",
                tag="v0.2.1",
                requirements_text=requirements,
            )
            self._refuses(
                base,
                "0.2.1 requires PLEBIAN_OS_INSTALL_WAYDROID=1",
                target="0.2.1",
            )

    def test_0_2_1_split_transaction_restores_every_write_boundary(self):
        boundaries = ("backup", "stage", "selector", "updater", "session", "closure")
        for boundary in boundaries:
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                env = self._machine(base)
                before = env.read_bytes()
                self._source(
                    base,
                    self._f120_manifest_text(),
                    version="0.2.1",
                    release="0.2.1",
                    tag="v0.2.1",
                    requirements_text=(
                        ROOT / "releases" / "0.2.1.requirements"
                    ).read_text(),
                )
                result = self._run(
                    base, "0.2.1", "--offline", fail_after=boundary)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual(env.read_bytes(), before)
                self.assertFalse(env.with_name("closure.env").exists())
                self.assertFalse(
                    (base / "root/usr/local/bin/plebian-os-select-closure").exists())
                self.assertFalse(
                    (base / "root/usr/local/bin/plebian-os-update").exists())
                self.assertEqual(self._recovery_records(base), [])

    def test_split_migration_refuses_an_ambiguous_release_pin_edit(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            session = self._machine(base)
            with session.open("a") as stream:
                stream.write(f"if true; then PLEB_REF={'e' * 40}; fi\n")
            self._source(
                base,
                self._f120_manifest_text(),
                version="0.2.1",
                release="0.2.1",
                tag="v0.2.1",
                requirements_text=(
                    ROOT / "releases" / "0.2.1.requirements"
                ).read_text(),
            )
            self._refuses(
                base, "sets release-controlled key PLEB_REF in an ambiguous form",
                target="0.2.1",
            )

    def test_0_2_1_split_rollback_retains_selected_pair_at_every_boundary(self):
        boundaries = (
            "rollback-stage", "rollback-closure", "rollback-session",
            "rollback-updater", "rollback-selector",
        )
        for boundary in boundaries:
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                session = self._machine(base)
                self._source(
                    base,
                    self._f120_manifest_text(),
                    version="0.2.1",
                    release="0.2.1",
                    tag="v0.2.1",
                    requirements_text=(
                        ROOT / "releases" / "0.2.1.requirements"
                    ).read_text(),
                )
                selected = self._run(base, "0.2.1", "--offline")
                self.assertEqual(selected.returncode, 0, selected.stderr)
                closure = session.with_name("closure.env")
                selector = base / "root/usr/local/bin/plebian-os-select-closure"
                updater = base / "root/usr/local/bin/plebian-os-update"
                selected_bytes = tuple(
                    path.read_bytes() for path in (session, closure, selector, updater)
                )
                failed = self._run(base, "--rollback", fail_after=boundary)
                self.assertNotEqual(failed.returncode, 0, failed.stdout)
                self.assertIn("retained", failed.stderr)
                self.assertEqual(
                    tuple(path.read_bytes() for path in (session, closure, selector, updater)),
                    selected_bytes,
                )
                retried = self._run(base, "--rollback")
                self.assertEqual(retried.returncode, 0, retried.stderr)

    def test_image_source_refusal_precedes_selection_and_clean_retry_keeps_caller_lock(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sources = base / "home/.local/gpu_terminal/sources"
            pleb, kilix, kilix95 = sources / "pleb", sources / "kilix", sources / "kilix-desktops/kilix-95"
            histories = [self._component_history(repo) for repo in (pleb, kilix, kilix95)]
            pins = dict(zip(("PLEB_REF", "KILIX_REF", "KILIX95_REF"), (h[-1] for h in histories)))
            os_head = self._source(base, self._manifest_text(**pins))
            previous = {**dict(INSTALLED_RELEASE_VALUES), "PLEBIAN_OS_REF": os_head,
                        **dict(zip(pins, (h[0] for h in histories)))}
            session = self._machine(base, release=list(previous.items()))
            before = session.read_bytes()
            self._seed_core_public_caches(base, pleb, kilix, kilix95)
            for repo, history in zip((pleb, kilix, kilix95), histories):
                subprocess.run(["git", "-C", str(repo), "checkout", "-q", "--detach", history[0]], check=True)
            owner = pleb / "operator.bin"
            owner.write_bytes(b"owner bytes\x00\xff")
            state = base / "home/.local/gpu_terminal/pleb/state"
            state.mkdir(parents=True)
            lock = state / "update.lock"
            fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                args = dict(check_ancestry=True, pass_fds=(fd,), env_extra={"PLEB_UPDATE_LOCK_FD": str(fd)})
                refused = self._run(base, "0.1.8", "--offline", **args)
                self.assertNotEqual(refused.returncode, 0)
                self.assertIn("has local changes; refusing a whole-stack update", refused.stderr)
                self.assertEqual(session.read_bytes(), before)
                self.assertFalse(session.with_name("closure.env").exists())
                self.assertFalse((base / "root/usr/local/bin/plebian-os-update").exists())
                self.assertEqual(owner.read_bytes(), b"owner bytes\x00\xff")
                for repo, history in zip((pleb, kilix, kilix95), histories):
                    self.assertEqual(subprocess.check_output(
                        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(), history[0])
                owner.replace(base / "operator-moved-aside.bin")
                selected = self._run(base, "0.1.8", "--offline", **args)
                self.assertEqual(selected.returncode, 0, selected.stderr)
                self.assertEqual(self._values(session)["PLEB_REF"], pins["PLEB_REF"])
                self.assertEqual((base / "operator-moved-aside.bin").read_bytes(), b"owner bytes\x00\xff")
                competitor = os.open(lock, os.O_RDWR)
                try:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    os.close(competitor)
            finally:
                os.close(fd)

    def _selected_split_fixture(self, base):
        session = self._machine(base)
        self._source(
            base, self._f120_manifest_text(), version="0.2.1",
            release="0.2.1", tag="v0.2.1",
            requirements_text=(ROOT / "releases/0.2.1.requirements").read_text())
        selected = self._run(base, "0.2.1", "--offline")
        self.assertEqual(selected.returncode, 0, selected.stderr)
        return session

    def test_a_repeated_hop_rollback_finds_its_own_spent_record_and_succeeds(self):
        """The hop driver died after this rollback ran, before it cleared its
        own marker; its recovery asks again with the same trusted tag. The
        call pattern is the published driver's: --rollback and the tag object."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            session = self._selected_split_fixture(base)
            closure = session.with_name("closure.env")
            tag = subprocess.run(
                ["git", "-C", str(base / "src"), "rev-parse", "refs/tags/v0.2.1"],
                capture_output=True, text=True, check=True).stdout.strip()
            # The hop driver names the split layout, as it does on every call.
            tagged = {"PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA": tag,
                      "PLEBIAN_OS_CLOSURE_LAYOUT": "split"}
            first = self._run(base, "--rollback", env_extra=tagged)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertFalse(closure.exists())
            restored = session.read_bytes()
            again = self._run(base, "--rollback", env_extra=tagged)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertIn("already rolled back", again.stdout)
            self.assertEqual(session.read_bytes(), restored)
            self.assertFalse(closure.exists())
            # A manual rollback, another hop's tag, or a closure that is not the
            # one the record saved is still the hard failure.
            manual = self._run(base, "--rollback",
                               env_extra={"PLEBIAN_OS_CLOSURE_LAYOUT": "split"})
            self.assertNotEqual(manual.returncode, 0)
            self.assertIn("no split closure to roll back to", manual.stderr)
            other = self._run(base, "--rollback", env_extra={
                "PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA": "1" * 40,
                "PLEBIAN_OS_CLOSURE_LAYOUT": "split"})
            self.assertNotEqual(other.returncode, 0)
            self.assertIn("no split closure to roll back to", other.stderr)
            with session.open("a") as stream:
                stream.write("OPERATOR_NOTE=changed-since\n")
            moved = self._run(base, "--rollback", env_extra=tagged)
            self.assertNotEqual(moved.returncode, 0)
            self.assertIn("is already restored and the installed session or closure has changed since",
                          moved.stderr)
            self.assertIn("release-hop/active", moved.stderr)
            closure.write_text("PLEBIAN_OS_VERSION=0.2.1\n")
            selected = self._run(base, "--rollback", env_extra=tagged)
            self.assertNotEqual(selected.returncode, 0)

    def test_a_repeated_hop_rollback_never_walks_back_to_an_older_record(self):
        """Records are never pruned and a completed hop leaves its record
        unspent, so a machine with selection history has an older unspent
        record when a later hop is rolled back twice. The repeat must answer
        from the hop's own spent record and must not restore the older one,
        whether the older record carries another tag or the same one."""
        for older in ("another tag", "the same tag"):
            with self.subTest(older=older), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                session = self._selected_split_fixture(base)
                tag = subprocess.run(
                    ["git", "-C", str(base / "src"), "rev-parse", "refs/tags/v0.2.1"],
                    capture_output=True, text=True, check=True).stdout.strip()
                own = self._recovery_records(base)[0]
                earlier = own.parent / "closure-rollback.20200101T000000Z.AAAAAA"
                shutil.copytree(own, earlier)
                (earlier / "session.env").write_bytes(b"# an older hop's saved session\n")
                if older == "another tag":
                    meta = (earlier / "meta").read_text().replace(tag, "2" * 40)
                    (earlier / "meta").write_text(meta)
                tagged = {"PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA": tag,
                          "PLEBIAN_OS_CLOSURE_LAYOUT": "split"}
                first = self._run(base, "--rollback", env_extra=tagged)
                self.assertEqual(first.returncode, 0, first.stderr)
                self.assertTrue((own / "restored").exists())
                restored = session.read_bytes()
                self.assertNotEqual(restored, b"# an older hop's saved session\n")
                again = self._run(base, "--rollback", env_extra=tagged)
                self.assertEqual(again.returncode, 0, again.stderr)
                self.assertIn("already rolled back", again.stdout)
                self.assertEqual(session.read_bytes(), restored)
                self.assertFalse((earlier / "restored").exists(), "the older record is untouched")
                # Without a trusted tag a rollback is a deliberate one and still
                # undoes the older hop, as it always did.
                manual = self._run(base, "--rollback",
                                   env_extra={"PLEBIAN_OS_CLOSURE_LAYOUT": "split"})
                self.assertEqual(manual.returncode, 0, manual.stderr)
                self.assertTrue((earlier / "restored").exists())

    def test_real_pleb_recovery_settles_a_hop_whose_record_is_already_restored(self):
        """The state a dropped terminal leaves: the selector's record is stamped
        restored, the closure is the pre-hop one, and Pleb's hop marker still
        says `selected`. Real Pleb recovery drives the real selector."""
        pleb_repo = os.environ.get("PLEBIAN_OS_PLEB_REPO")
        if not pleb_repo or not (Path(pleb_repo) / "bin/pleb").is_file():
            self.skipTest("PLEBIAN_OS_PLEB_REPO is not set")
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            session = self._selected_split_fixture(base)
            closure = session.with_name("closure.env")
            src = base / "src"
            commit = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"],
                                    capture_output=True, text=True, check=True).stdout.strip()
            tag = subprocess.run(["git", "-C", str(src), "rev-parse", "refs/tags/v0.2.1"],
                                 capture_output=True, text=True, check=True).stdout.strip()
            record = self._recovery_records(base)[0]
            baseline = [hashlib.sha256((record / "session.env").read_bytes()).hexdigest(), "absent"]
            tagged = {"PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA": tag,
                      "PLEBIAN_OS_CLOSURE_LAYOUT": "split"}
            first = self._run(base, "--rollback", env_extra=tagged)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertTrue((record / "restored").exists())
            original = session.read_bytes()
            # Pleb's side of the dropped hop: the cache, and the hop marker.
            home = base / "home"
            storage = home / ".local/gpu_terminal/pleb"
            state = storage / "state/release-hop"
            cache = storage / "cache/release-hop"
            for directory in (state, cache / "selectors", cache / "tag-trust"):
                directory.mkdir(parents=True, mode=0o700, exist_ok=True)
            repo = cache / "plebian-os.git"
            origin = dict(INSTALLED_RELEASE_VALUES)["PLEBIAN_OS_REPO"]
            subprocess.run(["git", "init", "-q", "--bare", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", origin], check=True)
            subprocess.run(["git", "-C", str(repo), "fetch", "-q", str(src),
                            "refs/tags/v0.2.1:refs/tags/v0.2.1"], check=True)
            (cache / "selectors" / commit).write_bytes(SELECT.read_bytes())
            (cache / "selectors" / commit).chmod(0o755)
            (state / "active").write_text("\n".join((
                "0.2.1", commit, tag, hashlib.sha256(SELECT.read_bytes()).hexdigest(),
                "v0.2.1")) + "\n")
            (state / "baseline").write_text("\n".join(baseline) + "\n")
            (state / "phase").write_text("selected\n")
            updater_log = base / "updater.log"
            fake = base / "fake-updater"
            fake.write_text(f"#!/bin/sh\necho \"$@\" >>{shlex.quote(str(updater_log))}\n")
            fake.chmod(0o755)
            root = base / "root"
            env = {
                "HOME": str(home), "PATH": os.environ["PATH"], "LANG": "C",
                "GPU_TERMINAL_HOME": str(home / ".local/gpu_terminal"),
                "PLEB_STORAGE_HOME": str(storage),
                "PLEB_ENV_SYSTEM": str(session), "PLEB_CLOSURE_SYSTEM": str(closure),
                "PLEB_ENV_USER": str(base / "no-user-session.env"),
                "PLEB_CLOSURE_USER": str(base / "no-user-closure.env"),
                "PLEBIAN_OS_MANAGED_INSTALL": "1",
                "PLEBIAN_OS_CLOSURE_TEST_ROOT": str(root),
                "PLEBIAN_OS_RECOVERY_BASE": str(root / "var/lib/plebian-os"),
                "PLEBIAN_OS_SELECTOR_DST": str(root / "usr/local/bin/plebian-os-select-closure"),
                "PLEBIAN_OS_UPDATER_DST": str(fake),
                "PLEBIAN_OS_SELECT_TEST_SKIP_COMPONENT_ANCESTRY": "1",
            }
            for name in ("kilix", "kilix-desktops/kilix-95"):
                directory = home / ".local/gpu_terminal/sources" / name
                directory.mkdir(parents=True)
                subprocess.run(["git", "init", "-q", str(directory)], check=True)
            recovered = subprocess.run(
                [str(Path(pleb_repo) / "bin/pleb"), "update", "--rollback", "--no-restart"],
                env=env, capture_output=True, text=True, check=False, timeout=120)
            self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
            self.assertIn("already rolled back", recovered.stdout + recovered.stderr)
            self.assertFalse((state / "active").exists())
            self.assertEqual(updater_log.read_text().strip(), "--revalidate-current")
            self.assertEqual(session.read_bytes(), original)
            self.assertFalse(closure.exists())

    # ── a finished rollback settles the hop marker Pleb left behind ─────────
    def _hop_marker(self, base, tag, lines=4, phase="selected", tag_line="v0.2.1",
                    target="0.2.1", commit="a" * 40, selector_sha="b" * 64, extra=None):
        state = base / "home/.local/gpu_terminal/pleb/state"
        marker = state / "release-hop"
        marker.mkdir(parents=True, exist_ok=True, mode=0o700)
        rows = [target, commit, tag, selector_sha, tag_line][:lines]
        if extra:
            rows.append(extra)
        (marker / "active").write_text("\n".join(rows) + "\n")
        (marker / "phase").write_text(phase + "\n")
        (marker / "baseline").write_text("absent\nabsent\n")
        return marker

    def _spent_hop(self, base):
        session = self._selected_split_fixture(base)
        tag = subprocess.run(
            ["git", "-C", str(base / "src"), "rev-parse", "refs/tags/v0.2.1"],
            capture_output=True, text=True, check=True).stdout.strip()
        tagged = {"PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA": tag,
                  "PLEBIAN_OS_CLOSURE_LAYOUT": "split"}
        return session, tag, tagged

    def test_a_finished_rollback_settles_the_hop_marker_it_belongs_to(self):
        for lines in (4, 5):
            for retained in (False, True):
                for repeat in (False, True):
                    with self.subTest(lines=lines, retained=retained, repeat=repeat), \
                            tempfile.TemporaryDirectory() as td:
                        base = Path(td)
                        session, tag, tagged = self._spent_hop(base)
                        state = base / "home/.local/gpu_terminal/pleb/state"
                        if repeat:
                            first = self._run(base, "--rollback", env_extra=tagged)
                            self.assertEqual(first.returncode, 0, first.stderr)
                        marker = self._hop_marker(base, tag, lines)
                        (marker / "unselected-checkouts").write_text("kept\n")
                        if retained:
                            kept = state / "stack-rollback.Kept01"
                            kept.mkdir(parents=True, mode=0o700)
                            (kept / "owner").write_text("pid=999999\nstart=1\nboot=gone\n")
                            (kept / "failure-reason").write_text("rollback-complete: no\n")
                        result = self._run(base, "--rollback", env_extra=tagged)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        if repeat:
                            self.assertIn("already rolled back", result.stdout)
                        names = {p.name for p in marker.iterdir()}
                        if retained:
                            self.assertTrue({"active", "phase", "baseline"} <= names, names)
                            self.assertNotIn("settled", result.stdout)
                        else:
                            self.assertEqual(names, {"unselected-checkouts"}, names)
                            self.assertIn("settled the interrupted release hop's marker",
                                          result.stdout)
                            self.assertIn("the closure was already restored", result.stdout)

    def test_the_hop_marker_is_left_alone_unless_it_is_provably_this_hops(self):
        cases = {
            "another tag object": dict(tag="2" * 40),
            "a complete hop": dict(phase="complete"),
            "a driver mid-rollback": dict(phase="rolling-back"),
            "a malformed marker": dict(lines=3),
            "six lines": dict(lines=5, extra="v0.2.1"),
            "a bad release on line 1": dict(target="0.2"),
            "a bad commit on line 2": dict(commit="nothex"),
            "a bad selector hash on line 4": dict(selector_sha="c" * 63),
            "a bad tag on line 5": dict(lines=5, tag_line="0.2.1"),
            "an unknown phase": dict(phase="sideways"),
        }
        for name, change in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                session, tag, tagged = self._spent_hop(base)
                options = {"tag": tag, **change}
                marker = self._hop_marker(base, options.pop("tag"), **options)
                result = self._run(base, "--rollback", env_extra=tagged)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual({p.name for p in marker.iterdir()},
                                 {"active", "phase", "baseline"})
        with self.subTest(case="a symlinked release-hop directory"), tempfile.TemporaryDirectory() as td:
            base = Path(td)
            session, tag, tagged = self._spent_hop(base)
            marker = self._hop_marker(base, tag)
            real = marker.with_name("release-hop.real")
            marker.rename(real)
            marker.symlink_to(real)
            result = self._run(base, "--rollback", env_extra=tagged)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((real / "active").exists())
        with self.subTest(case="a symlinked marker file"), tempfile.TemporaryDirectory() as td:
            base = Path(td)
            session, tag, tagged = self._spent_hop(base)
            marker = self._hop_marker(base, tag)
            real = marker / "active.real"
            (marker / "active").rename(real)
            (marker / "active").symlink_to(real)
            result = self._run(base, "--rollback", env_extra=tagged)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((marker / "phase").exists())
        with self.subTest(case="a request with no trusted tag"), tempfile.TemporaryDirectory() as td:
            base = Path(td)
            session, tag, tagged = self._spent_hop(base)
            marker = self._hop_marker(base, tag)
            result = self._run(base, "--rollback",
                               env_extra={"PLEBIAN_OS_CLOSURE_LAYOUT": "split"})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((marker / "active").exists())
        with self.subTest(case="a standalone machine"), tempfile.TemporaryDirectory() as td:
            # Pleb's own recovery also puts a standalone machine's checkouts
            # back, so its marker stays.
            base = Path(td)
            session, tag, tagged = self._spent_hop(base)
            marker = self._hop_marker(base, tag)
            result = self._run(base, "--rollback", env_extra={
                **tagged, "PLEBIAN_OS_SELECTOR_MODE": "standalone",
                "PLEBIAN_OS_SELECTOR_DST": "", "PLEBIAN_OS_UPDATER_DST": ""})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("previous split closure restored", result.stdout)
            self.assertEqual({p.name for p in marker.iterdir()},
                             {"active", "phase", "baseline"})
        with self.subTest(case="a failed rollback"), tempfile.TemporaryDirectory() as td:
            base = Path(td)
            session, tag, tagged = self._spent_hop(base)
            marker = self._hop_marker(base, tag)
            failed = self._run(base, "--rollback", env_extra=tagged,
                               fail_after="rollback-session")
            self.assertNotEqual(failed.returncode, 0)
            self.assertTrue((marker / "active").exists())

    def test_the_published_022_recovery_finds_nothing_after_the_marker_is_settled(self):
        """2dd44b0's own recovery, unchanged: with the marker its 4-line form
        left behind it tries to recover the hop (and a plain pleb update could
        not finish that); once the rollback settled the marker it returns at
        once with nothing to do."""
        pleb_repo = os.environ.get("PLEBIAN_OS_PLEB_REPO")
        if not pleb_repo:
            self.skipTest("PLEBIAN_OS_PLEB_REPO is not set")
        published = subprocess.run(
            ["git", "-C", pleb_repo, "cat-file", "-t", "2dd44b0"],
            capture_output=True, text=True)
        if published.returncode != 0:
            self.skipTest("the 0.2.2 Pleb commit is not in PLEBIAN_OS_PLEB_REPO")
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            old = base / "pleb-022"
            old.mkdir()
            archive = subprocess.Popen(["git", "-C", pleb_repo, "archive", "2dd44b0"],
                                       stdout=subprocess.PIPE)
            subprocess.run(["tar", "-x", "-C", str(old)], stdin=archive.stdout, check=True)
            archive.stdout.close()
            self.assertEqual(archive.wait(), 0)
            session, tag, tagged = self._spent_hop(base)
            marker = self._hop_marker(base, tag, lines=4, target="0.2.1")
            storage = base / "home/.local/gpu_terminal/pleb"
            env = {"HOME": str(base / "home"), "PATH": os.environ["PATH"], "LANG": "C",
                   "PLEB_STORAGE_HOME": str(storage),
                   "PLEB_STATE_HOME": str(storage / "state"),
                   "PLEB_CACHE_HOME": str(storage / "cache")}
            def recover():
                return subprocess.run(
                    ["bash", "-euo", "pipefail", "-c",
                     f"PLEB_ROOT={old}; . {old}/lib/common.sh; . {old}/lib/closure.sh\n"
                     'pleb_recover_incomplete_release_hop\n'
                     'echo "RESULT=[${_PLEB_HOP_RECOVERY_RESULT:-}]"'],
                    env=env, capture_output=True, text=True, check=False)
            before = recover()
            self.assertNotEqual(before.returncode, 0, "the marker is still an interrupted hop")
            rolled = self._run(base, "--rollback", env_extra=tagged)
            self.assertEqual(rolled.returncode, 0, rolled.stderr)
            self.assertFalse((marker / "active").exists())
            after = recover()
            self.assertEqual((after.returncode, after.stdout, after.stderr),
                             (0, "RESULT=[]\n", ""))

    def test_a_hop_rollback_never_walks_back_to_an_older_record(self):
        """Once the newest record is this tag's own and spent, nothing falls
        through to an older one, whatever the installed state or timing is."""
        with self.subTest(case="the closure changed after the rollback"), \
                tempfile.TemporaryDirectory() as td:
            base = Path(td)
            session, tag, tagged = self._spent_hop(base)
            own = self._recovery_records(base)[0]
            earlier = own.parent / "closure-rollback.20200101T000000Z.AAAAAA"
            shutil.copytree(own, earlier)
            (earlier / "session.env").write_bytes(b"# an older hop's saved session\n")
            first = self._run(base, "--rollback", env_extra=tagged)
            self.assertEqual(first.returncode, 0, first.stderr)
            with session.open("a") as stream:
                stream.write("OPERATOR_NOTE=changed-since\n")
            kept = session.read_bytes()
            again = self._run(base, "--rollback", env_extra=tagged)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual(session.read_bytes(), kept)
            self.assertFalse((earlier / "restored").exists())
        with self.subTest(case="two newest records in one second"), \
                tempfile.TemporaryDirectory() as td:
            base = Path(td)
            session, tag, tagged = self._spent_hop(base)
            own = self._recovery_records(base)[0]
            twin = own.parent / (own.name.rsplit(".", 1)[0] + ".TWIN01")
            shutil.copytree(own, twin)
            (twin / "restored").write_text("restored=2026-11-17T00:00:00Z\n")
            before = session.read_bytes()
            refused = self._run(base, "--rollback", env_extra=tagged)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("cannot tell which recovery record is newest", refused.stderr)
            self.assertEqual(session.read_bytes(), before)
            self.assertFalse((own / "restored").exists())

    def test_an_unspent_newest_record_is_restored_even_when_the_closure_looks_saved(self):
        """The 'already rolled back' answer needs the newest record to be spent.
        An unspent one whose saved session and closure happen to be installed
        still has the selector and updater to put back."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            session, tag, tagged = self._spent_hop(base)
            record = self._recovery_records(base)[0]
            session.write_bytes((record / "session.env").read_bytes())
            session.with_name("closure.env").unlink()
            selector = base / "root/usr/local/bin/plebian-os-select-closure"
            updater = base / "root/usr/local/bin/plebian-os-update"
            self.assertTrue(selector.exists() and updater.exists())
            result = self._run(base, "--rollback", env_extra=tagged)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("already rolled back", result.stdout)
            self.assertTrue((record / "restored").exists())
            self.assertFalse(selector.exists() or updater.exists())

    def test_a_selection_that_replaced_nothing_settles_only_a_selecting_marker(self):
        for phase, settled in (("selecting", True), ("selected", False)):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                env = self._machine(base)
                before = env.read_bytes()
                self._source(base)
                interrupted = self._run(base, "0.1.8", "--offline",
                                        fail_after="interrupt:render")
                self.assertEqual(interrupted.returncode, 130, interrupted.stderr)
                facts = self._pending(base).read_text().splitlines()
                marker = self._hop_marker(base, facts[1].split("=", 1)[1], phase=phase)
                result = self._rollback_for_pending_tag(base, facts[1])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("nothing was restored", result.stdout + result.stderr)
                self.assertEqual(env.read_bytes(), before)
                self.assertEqual((marker / "active").exists(), not settled)
                if settled:
                    self.assertIn("settled the interrupted release hop's marker", result.stdout)
                    self.assertIn("nothing was replaced", result.stdout)
                    self.assertNotIn("already restored", result.stdout)

    def test_an_interrupted_same_tag_reselect_settles_only_a_selecting_marker(self):
        for phase, settled in (("selecting", True), ("selected", False)):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                session, tag, tagged = self._spent_hop(base)
                attempt = base / "home/.local/gpu_terminal/pleb/state/selection-attempt"
                attempt.parent.mkdir(parents=True, exist_ok=True)
                attempt.write_text(f"format=1\ntag={tag}\ntarget=0.2.1\ninstalled=0.2.1\n")
                marker = self._hop_marker(base, tag, phase=phase)
                before = session.read_bytes()
                result = self._run(base, "--rollback", env_extra=tagged)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("interrupted reselect", result.stdout)
                self.assertEqual(session.read_bytes(), before)
                self.assertEqual((marker / "active").exists(), not settled)
                if settled:
                    self.assertIn("settled the interrupted release hop's marker", result.stdout)
                    self.assertIn("nothing was replaced", result.stdout)

    def test_a_rollback_not_bound_to_the_hops_own_record_leaves_the_marker(self):
        """A pending marker that no longer matches the files (disposition 2) is
        an ordinary rollback of the newest record, which may be an older hop's."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            original = env.read_bytes()
            self._source(base)
            interrupted = self._run(base, "0.1.8", "--offline", fail_after="interrupt:render")
            self.assertEqual(interrupted.returncode, 130, interrupted.stderr)
            pending = self._pending(base)
            text = pending.read_text()
            self.assertEqual(self._run(base, "0.1.8", "--offline").returncode, 0)
            pending.write_text(text)
            marker = self._hop_marker(base, text.splitlines()[1].split("=", 1)[1])
            result = self._rollback_for_pending_tag(base, text.splitlines()[1])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(env.read_bytes(), original)
            self.assertEqual({p.name for p in marker.iterdir()}, {"active", "phase", "baseline"})

    def test_a_rollback_leaves_a_durable_record_even_with_a_dead_terminal(self):
        """The terminal is often gone when the driver died, so the outcome lines
        are also appended to update.log in the Pleb state directory."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            session, tag, tagged = self._spent_hop(base)
            state = base / "home/.local/gpu_terminal/pleb/state"
            log = state / "update.log"
            self.assertFalse(log.exists(), "a selection records nothing")
            self._hop_marker(base, tag)
            log.write_text("2026-11-17T00:00:00Z earlier line\n")
            first = self._run(base, "--rollback", env_extra=tagged, dead_tty=True)
            self.addCleanup(first.kill)
            self.assertEqual(first.wait(timeout=60), 0)
            repeat = self._run(base, "--rollback", env_extra=tagged, dead_tty=True)
            self.addCleanup(repeat.kill)
            self.assertEqual(repeat.wait(timeout=60), 0)
            lines = log.read_text().splitlines()
            self.assertEqual(lines[0], "2026-11-17T00:00:00Z earlier line")
            for line in lines[1:]:
                self.assertRegex(
                    line, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ plebian-os-select-closure: \S")
                self.assertNotIn("\x1b", line)
            text = "\n".join(lines)
            self.assertIn("previous split closure restored from", text)
            self.assertIn("settled the interrupted release hop's marker", text)
            self.assertIn("the closure was already restored", text)
            self.assertIn("this selection was already rolled back", text)

    def test_a_refused_rollback_is_recorded_too(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            session, tag, tagged = self._spent_hop(base)
            self.assertEqual(self._run(base, "--rollback", env_extra=tagged).returncode, 0)
            with session.open("a") as stream:
                stream.write("OPERATOR_NOTE=changed-since\n")
            refused = self._run(base, "--rollback", env_extra=tagged)
            self.assertNotEqual(refused.returncode, 0)
            log = base / "home/.local/gpu_terminal/pleb/state/update.log"
            self.assertIn("is already restored and the installed session or closure has changed",
                          log.read_text())
            self.assertEqual(log.stat().st_mode & 0o777, 0o600)

    def test_a_failing_record_never_fails_the_rollback_and_is_never_followed_through_a_link(self):
        for case in ("a symlinked update.log", "an unwritable state directory",
                     "a symlinked state directory"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                session, tag, tagged = self._spent_hop(base)
                state = base / "home/.local/gpu_terminal/pleb/state"
                state.mkdir(parents=True, exist_ok=True)
                victim = base / "victim"
                victim.write_text("untouched\n")
                if case == "a symlinked update.log":
                    (state / "update.log").symlink_to(victim)
                elif case == "an unwritable state directory":
                    state.chmod(0o500)
                else:
                    elsewhere = base / "elsewhere"
                    state.rename(elsewhere)
                    state.symlink_to(elsewhere)
                try:
                    result = self._run(base, "--rollback", env_extra=tagged)
                finally:
                    if state.is_dir() and not state.is_symlink():
                        state.chmod(0o700)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("previous split closure restored", result.stdout)
                self.assertEqual(victim.read_text(), "untouched\n")
                if case == "a symlinked state directory":
                    self.assertFalse((elsewhere / "update.log").exists())

    def test_a_rollback_that_waits_out_a_running_update_does_not_settle_the_marker(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env, original, selected, updater, fifo = self._select_with_running_update(base)
            tag = subprocess.run(
                ["git", "-C", str(base / "src"), "rev-parse", "refs/tags/v0.1.8"],
                capture_output=True, text=True, check=True).stdout.strip()
            marker = self._hop_marker(base, tag)
            refused = self._run(base, "--rollback", env_extra={
                "PLEBIAN_OS_SELECT_UPDATE_WAIT_SECONDS": "1",
                "PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA": tag})
            self.assertEqual(refused.returncode, 13, refused.stderr)
            self.assertEqual({p.name for p in marker.iterdir()},
                             {"active", "phase", "baseline"})
            self._release(updater, fifo)

    def test_split_rollback_sync_failure_is_retryable(self):
        for fail_target in ("marker", "record"):
            with self.subTest(target=fail_target), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                session = self._selected_split_fixture(base)
                paths = (session, session.with_name("closure.env"),
                         base / "root/usr/local/bin/plebian-os-select-closure",
                         base / "root/usr/local/bin/plebian-os-update")
                before = tuple(p.read_bytes() for p in paths)
                record = self._recovery_records(base)[0]
                bindir = base / "mock-bin"
                bindir.mkdir()
                target = record / "restored" if fail_target == "marker" else record
                (bindir / "sync").write_text(
                    '#!/bin/sh\n[ "$2" != ' + shlex.quote(str(target)) + ' ]\n')
                (bindir / "sync").chmod(0o755)
                failed = self._run(base, "--rollback", env_extra={
                    "PATH": str(bindir) + ":" + os.environ["PATH"]})
                self.assertNotEqual(failed.returncode, 0)
                self.assertEqual(tuple(p.read_bytes() for p in paths), before)
                self.assertFalse((record / "restored").exists())
                retried = self._run(base, "--rollback")
                self.assertEqual(retried.returncode, 0, retried.stderr)

    def test_incomplete_compensation_keeps_current_operator_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            session = self._selected_split_fixture(base)
            with session.open("a") as stream:
                stream.write("OPERATOR_NOTE=keep-me\n")
            before = session.read_bytes()
            bindir = base / "mock-bin"
            bindir.mkdir()
            real_cp = shutil.which("cp")
            (bindir / "cp").write_text(
                '#!/bin/sh\ncase "$3" in */.closure-rollback-current.*/*) exit 1;; esac\n'
                + "exec " + shlex.quote(real_cp) + ' "$@"\n')
            (bindir / "cp").chmod(0o755)
            failed = self._run(base, "--rollback", fail_after="rollback-session",
                              env_extra={"PATH": str(bindir) + ":" + os.environ["PATH"]})
            self.assertNotEqual(failed.returncode, 0)
            snapshots = list((base / "root/var/lib/plebian-os").glob(
                ".closure-rollback-current.*"))
            self.assertEqual(len(snapshots), 1, failed.stderr)
            self.assertEqual((snapshots[0] / "session.env").read_bytes(), before)
            self.assertIn(str(snapshots[0]), failed.stderr)
            self.assertFalse((self._recovery_records(base)[0] / "restored").exists())

    def test_exported_release_metadata_is_canonical_and_old_records_still_restore(self):
        for old_record in (False, True):
            with self.subTest(old_record=old_record), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                session = self._machine(base, release=self._release_values("0.2.2"))
                text = session.read_text()
                for key, value in (("PLEBIAN_OS_VERSION", "0.2.2"),
                                   ("PLEBIAN_OS_RELEASE_MODE", "1")):
                    text = text.replace(guarded(key, value), f'export {key}="{value}"')
                session.write_text(text)
                self._source(
                    base, (ROOT / "releases/0.2.2.env").read_text(),
                    version="0.2.2", release="0.2.2", tag="v0.2.2",
                    requirements_text=(ROOT / "releases/0.2.2.requirements").read_text())
                selected = self._run(base, "0.2.2", "--offline")
                self.assertEqual(selected.returncode, 0, selected.stderr)
                metadata = self._recovery_records(base)[0] / "release-metadata.env"
                self.assertEqual(metadata.read_text(),
                                 "PLEBIAN_OS_VERSION=0.2.2\nPLEBIAN_OS_RELEASE_MODE=1\n")
                if old_record:
                    metadata.unlink()
                self._leave_install_snapshot(base)
                restored = self._run(base, "--rollback")
                self.assertEqual(restored.returncode, 0, restored.stderr)
                self.assertEqual(session.read_text(), text)

    def test_recovery_metadata_parser_accepts_literals_and_refuses_ambiguity(self):
        source = SELECT.read_text()
        start = source.index("record_release_value() {")
        function = source[start:source.index("\n}\n", start) + 3]
        # All privileged transactions receive the same standalone data parser.
        self.assertEqual(source.count("declare -f record_release_value"), 4)
        cases = [
            ('export PLEBIAN_OS_VERSION="0.2.2"', "0.2.2"),
            ("PLEBIAN_OS_VERSION='0.2.2'", "0.2.2"),
            (r"PLEBIAN_OS_VERSION=0\.2\.2", "0.2.2"),
            ('PLEBIAN_OS_VERSION=0."2".2', "0.2.2"),
            (guarded("PLEBIAN_OS_VERSION", "0.2.2"), "0.2.2"),
            ('if true; then PLEBIAN_OS_VERSION=0.2.2; fi', None),
            ('OTHER=note; PLEBIAN_OS_VERSION=0.2.2', None),
            ('PLEBIAN_OS_VERSION="unknown"', None),
            (r'PLEBIAN_OS_VERSION="0\.2\.2"', None),
            ('# no release metadata', None),
            ('OTHER_KEY=1', None),
        ]
        # Only a record that assigns the key nowhere reports status 3, the
        # first-selection case; everything malformed or ambiguous stays 2.
        never_assigned = {'# no release metadata', 'OTHER_KEY=1'}
        for line, expected in cases:
            with self.subTest(line=line), tempfile.TemporaryDirectory() as td:
                record = Path(td)
                (record / "session.env").write_text(line + "\n")
                result = subprocess.run(
                    ["bash", "-c", function + '\nrecord="$1"\n'
                     'record_release_value PLEBIAN_OS_VERSION', "bash", td],
                    capture_output=True, text=True)
                if expected is None:
                    self.assertEqual(result.returncode,
                                     3 if line in never_assigned else 2, result.stderr)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), expected)

    def test_standalone_split_selects_and_rolls_back_without_os_tooling(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            system_env = self._machine(base)
            user_env = base / "home/.local/gpu_terminal/pleb/config/session.env"
            user_env.parent.mkdir(parents=True)
            legacy = "\n".join(
                line for line in system_env.read_text().splitlines()
                if "${PLEB_REF+x}" not in line and "${KILIX_REF+x}" not in line
            )
            legacy += (
                "\n# Legacy standalone release pins used plain assignments.\n"
                f"PLEB_REF={dict(INSTALLED_RELEASE_VALUES)['PLEB_REF']}\n"
                f"KILIX_REF={dict(INSTALLED_RELEASE_VALUES)['KILIX_REF']}\n"
            )
            user_env.write_text(legacy)
            user_env.chmod(0o600)
            before = user_env.read_bytes()
            system_env.unlink()
            self._source(
                base,
                self._f120_manifest_text(),
                version="0.2.1",
                release="0.2.1",
                tag="v0.2.1",
                requirements_text=(
                    ROOT / "releases" / "0.2.1.requirements"
                ).read_text(),
            )
            closure = user_env.with_name("closure.env")
            recovery = base / "home/.local/gpu_terminal/pleb/state/release-hop"
            env_extra = {
                "PLEBIAN_OS_SELECTOR_MODE": "standalone",
                "PLEBIAN_OS_CLOSURE_LAYOUT": "split",
                "PLEBIAN_OS_SESSION_ENV": str(user_env),
                "PLEBIAN_OS_CLOSURE_ENV": str(closure),
                "PLEBIAN_OS_RECOVERY_BASE": str(recovery),
                "PLEBIAN_OS_SELECTOR_DST": "",
                "PLEBIAN_OS_UPDATER_DST": "",
            }
            selected = self._run(
                base, "0.2.1", "--offline", env_extra=env_extra)
            self.assertEqual(selected.returncode, 0, selected.stderr)
            self.assertTrue(closure.is_file())
            self.assertEqual(closure.stat().st_mode & 0o777, 0o600)
            self.assertEqual(user_env.stat().st_mode & 0o777, 0o600)
            self.assertIn("did not deploy it", selected.stdout)
            self.assertFalse((base / "root/etc/pleb/session.env").exists())
            self.assertFalse(
                (base / "root/usr/local/bin/plebian-os-select-closure").exists())
            self.assertFalse(
                (base / "root/usr/local/bin/plebian-os-update").exists())
            values = self._values(user_env)
            self.assertEqual(values["PLEBIAN_OS_VERSION"], "0.2.1")
            self.assertEqual(values["PLEB_RESPAWN"], "0")

            rolled_back = self._run(base, "--rollback", env_extra=env_extra)
            self.assertEqual(rolled_back.returncode, 0, rolled_back.stderr)
            self.assertEqual(user_env.read_bytes(), before)
            self.assertFalse(closure.exists())

    # ── a standalone machine that never selected a release ──────────────────
    # pleb on plain Debian has no closure.env and, at most, a user session.env
    # with operator choices. The first selection has no release to record; its
    # rollback must put back exactly that: no closure, the same session bytes.
    UNSELECTED_SESSIONS = {
        "absent": None,
        "operator-only": "# operator choices\nPLEB_RESPAWN=0\nKILIX_DESKTOP_FLAVOR=xp\n",
    }

    def _unselected_standalone(self, base, session_text):
        user_env = base / "home/.local/gpu_terminal/pleb/config/session.env"
        user_env.parent.mkdir(parents=True)
        (base / "root").mkdir()
        if session_text is not None:
            user_env.write_text(session_text)
            user_env.chmod(0o600)
        self._source(
            base, (ROOT / "releases/0.2.2.env").read_text(),
            version="0.2.2", release="0.2.2", tag="v0.2.2",
            requirements_text=(ROOT / "releases/0.2.2.requirements").read_text())
        recovery = base / "home/.local/gpu_terminal/pleb/state/release-hop"
        env_extra = {
            "PLEBIAN_OS_SELECTOR_MODE": "standalone",
            "PLEBIAN_OS_CLOSURE_LAYOUT": "split",
            "PLEBIAN_OS_SESSION_ENV": str(user_env),
            "PLEBIAN_OS_CLOSURE_ENV": str(user_env.with_name("closure.env")),
            "PLEBIAN_OS_RECOVERY_BASE": str(recovery),
            "PLEBIAN_OS_SELECTOR_DST": "",
            "PLEBIAN_OS_UPDATER_DST": "",
        }
        return user_env, recovery, env_extra

    @staticmethod
    def _state(path: Path):
        return path.read_bytes() if path.exists() else None

    def _tag_object(self, base, tag="v0.2.2"):
        return subprocess.run(
            ["git", "-C", str(base / "src"), "rev-parse", f"refs/tags/{tag}"],
            capture_output=True, text=True, check=True).stdout.strip()

    def _select_first(self, base, env_extra, **kwargs):
        return self._run(base, "0.2.2", "--offline", "--source", str(base / "src"),
                         env_extra=env_extra, **kwargs)

    def test_first_standalone_selection_records_an_unselected_machine(self):
        for name, text in self.UNSELECTED_SESSIONS.items():
            with self.subTest(session=name), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                user_env, recovery, env_extra = self._unselected_standalone(base, text)
                closure = user_env.with_name("closure.env")
                selected = self._select_first(base, env_extra)
                self.assertEqual(selected.returncode, 0, selected.stderr)
                self.assertNotIn("status 6", selected.stderr)
                self.assertIn("treating 0.2.2 as a first selection", selected.stderr)
                self.assertEqual(self._values(user_env)["PLEBIAN_OS_VERSION"], "0.2.2")
                self.assertEqual(closure.stat().st_mode & 0o777, 0o600)
                if text is not None:
                    self.assertEqual(self._values(user_env)["KILIX_DESKTOP_FLAVOR"], "xp")
                    self.assertEqual(user_env.read_text(), text)
                records = sorted(recovery.glob("closure-rollback.*"))
                self.assertEqual(len(records), 1)
                record = records[0]
                self.assertEqual((record / "closure.existed").read_text(), "0\n")
                self.assertEqual((record / "session.existed").read_text(),
                                 "0\n" if text is None else "1\n")
                self.assertEqual(
                    (record / "release-metadata.env").read_text(),
                    "# No Plebian-OS release was selected before this record.\n")

    def test_first_standalone_rollback_returns_to_no_closure(self):
        # pleb's --rollback and its restore after a failed stack apply both run
        # the target selector's --rollback with the hop's trusted tag object.
        for name, text in self.UNSELECTED_SESSIONS.items():
            for trusted in (False, True):
                with self.subTest(session=name, trusted_tag=trusted), \
                        tempfile.TemporaryDirectory() as td:
                    base = Path(td)
                    user_env, recovery, env_extra = self._unselected_standalone(base, text)
                    closure = user_env.with_name("closure.env")
                    before = (self._state(user_env), self._state(closure))
                    self.assertEqual(self._select_first(base, env_extra).returncode, 0)
                    rollback_env = dict(env_extra)
                    if trusted:
                        rollback_env["PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA"] = self._tag_object(base)
                    restored = self._run(base, "--rollback", env_extra=rollback_env)
                    self.assertEqual(restored.returncode, 0, restored.stderr)
                    self.assertEqual((self._state(user_env), self._state(closure)), before)
                    record = sorted(recovery.glob("closure-rollback.*"))[0]
                    self.assertTrue((record / "restored").is_file())
                    again = self._run(base, "--rollback", env_extra=env_extra)
                    self.assertNotEqual(again.returncode, 0)
                    self.assertIn("no split closure to roll back to", again.stderr)
                    self.assertEqual((self._state(user_env), self._state(closure)), before)

    def test_failed_first_standalone_apply_restores_no_closure(self):
        for name, text in self.UNSELECTED_SESSIONS.items():
            for boundary in ("backup", "stage", "session", "closure"):
                with self.subTest(session=name, fail_after=boundary), \
                        tempfile.TemporaryDirectory() as td:
                    base = Path(td)
                    user_env, recovery, env_extra = self._unselected_standalone(base, text)
                    closure = user_env.with_name("closure.env")
                    before = (self._state(user_env), self._state(closure))
                    failed = self._select_first(base, env_extra, fail_after=boundary)
                    self.assertNotEqual(failed.returncode, 0)
                    self.assertIn("injected split-closure failure", failed.stderr)
                    self.assertEqual((self._state(user_env), self._state(closure)), before)
                    self.assertEqual(list(recovery.glob("closure-rollback.*")), [])
                    retried = self._select_first(base, env_extra)
                    self.assertEqual(retried.returncode, 0, retried.stderr)

    def test_repeat_standalone_selection_keeps_ordinary_records(self):
        for name, text in self.UNSELECTED_SESSIONS.items():
            with self.subTest(session=name), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                user_env, recovery, env_extra = self._unselected_standalone(base, text)
                closure = user_env.with_name("closure.env")
                unselected = (self._state(user_env), self._state(closure))
                # Select, roll back to unselected, select again.
                self.assertEqual(self._select_first(base, env_extra).returncode, 0)
                first = (self._state(user_env), self._state(closure))
                self.assertEqual(self._run(base, "--rollback", env_extra=env_extra).returncode, 0)
                self.assertEqual((self._state(user_env), self._state(closure)), unselected)
                # No pause between selections: a record's name sorts after
                # every existing record even within one second.
                again = self._select_first(base, env_extra)
                self.assertEqual(again.returncode, 0, again.stderr)
                self.assertEqual((self._state(user_env), self._state(closure)), first)
                # Selecting once more starts from a selected machine: an
                # ordinary record carrying the selected release.
                reselected = self._select_first(base, env_extra)
                self.assertEqual(reselected.returncode, 0, reselected.stderr)
                self.assertIn("closure: 0.2.2 -> 0.2.2 (reselecting the same release",
                              reselected.stdout)
                newest = sorted(recovery.glob("closure-rollback.*"))[-1]
                self.assertEqual((newest / "closure.existed").read_text(), "1\n")
                self.assertEqual((newest / "release-metadata.env").read_text(),
                                 "PLEBIAN_OS_VERSION=0.2.2\nPLEBIAN_OS_RELEASE_MODE=1\n")
                self.assertEqual(self._run(base, "--rollback", env_extra=env_extra).returncode, 0)
                self.assertEqual((self._state(user_env), self._state(closure)), first)
                self.assertEqual(self._run(base, "--rollback", env_extra=env_extra).returncode, 0)
                self.assertEqual((self._state(user_env), self._state(closure)), unselected)

    def test_first_standalone_selection_checks_ancestry_from_unpinned_checkouts(self):
        # No skip: a never-selected machine has no installed PLEB_REF or
        # KILIX_REF pin. Its checkouts' HEADs are what is installed.
        for name, text in self.UNSELECTED_SESSIONS.items():
            for provider in (True, False):
                with self.subTest(session=name, kilix95_checkout=provider), \
                        tempfile.TemporaryDirectory() as td:
                    base = Path(td)
                    sources = base / "home/.local/gpu_terminal/sources"
                    pleb, kilix, kilix95 = (sources / "pleb", sources / "kilix",
                                            sources / "kilix-desktops/kilix-95")
                    user_env = base / "home/.local/gpu_terminal/pleb/config/session.env"
                    user_env.parent.mkdir(parents=True)
                    (base / "root").mkdir()
                    if text is not None:
                        user_env.write_text(text)
                        user_env.chmod(0o600)
                    histories = [self._component_history(repo) for repo in (pleb, kilix, kilix95)]
                    pins = dict(zip(("PLEB_REF", "KILIX_REF", "KILIX95_REF"),
                                    (h[-1] for h in histories)))
                    self._source(base, self._manifest_text(**pins))
                    self._seed_core_public_caches(base, pleb, kilix, kilix95)
                    for repo, history in zip((pleb, kilix, kilix95), histories):
                        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "--detach",
                                        history[0]], check=True)
                    if not provider:
                        shutil.rmtree(kilix95)
                    closure = user_env.with_name("closure.env")
                    env_extra = {
                        "PLEBIAN_OS_SELECTOR_MODE": "standalone",
                        "PLEBIAN_OS_CLOSURE_LAYOUT": "split",
                        "PLEBIAN_OS_SESSION_ENV": str(user_env),
                        "PLEBIAN_OS_CLOSURE_ENV": str(closure),
                        "PLEBIAN_OS_RECOVERY_BASE": str(
                            base / "home/.local/gpu_terminal/pleb/state/release-hop"),
                        "PLEBIAN_OS_SELECTOR_DST": "", "PLEBIAN_OS_UPDATER_DST": "",
                        "PLEBIAN_OS_PLEB_DIR": str(pleb), "PLEBIAN_OS_KILIX_DIR": str(kilix),
                        "PLEBIAN_OS_KILIX95_DIR": str(kilix95),
                    }
                    before = (self._state(user_env), self._state(closure))
                    selected = self._run(base, "0.1.8", "--offline", "--source", str(base / "src"),
                                         check_ancestry=True, env_extra=env_extra)
                    self.assertEqual(selected.returncode, 0, selected.stderr)
                    for label, history in (("Pleb", histories[0]), ("Kilix", histories[1])):
                        self.assertIn(f"{label}: no installed", selected.stdout)
                        self.assertIn(f"component {label}: {history[0][:12]} -> "
                                      f"{history[-1][:12]} (forward", selected.stdout)
                    self.assertEqual(self._values(user_env)["PLEB_REF"], pins["PLEB_REF"])
                    rolled = self._run(base, "--rollback", env_extra=env_extra)
                    self.assertEqual(rolled.returncode, 0, rolled.stderr)
                    self.assertEqual((self._state(user_env), self._state(closure)), before)

    def test_image_machine_without_installed_pins_still_refuses_ancestry(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sources = base / "home/.local/gpu_terminal/sources"
            repos = (sources / "pleb", sources / "kilix", sources / "kilix-desktops/kilix-95")
            histories = [self._component_history(repo) for repo in repos]
            pins = dict(zip(("PLEB_REF", "KILIX_REF", "KILIX95_REF"), (h[-1] for h in histories)))
            os_head = self._source(base, self._manifest_text(**pins))
            self._seed_core_public_caches(base, *repos)
            previous = {**dict(INSTALLED_RELEASE_VALUES), "PLEBIAN_OS_REF": os_head,
                        **dict(zip(pins, (h[0] for h in histories)))}
            del previous["PLEB_REF"]
            session = self._machine(base, release=list(previous.items()))
            before = session.read_bytes()
            refused = self._run(base, "0.1.8", "--offline", check_ancestry=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("installed PLEB_REF must be a full 40-character commit", refused.stderr)
            self.assertEqual(session.read_bytes(), before)

    def test_standalone_records_without_a_clear_release_still_refuse(self):
        # Only "no closure and no release value at all" is a first selection.
        cases = {
            "mode-without-version": ("PLEBIAN_OS_RELEASE_MODE=1\n", None),
            "invalid-version": ("PLEBIAN_OS_VERSION=unknown\n", None),
            "closure-without-version": ("PLEB_RESPAWN=0\n", "PLEB_REF=" + "1" * 40 + "\n"),
        }
        for name, (session_text, closure_text) in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                user_env, recovery, env_extra = self._unselected_standalone(base, session_text)
                closure = user_env.with_name("closure.env")
                if closure_text is not None:
                    closure.write_text(closure_text)
                    closure.chmod(0o600)
                before = (self._state(user_env), self._state(closure))
                refused = self._select_first(base, env_extra)
                self.assertNotEqual(refused.returncode, 0)
                self.assertIn("could not select the split closure (status 6)", refused.stderr)
                self.assertEqual((self._state(user_env), self._state(closure)), before)

    def test_image_machine_without_release_metadata_still_refuses(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            release = [(k, v) for k, v in self._release_values("0.2.2")
                       if k not in ("PLEBIAN_OS_VERSION", "PLEBIAN_OS_RELEASE",
                                    "PLEBIAN_OS_RELEASE_MODE")]
            session = self._machine(base, release=release)
            before = session.read_bytes()
            self._source(
                base, (ROOT / "releases/0.2.2.env").read_text(),
                version="0.2.2", release="0.2.2", tag="v0.2.2",
                requirements_text=(ROOT / "releases/0.2.2.requirements").read_text())
            refused = self._run(base, "0.2.2", "--offline")
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("could not select the split closure (status 6)", refused.stderr)
            self.assertEqual(session.read_bytes(), before)
            self.assertFalse(session.with_name("closure.env").exists())

    def test_selection_adds_a_pin_the_installed_release_never_had(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            without_voice = [(k, v) for k, v in INSTALLED_RELEASE_VALUES
                             if not k.startswith("KILIX_VOICE_")]
            env = self._machine(base, release=without_voice)
            self._source(base)
            result = self._run(base, "0.1.8", "--offline")
            self.assertEqual(result.returncode, 0, result.stderr)
            after = self._values(env)
            self.assertEqual(after["KILIX_VOICE_REF"],
                             "eda9ca90eed677fa4fca383e7b8ad2fc85e54b0e")
            # Seven are the release's new pins; two are the selection's
            # recorded tag and tag object.
            self.assertIn("closure adds 9 key(s) this release introduces", result.stdout)

    # ── operator-controlled keys survive ────────────────────────────────────
    def test_operator_controlled_choices_survive_selection(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            before_lines = env.read_text().splitlines()
            self._source(base)
            self.assertEqual(self._run(base, "0.1.8", "--offline").returncode, 0)
            after = self._values(env)
            for name, value in OPERATOR_VALUES:
                self.assertEqual(after[name], value, name)
            after_lines = env.read_text().splitlines()
            release_names = {name for name, _ in INSTALLED_RELEASE_VALUES}
            release_names |= {
                "PLEBIAN_OS_RELEASE",
                "PLEBIAN_OS_INSTALL_UV",
                "PLEBIAN_OS_UV_VERSION",
                "PLEBIAN_OS_UV_INSTALLER_SHA256",
                "PLEBIAN_OS_RELEASE_TAG",
                "PLEBIAN_OS_RELEASE_TAG_OBJECT",
            }
            kept_before = [line for line in before_lines
                           if not any(f"${{{n}+x}}" in line for n in release_names)]
            kept_after = [line for line in after_lines
                          if not any(f"${{{n}+x}}" in line for n in release_names)
                          and not line.startswith(
                              "# Added by plebian-os-select-closure")]
            self.assertEqual(kept_before, kept_after)
            self.assertIn("PLEB_RESPAWN=0   # operator note, deliberately unguarded",
                          after_lines)

    def test_image_policy_defaults_are_validated_but_never_selected(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            policy = base / "root" / "etc" / "default" / "plebian-os"
            policy.parent.mkdir(parents=True)
            policy.write_text('PLEBIAN_OS_DESKTOP="0"\nPLEBIAN_OS_KIOSK="1"\n')
            before = policy.read_bytes()
            self._source(base)
            selected = self._run(base, "0.1.8", "--offline")
            self.assertEqual(selected.returncode, 0, selected.stderr)
            self.assertEqual(policy.read_bytes(), before)
            values = self._values(env)
            self.assertNotIn("PLEBIAN_OS_DESKTOP", values)
            self.assertNotIn("PLEBIAN_OS_KIOSK", values)
            self.assertIn(
                "PLEBIAN_OS_DESKTOP: validated image default only",
                selected.stdout,
            )
            self.assertIn(
                "PLEBIAN_OS_KIOSK: validated image default only",
                selected.stdout,
            )

            base = Path(td) / "invalid"
            self._machine(base)
            self._source(base, self._manifest_text(PLEBIAN_OS_DESKTOP="2"))
            self._refuses(base, "PLEBIAN_OS_DESKTOP must be 0 or 1")

    # ── an incomplete or malformed closure is refused, by name ──────────────
    def _refuses(self, base: Path, expected: str, *args, target="0.1.8"):
        env = base / "root" / "etc" / "pleb" / "session.env"
        before = env.read_bytes()
        result = self._run(base, target, "--offline", *args)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(expected, result.stderr)
        self.assertEqual(env.read_bytes(), before)
        self.assertEqual(self._recovery_records(base), [])
        return result

    def test_incomplete_closure_is_refused_and_names_the_missing_pins(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(drop=("KILIX_REF", "PLEB_REF")))
            result = self._refuses(base, "incomplete closure")
            self.assertIn("KILIX_REF", result.stderr)
            self.assertIn("PLEB_REF", result.stderr)

    def test_explicit_live_policy_clears_the_installed_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            self._source(base, self._manifest_text(PLEBIAN_OS_APT_SNAPSHOT=""))
            result = self._run(base, "0.1.8", "--offline")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self._values(env)["PLEBIAN_OS_APT_SNAPSHOT"], "")

    def test_omitted_apt_policy_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(drop=("PLEBIAN_OS_APT_SNAPSHOT",)))
            self._refuses(base, "PLEBIAN_OS_APT_SNAPSHOT must be declared")

    def test_undeclared_branch_key_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(drop=("KILIX95_BRANCH",)))
            self._refuses(base, "these must be declared, even empty: KILIX95_BRANCH")

    def test_branch_pin_in_a_release_closure_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(PLEB_BRANCH="main"))
            self._refuses(base, "PLEB_BRANCH must be empty in a release closure")

    def test_malformed_manifest_line_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(raw_lines=("KILIX_REF_WITHOUT_VALUE",)))
            self._refuses(base, "invalid manifest line: KILIX_REF_WITHOUT_VALUE")

    def test_duplicate_manifest_key_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(raw_lines=("KILIX_REF=" + "c" * 40,)))
            self._refuses(base, "duplicate manifest key: KILIX_REF")

    def test_placeholder_pin_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(KILIX95_REF="REPLACE_ME"))
            self._refuses(base, "KILIX95_REF is still REPLACE_ME")

    def test_short_commit_pin_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(KILIX_REF="df641fb"))
            self._refuses(base, "KILIX_REF must be a full 40-character lowercase commit SHA")

    def test_half_pinned_optional_closure_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(drop=("KILIX_VOICE_MODEL_SHA256",)))
            self._refuses(base, "PLEBIAN_OS_INSTALL_VOICE_MODEL=1 needs pinned values for")

    def test_enabled_uv_requires_exact_version_and_checksum_pins(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(
                base,
                self._manifest_text(PLEBIAN_OS_INSTALL_UV="1"),
            )
            self._refuses(
                base,
                "PLEBIAN_OS_INSTALL_UV=1 needs a pinned PLEBIAN_OS_UV_VERSION",
            )

    def test_release_requirements_cannot_be_overridden_by_the_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(
                base,
                requirements_text="PLEBIAN_OS_INSTALL_UV=1\n",
            )
            self._refuses(
                base,
                "release requirements demand PLEBIAN_OS_INSTALL_UV=1",
            )

    # ── a closure whose version disagrees with the artifact is refused ──────
    def test_manifest_version_disagreeing_with_the_release_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(PLEBIAN_OS_VERSION="0.1.7"))
            self._refuses(base, "PLEBIAN_OS_VERSION is '0.1.7', not 0.1.8")

    def test_manifest_version_disagreeing_with_the_artifact_VERSION_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, version="0.1.9")
            self._refuses(base, "the release commit's VERSION reads '0.1.9', not 0.1.8")

    def test_release_mode_must_be_declared(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(PLEBIAN_OS_RELEASE_MODE="0"))
            self._refuses(base, "PLEBIAN_OS_RELEASE_MODE must be 1")

    def test_os_ref_naming_another_release_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, self._manifest_text(PLEBIAN_OS_REF="v0.1.7"))
            self._refuses(base, "PLEBIAN_OS_REF must be v0.1.8")

    def test_missing_release_tag_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base, tag="v0.1.7", release="0.1.8")
            result = self._refuses(base, "release tag v0.1.8 is not in")

    def test_offline_tag_requires_an_exact_trusted_tag_object(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            before = env.read_bytes()
            self._source(base)
            missing = self._run(
                base, "0.1.8", "--offline", trust_tag=False)
            self.assertNotEqual(missing.returncode, 0, missing.stdout)
            self.assertIn(
                "--offline requires PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA",
                missing.stderr,
            )
            wrong = self._run(
                base, "0.1.8", "--offline", trust_tag=False,
                env_extra={"PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA": "f" * 40},
            )
            self.assertNotEqual(wrong.returncode, 0, wrong.stdout)
            self.assertIn("not trusted object", wrong.stderr)
            self.assertEqual(env.read_bytes(), before)

    # ── a hand edit outside the managed form is refused ─────────────────────
    def test_unmanaged_release_key_edit_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base, extra_lines=("KILIX_REF=" + "d" * 40,))
            self._source(base)
            self._refuses(base, "sets the release-controlled key KILIX_REF outside the managed form")

    # ── a failure mid-write leaves the previous closure intact ──────────────
    def _fails_intact(self, base: Path, boundary: str, expected: str):
        env = base / "root" / "etc" / "pleb" / "session.env"
        selector = (base / "root" / "usr" / "local" / "bin" /
                    "plebian-os-select-closure")
        updater = base / "root" / "usr" / "local" / "bin" / "plebian-os-update"
        before = env.read_bytes()
        selector_before = selector.read_bytes() if selector.exists() else None
        updater_before = updater.read_bytes() if updater.exists() else None
        result = self._run(base, "0.1.8", "--offline", fail_after=boundary)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(expected, result.stderr)
        self.assertEqual(env.read_bytes(), before)
        if selector_before is None:
            self.assertFalse(selector.exists())
        else:
            self.assertEqual(selector.read_bytes(), selector_before)
        if updater_before is None:
            self.assertFalse(updater.exists())
        else:
            self.assertEqual(updater.read_bytes(), updater_before)
        leftovers = list((base / "root" / "etc" / "pleb").glob(".session.env.*"))
        self.assertEqual(leftovers, [])
        return result

    def test_failure_before_the_write_leaves_the_previous_closure_intact(self):
        for boundary in ("render", "verify"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                self._machine(base)
                self._source(base)
                self._fails_intact(
                    base, boundary,
                    f"injected closure selection failure after {boundary}")
                self.assertEqual(self._recovery_records(base), [])

    def test_failure_mid_write_leaves_the_previous_closure_intact(self):
        for boundary in ("backup", "stage", "selector", "updater"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                self._machine(base)
                self._source(base)
                self._fails_intact(
                    base, boundary,
                    "the previous closure is still selected")
                # A half-finished selection leaves no recovery record claiming
                # to hold a closure that was never replaced.
                self.assertEqual(self._recovery_records(base), [])

    def test_a_failed_selection_can_be_retried_and_then_succeeds(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            self._source(base)
            self._fails_intact(base, "stage", "the previous closure is still selected")
            self.assertEqual(self._run(base, "0.1.8", "--offline").returncode, 0)
            self.assertEqual(self._values(env)["PLEBIAN_OS_VERSION"], "0.1.8")

    # ── a backwards selection is announced ──────────────────────────────────
    def test_backwards_selection_is_announced_as_a_downgrade(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            newer = [(k, "0.1.9" if k in ("PLEBIAN_OS_VERSION", "PLEBIAN_OS_RELEASE") else v)
                     for k, v in INSTALLED_RELEASE_VALUES]
            self._machine(base, release=newer)
            self._source(base)
            result = self._run(base, "0.1.8", "--offline")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("closure: 0.1.9 -> 0.1.8 (DOWNGRADE, pinned by releases/0.1.8.env@",
                          result.stderr)
            self.assertIn("the installed release was newer", result.stderr)

    def test_forward_selection_is_not_announced_as_a_downgrade(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base)
            result = self._run(base, "0.1.8", "--offline")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("DOWNGRADE", result.stderr)
            self.assertIn("closure: 0.1.7 -> 0.1.8 (pinned by releases/0.1.8.env@",
                          result.stdout)

    def test_component_downgrade_is_detected_while_release_moves_forward(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sources = base / "home" / ".local" / "gpu_terminal" / "sources"
            pleb_dir = sources / "pleb"
            kilix_dir = sources / "kilix"
            kilix95_dir = sources / "kilix-desktops" / "kilix-95"
            pleb = self._component_history(pleb_dir)
            kilix = self._component_history(kilix_dir)
            kilix95 = self._component_history(kilix95_dir, count=1)
            manifest = self._manifest_text(
                PLEB_REF=pleb[0],
                KILIX_REF=kilix[1],
                KILIX95_REF=kilix95[0],
            )
            os_commit = self._source(base, manifest)
            self._seed_core_public_caches(
                base, pleb_dir, kilix_dir, kilix95_dir)
            installed = dict(INSTALLED_RELEASE_VALUES)
            installed.update({
                "PLEBIAN_OS_REF": os_commit,
                "PLEB_REF": pleb[1],
                "KILIX_REF": kilix[0],
                "KILIX95_REF": kilix95[0],
            })
            self._machine(base, release=list(installed.items()))

            result = self._run(
                base, "0.1.8", "--offline", "--dry-run", check_ancestry=True)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("closure: 0.1.7 -> 0.1.8", result.stdout)
            self.assertIn(
                f"component Pleb: {pleb[1][:12]} -> {pleb[0][:12]} (DOWNGRADE;",
                result.stderr,
            )
            self.assertIn(
                f"component Kilix: {kilix[0][:12]} -> {kilix[1][:12]} (forward;",
                result.stdout,
            )

    def test_component_sideways_move_is_announced_as_diverged(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sources = base / "home/.local/gpu_terminal/sources"
            pleb_dir = sources / "pleb"
            pleb = self._component_history(pleb_dir)
            git = ["git", "-C", str(pleb_dir)]
            subprocess.run(git + ["checkout", "-q", "HEAD^"], check=True)
            (pleb_dir / "sideways").write_text("sideways\n")
            subprocess.run(git + ["add", "sideways"], check=True)
            subprocess.run(git + ["commit", "-qm", "sideways"], check=True)
            sideways = subprocess.run(
                git + ["rev-parse", "HEAD"], capture_output=True,
                text=True, check=True,
            ).stdout.strip()
            kilix_dir = sources / "kilix"
            kilix95_dir = sources / "kilix-desktops/kilix-95"
            kilix = self._component_history(kilix_dir, count=1)
            kilix95 = self._component_history(kilix95_dir, count=1)
            manifest = self._manifest_text(
                PLEB_REF=sideways,
                KILIX_REF=kilix[0],
                KILIX95_REF=kilix95[0],
            )
            os_commit = self._source(base, manifest)
            self._seed_core_public_caches(
                base, pleb_dir, kilix_dir, kilix95_dir)
            installed = dict(INSTALLED_RELEASE_VALUES)
            installed.update({
                "PLEBIAN_OS_REF": os_commit,
                "PLEB_REF": pleb[1],
                "KILIX_REF": kilix[0],
                "KILIX95_REF": kilix95[0],
            })
            self._machine(base, release=list(installed.items()))

            result = self._run(
                base, "0.1.8", "--offline", "--dry-run", check_ancestry=True)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                f"component Pleb: {pleb[1][:12]} -> {sideways[:12]} "
                "(DIVERGED, neither commit is an ancestor;",
                result.stderr,
            )

    def test_component_commit_must_be_reachable_from_an_advertised_ref(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sources = base / "home/.local/gpu_terminal/sources"
            pleb_dir = sources / "pleb"
            kilix_dir = sources / "kilix"
            kilix95_dir = sources / "kilix-desktops/kilix-95"
            pleb = self._component_history(pleb_dir)
            kilix = self._component_history(kilix_dir, count=1)
            kilix95 = self._component_history(kilix95_dir, count=1)
            manifest = self._manifest_text(
                PLEB_REF=pleb[1],
                KILIX_REF=kilix[0],
                KILIX95_REF=kilix95[0],
            )
            os_commit = self._source(base, manifest)
            values = dict(INSTALLED_RELEASE_VALUES)
            self._seed_public_cache(
                base, "plebian-os", values["PLEBIAN_OS_REPO"], base / "src")
            # The target object exists in the checkout, but only its parent is
            # represented by the cached public-ref snapshot.
            self._seed_public_cache(
                base, "pleb", values["PLEB_REPO"], pleb_dir,
                public_commit=pleb[0],
            )
            self._seed_public_cache(
                base, "kilix", values["KILIX_REPO"], kilix_dir)
            self._seed_public_cache(
                base, "kilix-95", values["KILIX95_REPO"], kilix95_dir)
            installed = dict(INSTALLED_RELEASE_VALUES)
            installed.update({
                "PLEBIAN_OS_REF": os_commit,
                "PLEB_REF": pleb[0],
                "KILIX_REF": kilix[0],
                "KILIX95_REF": kilix95[0],
            })
            env = self._machine(base, release=list(installed.items()))
            before = env.read_bytes()

            result = self._run(
                base, "0.1.8", "--offline", check_ancestry=True)

            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn(
                f"Pleb target PLEB_REF={pleb[1]} is not reachable from any "
                "advertised head or tag",
                result.stderr,
            )
            self.assertEqual(env.read_bytes(), before)

    def test_offline_selection_refuses_missing_component_target(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sources = base / "home" / ".local" / "gpu_terminal" / "sources"
            pleb_dir = sources / "pleb"
            kilix_dir = sources / "kilix"
            kilix95_dir = sources / "kilix-desktops" / "kilix-95"
            pleb = self._component_history(pleb_dir, count=1)
            kilix = self._component_history(kilix_dir, count=1)
            kilix95 = self._component_history(kilix95_dir, count=1)
            missing = "f" * 40
            manifest = self._manifest_text(
                PLEB_REF=missing,
                KILIX_REF=kilix[0],
                KILIX95_REF=kilix95[0],
            )
            os_commit = self._source(base, manifest)
            self._seed_core_public_caches(
                base, pleb_dir, kilix_dir, kilix95_dir)
            installed = dict(INSTALLED_RELEASE_VALUES)
            installed.update({
                "PLEBIAN_OS_REF": os_commit,
                "PLEB_REF": pleb[0],
                "KILIX_REF": kilix[0],
                "KILIX95_REF": kilix95[0],
            })
            env = self._machine(base, release=list(installed.items()))
            before = env.read_bytes()

            result = self._run(
                base, "0.1.8", "--offline", check_ancestry=True)

            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn(
                f"Pleb target PLEB_REF={missing} is not reachable from any "
                "advertised head or tag",
                result.stderr,
            )
            self.assertEqual(env.read_bytes(), before)
            self.assertEqual(self._recovery_records(base), [])

    # ── the previous closure is recoverable ─────────────────────────────────
    def test_rollback_restores_the_previous_closure_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            selector = (base / "root" / "usr" / "local" / "bin" /
                        "plebian-os-select-closure")
            updater = base / "root" / "usr" / "local" / "bin" / "plebian-os-update"
            before = env.read_bytes()
            self._source(base)
            self.assertFalse(selector.exists())
            self.assertEqual(self._run(base, "0.1.8", "--offline").returncode, 0)
            self.assertNotEqual(env.read_bytes(), before)
            self.assertEqual(selector.read_bytes(), SELECT.read_bytes())
            self.assertEqual(selector.stat().st_mode & 0o777, 0o755)
            self.assertEqual(updater.read_bytes(), UPDATE.read_bytes())
            self.assertEqual(updater.stat().st_mode & 0o777, 0o755)
            records = self._recovery_records(base)
            self.assertEqual(len(records), 1)
            self.assertEqual((records[0] / "session.env").read_bytes(), before)
            self.assertEqual((records[0] / "selector.existed").read_text(), "0\n")
            self.assertEqual((records[0] / "updater.existed").read_text(), "0\n")
            self.assertIn("to=0.1.8", (records[0] / "meta").read_text())
            result = self._run(base, "--rollback")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(env.read_bytes(), before)
            self.assertFalse(selector.exists())
            self.assertFalse(updater.exists())
            # One record is one undo; a second call has nothing left to restore.
            again = self._run(base, "--rollback")
            self.assertNotEqual(again.returncode, 0)
            self.assertIn("no closure to roll back to", again.stderr)

    def _two_selections_in_one_second(self, base: Path, epoch: int):
        """Select 0.1.8 twice in one UTC second on a legacy-layout machine.

        Returns the clock PATH, the session bytes before and after the first
        selection, and the two records, told apart by their contents: the
        first selection found no installed selector, the second found one.
        """
        env = self._machine(base)
        original = env.read_bytes()
        self._source(base)
        clock = self._frozen_clock(base, epoch)
        first = self._run(base, "0.1.8", "--offline", env_extra=clock)
        self.assertEqual(first.returncode, 0, first.stderr)
        selected = env.read_bytes()
        self.assertNotEqual(selected, original)
        second = self._run(base, "0.1.8", "--offline", env_extra=clock)
        self.assertEqual(second.returncode, 0, second.stderr)
        by_selector = {(r / "selector.existed").read_text(): r
                       for r in self._recovery_records(base)}
        self.assertEqual(sorted(by_selector), ["0\n", "1\n"])
        at = "at=" + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch)) + "\n"
        for record in by_selector.values():
            self.assertIn(at, (record / "meta").read_text())
        return clock, original, selected, by_selector["0\n"], by_selector["1\n"]

    def test_legacy_selections_in_one_second_roll_back_newest_first(self):
        """Two selections in one UTC second: --rollback undoes the second one.

        A record was named by the UTC second plus a random suffix, and
        rollback took the last name in glob order, so a same-second pair was
        ordered by the random part and could restore the earlier selection's
        record. A record now takes a second past every existing record. The
        frozen clock and the descending suffixes make the old order fail
        every time rather than about half the time.
        """
        epoch = int(time.time())
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            clock, original, selected, older, newer = \
                self._two_selections_in_one_second(base, epoch)
            env = base / "root/etc/pleb/session.env"
            selector = base / "root/usr/local/bin/plebian-os-select-closure"
            self.assertTrue(older.name.startswith(
                f"closure-rollback.{self._record_stamp(epoch)}."), older.name)
            self.assertTrue(newer.name.startswith(
                f"closure-rollback.{self._record_stamp(epoch + 1)}."), newer.name)
            # Every earlier selector restores the last name in glob order.
            recovery = base / "root/var/lib/plebian-os"
            for locale in ("C", "en_US.UTF-8"):
                self.assertEqual(self._last_in_glob_order(recovery, locale), newer.name)

            back = self._run(base, "--rollback", env_extra=clock)
            self.assertEqual(back.returncode, 0, back.stderr)
            self.assertIn(newer.name, back.stdout + back.stderr)
            self.assertEqual(env.read_bytes(), selected)
            self.assertEqual(selector.read_bytes(), SELECT.read_bytes())
            self.assertTrue((newer / "restored").exists())
            self.assertFalse((older / "restored").exists())
            back = self._run(base, "--rollback", env_extra=clock)
            self.assertEqual(back.returncode, 0, back.stderr)
            self.assertEqual(env.read_bytes(), original)
            self.assertFalse(selector.exists())
            self.assertTrue((older / "restored").exists())

    def test_recovery_record_stamps_order_records_by_selection(self):
        """The stamp rule and the reader, apart from any selection."""
        source = SELECT.read_text()
        functions = "\n".join(
            re.search(rf"^{name}\(\) \{{.*?^\}}", source, re.S | re.M)[0]
            for name in ("recovery_record_seconds", "recovery_record_stamp",
                         "newest_recovery_record"))
        epoch = 1798761599          # 2026-12-31T23:59:59Z
        stamp = self._record_stamp

        def run(command, base, *args):
            ran = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", functions + "\n" + command,
                 "bash", str(base), *args],
                env={**os.environ, **clock}, text=True, capture_output=True)
            return ran.returncode, ran.stdout.strip()

        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "recovery"
            base.mkdir()
            clock = self._frozen_clock(Path(td), epoch)
            new = 'recovery_record_stamp "$1"'
            self.assertEqual(run(new, base), (0, stamp(epoch)))
            (base / f"closure-rollback.{stamp(epoch - 5)}.zzzzzz").mkdir()
            (base / "closure-rollback.copy").mkdir()
            self.assertEqual(run(new, base), (0, stamp(epoch)))
            (base / f"closure-rollback.{stamp(epoch)}.AAAAAA").mkdir()
            # The next second, across a year boundary.
            self.assertEqual(run(new, base), (0, "20270101T000000Z"))
            (base / f"closure-rollback.{stamp(epoch + 3600)}.000000").mkdir()
            self.assertEqual(run(new, base), (0, stamp(epoch + 3601)))

            newest = 'newest_recovery_record "${@:2}"'
            names = [f"closure-rollback.{stamp(epoch + 1)}.zzzzzz",
                     f"closure-rollback.{stamp(epoch + 2)}.000000",
                     f"closure-rollback.{stamp(epoch)}.zzzzzz"]
            paths = [str(base / name) for name in names]
            self.assertEqual(run(newest, base, *paths), (0, paths[1]))
            # A shared second below the newest does not matter.
            tied_below = paths + [str(base / f"closure-rollback.{stamp(epoch + 1)}.AAAAAA")]
            self.assertEqual(run(newest, base, *tied_below), (0, paths[1]))
            tied_top = paths + [str(base / f"closure-rollback.{stamp(epoch + 2)}.AAAAAA")]
            self.assertEqual(run(newest, base, *tied_top)[0], 12)
            self.assertEqual(run(newest, base, *paths, str(base / "closure-rollback.copy"))[0], 12)
            self.assertEqual(run(newest, base, *paths,
                                 str(base / "closure-rollback.2026111T000000Z.x"))[0], 12)

    def test_rollback_refuses_records_it_cannot_order(self):
        """Nothing in these names says which selection came last: refuse.

        Two unrestored records from one second are what an earlier selector
        left when two selections shared it. A record with no second in its
        name was not written by any selector. Rollback restores nothing and
        marks nothing, and the selected closure stays installed.
        """
        epoch = int(time.time())
        for name in (f"closure-rollback.{self._record_stamp(epoch)}.000000",
                     "closure-rollback.copy"):
            with self.subTest(newer=name), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                clock, _, _, older, newer = \
                    self._two_selections_in_one_second(base, epoch)
                newer = newer.rename(newer.with_name(name))
                env = base / "root/etc/pleb/session.env"
                selector = base / "root/usr/local/bin/plebian-os-select-closure"
                installed = (env.read_bytes(), selector.read_bytes())
                refused = self._run(base, "--rollback", env_extra=clock)
                self.assertNotEqual(refused.returncode, 0)
                self.assertIn("cannot tell which recovery record is newest",
                              refused.stderr)
                self.assertEqual((env.read_bytes(), selector.read_bytes()), installed)
                self.assertFalse((newer / "restored").exists())
                self.assertFalse((older / "restored").exists())

    # ── a rollback after an interrupted selection ──────────────────────────
    @staticmethod
    def _pending(base: Path) -> Path:
        return (base / "home" / ".local" / "gpu_terminal" / "pleb" / "state" /
                "selection-pending")

    def _rollback_for_pending_tag(self, base: Path, tag_line: str):
        tag = tag_line.split("=", 1)[1]
        extra = {} if tag == "-" else {"PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA": tag}
        return self._run(base, "--rollback", env_extra=extra)

    def test_rollback_after_an_interrupted_selection_restores_nothing(self):
        """The observed hazard: Ctrl-C while selecting, then a rollback, must not
        restore the record an EARLIER hop wrote."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            original = env.read_bytes()
            self._source(base)
            self.assertEqual(self._run(base, "0.1.8", "--offline").returncode, 0)
            selected = env.read_bytes()
            self.assertNotEqual(selected, original)
            self.assertFalse(self._pending(base).exists())
            interrupted = self._run(base, "0.1.8", "--offline",
                                    fail_after="interrupt:render")
            self.assertEqual(interrupted.returncode, 130, interrupted.stderr)
            self.assertEqual(env.read_bytes(), selected)
            facts = self._pending(base).read_text().splitlines()
            self.assertEqual(facts[0], "format=1")
            self.assertEqual(len(self._recovery_records(base)), 1)
            result = self._rollback_for_pending_tag(base, facts[1])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("nothing was restored", result.stderr + result.stdout)
            self.assertEqual(env.read_bytes(), selected)
            records = self._recovery_records(base)
            self.assertEqual(len(records), 1)
            self.assertFalse((records[0] / "restored").exists())
            self.assertFalse(self._pending(base).exists())
            # The marker is spent: a deliberate rollback now undoes the first hop.
            deliberate = self._rollback_for_pending_tag(base, facts[1])
            self.assertEqual(deliberate.returncode, 0, deliberate.stderr)
            self.assertEqual(env.read_bytes(), original)

    # ── a rollback lands after the running update's own rollback ───────────
    def _select_with_running_update(self, base: Path):
        """A completed selection, and an updater that owns a stack transaction
        and, once released, rolls back from its post-selection snapshot of
        session.env, as an interrupted update does."""
        env = self._machine(base)
        original = env.read_bytes()
        self._source(base)
        self.assertEqual(self._run(base, "0.1.8", "--offline").returncode, 0)
        selected = env.read_bytes()
        self.assertNotEqual(selected, original)
        snapshot = base / "updater-snapshot"
        snapshot.write_bytes(selected)
        fifo = base / "release-updater"
        os.mkfifo(fifo)
        state = base / "home/.local/gpu_terminal/pleb/state/stack-rollback.Live01"
        state.mkdir(parents=True, mode=0o700)
        updater = subprocess.Popen(
            ["bash", "-c",
             'read -r _ <"$1"; cat -- "$2" >"$3"; rm -rf -- "$4"', "updater",
             str(fifo), str(snapshot), str(env), str(state)])
        self.addCleanup(updater.wait)
        self.addCleanup(updater.kill)
        ticks = Path(f"/proc/{updater.pid}/stat").read_text().rsplit(") ", 1)[1].split()[19]
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        (state / "owner").write_text(f"pid={updater.pid}\nstart={ticks}\nboot={boot}\n")
        return env, original, selected, updater, fifo

    def _release(self, updater, fifo):
        with open(fifo, "w") as stream:
            stream.write("go\n")
        updater.wait(timeout=30)

    def test_rollback_waits_for_a_running_update_so_its_restore_lands_last(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env, original, selected, updater, fifo = self._select_with_running_update(base)
            rollback = self._run(base, "--rollback", popen=True)
            self.addCleanup(rollback.wait)
            self.addCleanup(rollback.kill)
            seen = ""
            while "waiting up to" not in seen:
                line = rollback.stderr.readline()
                self.assertTrue(line, "the selector ended instead of waiting: " + seen)
                seen += line
            self.assertIn("stack-rollback.Live01", seen)
            self.assertEqual(env.read_bytes(), selected, "nothing is restored while it runs")
            self.assertIsNone(rollback.poll())
            self.assertFalse(any((r / "restored").exists() for r in self._recovery_records(base)))
            self._release(updater, fifo)          # its rollback writes the snapshot back
            self.assertEqual(env.read_bytes(), selected)
            out, err = rollback.communicate(timeout=30)
            self.assertEqual(rollback.returncode, 0, err)
            self.assertIn("finished", out)
            self.assertEqual(env.read_bytes(), original, "the selector's restore lands last")
            self.assertTrue(all((r / "restored").exists() for r in self._recovery_records(base)))

    def test_a_rollback_that_outwaits_the_update_changes_nothing_and_can_be_repeated(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env, original, selected, updater, fifo = self._select_with_running_update(base)
            refused = self._run(base, "--rollback", env_extra={
                "PLEBIAN_OS_SELECT_UPDATE_WAIT_SECONDS": "1"})
            self.assertEqual(refused.returncode, 13, refused.stderr)
            self.assertIn("still running after 1s", refused.stderr)
            self.assertIn("run 'pleb update --rollback'", refused.stderr)
            self.assertEqual(env.read_bytes(), selected)
            records = self._recovery_records(base)
            self.assertEqual(len(records), 1)
            self.assertFalse((records[0] / "restored").exists(), "the record stays restorable")
            self._release(updater, fifo)
            again = self._run(base, "--rollback")
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertEqual(env.read_bytes(), original)

    def test_a_rollback_on_a_hung_up_terminal_still_restores_and_exits_zero(self):
        """Closing the terminal makes every message write fail with EIO. A
        message that cannot be written must not abort the rollback, before it
        restores (the wait's first warning) or after (its last line)."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            original = env.read_bytes()
            self._source(base)
            self.assertEqual(self._run(base, "0.1.8", "--offline").returncode, 0)
            self.assertNotEqual(env.read_bytes(), original)
            rollback = self._run(base, "--rollback", dead_tty=True)
            self.addCleanup(rollback.kill)
            self.assertEqual(rollback.wait(timeout=60), 0)
            self.assertEqual(env.read_bytes(), original)
            self.assertTrue(all((r / "restored").exists() for r in self._recovery_records(base)))
            again = self._run(base, "--rollback")
            self.assertIn("no closure to roll back to", again.stderr)

    def test_a_hung_up_terminal_does_not_end_the_wait_for_a_running_update(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env, original, selected, updater, fifo = self._select_with_running_update(base)
            rollback = self._run(base, "--rollback", dead_tty=True)
            self.addCleanup(rollback.kill)
            # The wait loop is a child `sleep`; a selector that died at its first
            # (unwritable) warning never gets there.
            for _ in range(400):
                if rollback.poll() is not None or subprocess.run(
                        ["pgrep", "-P", str(rollback.pid), "sleep"],
                        capture_output=True).returncode == 0:
                    break
                time.sleep(0.05)
            self.assertIsNone(rollback.poll(), "the selector ended instead of waiting")
            self.assertEqual(env.read_bytes(), selected)
            self._release(updater, fifo)
            self.assertEqual(rollback.wait(timeout=60), 0)
            self.assertEqual(env.read_bytes(), original, "the selector's restore lands last")
            self.assertTrue(all((r / "restored").exists() for r in self._recovery_records(base)))

    def test_a_rollback_run_by_the_update_itself_does_not_wait_for_it(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env, original, _, updater, fifo = self._select_with_running_update(base)
            go = base / "go"
            wrapper = self._run(
                base, popen=True,
                command=["bash", "-c",
                         'while [ ! -e "$1" ]; do sleep 0.05; done; "$2" --rollback',
                         "wrapper", str(go), str(SELECT)])
            self.addCleanup(wrapper.wait)
            self.addCleanup(wrapper.kill)
            owner = base / "home/.local/gpu_terminal/pleb/state/stack-rollback.Live01/owner"
            ticks = Path(f"/proc/{wrapper.pid}/stat").read_text().rsplit(") ", 1)[1].split()[19]
            boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            owner.write_text(f"pid={wrapper.pid}\nstart={ticks}\nboot={boot}\n")
            go.write_text("")
            out, err = wrapper.communicate(timeout=30)
            self.assertEqual(wrapper.returncode, 0, err)
            self.assertNotIn("waiting", err)
            self.assertEqual(env.read_bytes(), original)
            self._release(updater, fifo)

    def test_pending_marker_of_a_selection_that_did_replace_is_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            original = env.read_bytes()
            self._source(base)
            interrupted = self._run(base, "0.1.8", "--offline",
                                    fail_after="interrupt:render")
            self.assertEqual(interrupted.returncode, 130, interrupted.stderr)
            marker = self._pending(base).read_text()
            # The same selection, completed; then its marker reappears, as it
            # would if the selector died between the write and its last line.
            self.assertEqual(self._run(base, "0.1.8", "--offline").returncode, 0)
            self.assertNotEqual(env.read_bytes(), original)
            self._pending(base).write_text(marker)
            result = self._rollback_for_pending_tag(base, marker.splitlines()[1])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(env.read_bytes(), original)
            self.assertFalse(self._pending(base).exists())

    def test_pending_marker_of_another_tag_is_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            original = env.read_bytes()
            self._source(base)
            self.assertEqual(self._run(base, "0.1.8", "--offline").returncode, 0)
            interrupted = self._run(base, "0.1.8", "--offline",
                                    fail_after="interrupt:render")
            self.assertEqual(interrupted.returncode, 130, interrupted.stderr)
            result = self._run(base, "--rollback", env_extra={
                "PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA": "1" * 40})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(env.read_bytes(), original)
            self.assertFalse(self._pending(base).exists())

    def test_only_a_signalled_selection_leaves_a_pending_marker(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            self._source(base)
            dry = self._run(base, "0.1.8", "--offline", "--dry-run")
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertFalse(self._pending(base).exists())
            failed = self._run(base, "0.1.8", "--offline", fail_after="render")
            self.assertNotEqual(failed.returncode, 0)
            self.assertFalse(self._pending(base).exists())
            self.assertEqual(self._run(base, "0.1.8", "--offline").returncode, 0)
            self.assertFalse(self._pending(base).exists())

    def test_selection_replaces_and_rollback_restores_older_tools(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            selector = (base / "root" / "usr" / "local" / "bin" /
                        "plebian-os-select-closure")
            updater = base / "root" / "usr" / "local" / "bin" / "plebian-os-update"
            old_selector = b"#!/usr/bin/env bash\nprintf 'legacy selector\\n'\n"
            old_updater = b"#!/usr/bin/env bash\nprintf 'legacy updater\\n'\n"
            selector.write_bytes(old_selector)
            selector.chmod(0o700)
            updater.write_bytes(old_updater)
            updater.chmod(0o710)
            before = env.read_bytes()
            self._source(base)

            selected = self._run(base, "0.1.8", "--offline")
            self.assertEqual(selected.returncode, 0, selected.stderr)
            self.assertEqual(selector.read_bytes(), SELECT.read_bytes())
            self.assertEqual(selector.stat().st_mode & 0o777, 0o755)
            self.assertEqual(updater.read_bytes(), UPDATE.read_bytes())
            self.assertEqual(updater.stat().st_mode & 0o777, 0o755)
            records = self._recovery_records(base)
            self.assertEqual((records[0] / "selector.existed").read_text(), "1\n")
            self.assertEqual(
                (records[0] / "plebian-os-select-closure").read_bytes(),
                old_selector,
            )
            self.assertEqual(
                (records[0] / "plebian-os-select-closure").stat().st_mode & 0o777,
                0o700,
            )
            self.assertEqual((records[0] / "updater.existed").read_text(), "1\n")
            self.assertEqual(
                (records[0] / "plebian-os-update").read_bytes(), old_updater)
            self.assertEqual(
                (records[0] / "plebian-os-update").stat().st_mode & 0o777,
                0o710,
            )

            rolled_back = self._run(base, "--rollback")
            self.assertEqual(rolled_back.returncode, 0, rolled_back.stderr)
            self.assertEqual(env.read_bytes(), before)
            self.assertEqual(selector.read_bytes(), old_selector)
            self.assertEqual(selector.stat().st_mode & 0o777, 0o700)
            self.assertEqual(updater.read_bytes(), old_updater)
            self.assertEqual(updater.stat().st_mode & 0o777, 0o710)

    @staticmethod
    def _release_values(version="0.2.1", mode="1"):
        overrides = {"PLEBIAN_OS_VERSION": version, "PLEBIAN_OS_RELEASE": version,
                     "PLEBIAN_OS_RELEASE_MODE": mode}
        return [(k, overrides.get(k, v)) for k, v in INSTALLED_RELEASE_VALUES]

    # What Plebian-OS leaves under /etc/apt when it moves a machine off its
    # install snapshot; each one is evidence of that migration on its own.
    MIGRATION_EVIDENCE = (
        "sources.list.plebian-os-installer-snapshot",
        "sources.list.d/plebian-os-debian.sources",
    )
    # Written before a live switch that can still roll back, so never evidence.
    SECURITY_POLICY = "apt.conf.d/52plebian-os-security-upgrades"

    @staticmethod
    def _leave_install_snapshot(base: Path, evidence=MIGRATION_EVIDENCE):
        apt = base / "root" / "etc" / "apt"
        (apt / "sources.list.d" / "plebian-os-snapshot.sources").unlink()
        for name in evidence:
            (apt / name).parent.mkdir(parents=True, exist_ok=True)
            (apt / name).write_text("# written by Plebian-OS\n")

    def _assert_rollback_restores_selection(self, release, prepare):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base, release=release)
            before = env.read_bytes()
            self._source(base)
            selected = self._run(base, "0.1.8", "--offline")
            self.assertEqual(selected.returncode, 0, selected.stderr)
            prepare(base)

            result = self._run(base, "--rollback")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(env.read_bytes(), before)

    def test_rollback_below_live_apt_contract_is_refused_after_migration(self):
        for evidence in self.MIGRATION_EVIDENCE:
            with self.subTest(evidence=evidence), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                env = self._machine(base, release=self._release_values())
                selector = (base / "root" / "usr" / "local" / "bin" /
                            "plebian-os-select-closure")
                updater = base / "root" / "usr" / "local" / "bin" / "plebian-os-update"
                self._source(base)
                selected = self._run(base, "0.1.8", "--offline")
                self.assertEqual(selected.returncode, 0, selected.stderr)
                # No update runs here: the selector reads only the apt files that
                # Plebian-OS's own move to live Debian leaves behind.
                self._leave_install_snapshot(base, (evidence,))
                before = (env.read_bytes(), selector.read_bytes(), updater.read_bytes())

                refused = self._run(base, "--rollback")
                self.assertNotEqual(refused.returncode, 0)
                self.assertIn("left the Debian install snapshot", refused.stderr)
                self.assertIn("release 0.2.1 predates live security sources", refused.stderr)
                self.assertNotIn("by hand", refused.stderr)
                self.assertEqual(
                    (env.read_bytes(), selector.read_bytes(), updater.read_bytes()), before)
                records = self._recovery_records(base)
                self.assertEqual(len(records), 1)
                self.assertFalse((records[0] / "restored").exists())

    def test_rollback_to_a_0_2_2_record_works_after_migration(self):
        self._assert_rollback_restores_selection(
            self._release_values("0.2.2"), self._leave_install_snapshot)

    def test_rollback_to_a_development_record_works_after_migration(self):
        self._assert_rollback_restores_selection(
            self._release_values("0.2.1", mode="0"), self._leave_install_snapshot)

    def test_rollback_works_on_a_machine_unpinned_by_hand_but_never_migrated(self):
        def unpin_by_hand(base: Path):
            sources = base / "root" / "etc" / "apt" / "sources.list.d"
            (sources / "plebian-os-snapshot.sources").unlink()
            (sources / "debian.sources").write_text(
                "Types: deb\nURIs: https://deb.debian.org/debian\n")

        self._assert_rollback_restores_selection(self._release_values(), unpin_by_hand)

    def test_rollback_works_when_only_the_backports_source_is_present(self):
        def only_backports(base: Path):
            sources = base / "root" / "etc" / "apt" / "sources.list.d"
            (sources / "plebian-os-snapshot.sources").unlink()
            (sources / "plebian-os-debian-backports.sources").write_text(
                "Types: deb\nURIs: https://deb.debian.org/debian\n"
                "Suites: trixie-backports\nComponents: main\n"
            )

        self._assert_rollback_restores_selection(self._release_values(), only_backports)

    def test_rollback_before_update_still_works_while_snapshot_sources_remain(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base, release=self._release_values())
            before = env.read_bytes()
            self._source(base)
            selected = self._run(base, "0.1.8", "--offline")
            self.assertEqual(selected.returncode, 0, selected.stderr)
            self.assertTrue((base / "root" / "etc" / "apt" / "sources.list.d" /
                             "plebian-os-snapshot.sources").exists())

            result = self._run(base, "--rollback")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(env.read_bytes(), before)

    def test_rollback_works_when_a_failed_reconcile_left_only_the_security_policy(self):
        # A hand-unpinned host whose 0.2.2 post-commit reconcile wrote the
        # security policy and then rolled its live switch back.
        def failed_reconcile(base: Path):
            apt = base / "root" / "etc" / "apt"
            (apt / "sources.list.d" / "plebian-os-snapshot.sources").unlink()
            (apt / "sources.list.d" / "debian.sources").write_text(
                "Types: deb\nURIs: https://deb.debian.org/debian\n")
            (apt / self.SECURITY_POLICY).parent.mkdir(parents=True, exist_ok=True)
            (apt / self.SECURITY_POLICY).write_text("# written by Plebian-OS\n")

        self._assert_rollback_restores_selection(self._release_values(), failed_reconcile)

    def test_rollback_works_while_snapshot_sources_remain_beside_migration_files(self):
        def evidence_beside_snapshot(base: Path):
            apt = base / "root" / "etc" / "apt"
            for name in (*self.MIGRATION_EVIDENCE, self.SECURITY_POLICY):
                (apt / name).parent.mkdir(parents=True, exist_ok=True)
                (apt / name).write_text("# written by Plebian-OS\n")
            self.assertTrue((apt / "sources.list.d" / "plebian-os-snapshot.sources").exists())

        self._assert_rollback_restores_selection(
            self._release_values(), evidence_beside_snapshot)

    def test_target_updater_must_be_valid_shell(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            before = env.read_bytes()
            self._source(base, updater_bytes=b"#!/usr/bin/env bash\nif then\n")
            result = self._run(base, "0.1.8", "--offline")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid target updater", result.stderr)
            self.assertEqual(env.read_bytes(), before)
            self.assertEqual(self._recovery_records(base), [])

    def test_failed_rollback_retains_the_selected_session_and_selector(self):
        for boundary in ("rollback-selector", "rollback-updater", "rollback-session"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                env = self._machine(base)
                selector = (base / "root" / "usr" / "local" / "bin" /
                            "plebian-os-select-closure")
                updater = base / "root" / "usr" / "local" / "bin" / "plebian-os-update"
                self._source(base)
                selected = self._run(base, "0.1.8", "--offline")
                self.assertEqual(selected.returncode, 0, selected.stderr)
                selected_env = env.read_bytes()
                selected_selector = selector.read_bytes()
                selected_updater = updater.read_bytes()

                failed = self._run(base, "--rollback", fail_after=boundary)
                self.assertNotEqual(failed.returncode, 0)
                self.assertIn("selected session and installed tools were retained",
                              failed.stderr)
                self.assertEqual(env.read_bytes(), selected_env)
                self.assertEqual(selector.read_bytes(), selected_selector)
                self.assertEqual(updater.read_bytes(), selected_updater)
                records = self._recovery_records(base)
                self.assertEqual(len(records), 1)
                self.assertFalse((records[0] / "restored").exists())

                retried = self._run(base, "--rollback")
                self.assertEqual(retried.returncode, 0, retried.stderr)
                self.assertFalse(selector.exists())
                self.assertFalse(updater.exists())

    def test_selector_must_match_the_exact_target_commit(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            before = env.read_bytes()
            self._source(
                base,
                selector_bytes=b"#!/usr/bin/env bash\necho different-target-selector\n",
            )
            result = self._run(base, "0.1.8", "--offline")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("running selector does not match", result.stderr)
            self.assertEqual(env.read_bytes(), before)
            self.assertEqual(self._recovery_records(base), [])

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = self._machine(base)
            selector = (base / "root" / "usr" / "local" / "bin" /
                        "plebian-os-select-closure")
            updater = base / "root" / "usr" / "local" / "bin" / "plebian-os-update"
            before = env.read_bytes()
            self._source(base)
            result = self._run(base, "0.1.8", "--offline", "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("nothing was written", result.stdout)
            self.assertEqual(env.read_bytes(), before)
            self.assertFalse(selector.exists())
            self.assertFalse(updater.exists())
            self.assertEqual(self._recovery_records(base), [])

    def test_show_reports_the_installed_closure(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self._machine(base)
            result = self._run(base, "--show")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PLEBIAN_OS_VERSION=0.1.7", result.stdout)
            self.assertIn("KILIX_REF=6913364fe5f9eaa61258c0752b6ef12f55e49bc9",
                          result.stdout)


    def test_arm64_current_release_refuses_before_closure_or_tools_change(self):
        for dry_run in (False, True):
            with self.subTest(dry_run=dry_run), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                env_file = self._machine(base)
                before = env_file.read_bytes()
                manifest = (ROOT / 'releases/0.2.2.env').read_text()
                self._source(base, manifest_text=manifest, version='0.2.2',
                             release='0.2.2', tag='v0.2.2')
                bindir = base / 'bin'
                bindir.mkdir()
                uname = bindir / 'uname'
                uname.write_text('#!/bin/sh\necho aarch64\n')
                uname.chmod(0o755)
                args = ['0.2.2', '--source', str(base / 'src'), '--offline']
                if dry_run:
                    args.append('--dry-run')
                result = self._run(base, *args,
                    env_extra={'PATH': str(bindir) + ':' + os.environ['PATH']})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('no source-qualified ARM64 closure', result.stderr)
                self.assertEqual(env_file.read_bytes(), before)
                self.assertEqual(list((base / 'root/usr/local/bin').iterdir()), [])
                self.assertFalse((base / 'root/etc/pleb/closure.env').exists())

    def test_arm64_sidecar_is_read_but_amd64_waydroid_still_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            env_file = self._machine(base)
            before = env_file.read_bytes()
            manifest = (ROOT / 'releases/0.2.2.env').read_text()
            requirements = (ROOT / 'releases/0.2.2.requirements').read_text()
            self._source(base, manifest_text=manifest, version='0.2.2',
                         release='0.2.2', tag='v0.2.2',
                         arm64_manifest_text=manifest,
                         arm64_requirements_text=requirements)
            bindir = base / 'bin'
            bindir.mkdir()
            uname = bindir / 'uname'
            uname.write_text('#!/bin/sh\necho aarch64\n')
            uname.chmod(0o755)
            result = self._run(base, '0.2.2', '--source', str(base / 'src'),
                               '--offline', env_extra={'PATH': str(bindir) + ':' + os.environ['PATH']})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Waydroid closure is amd64-only', result.stderr)
            self.assertEqual(env_file.read_bytes(), before)


class ClosureSelectionContractTests(unittest.TestCase):
    """The selector is an operator tool with a privilege boundary and a
    documented place in the upgrade order."""

    def test_selector_refuses_to_run_as_root_like_the_updater(self):
        source = SELECT.read_text()
        self.assertIn("require_unprivileged_selector", source)
        self.assertIn(
            "run plebian-os-select-closure without sudo (it elevates only bounded system steps)",
            source)
        # The updater's own guard is untouched.
        self.assertIn(
            "run plebian-os-update without sudo (it elevates only bounded system steps)",
            UPDATE.read_text())

    def test_session_and_tools_are_replaced_only_after_all_backups(self):
        source = SELECT.read_text()
        self.assertIn('mv -fT -- "${tool_tmp[0]}" "${tool_paths[0]}"', source)
        self.assertIn('mv -fT -- "${tool_tmp[1]}" "${tool_paths[1]}"', source)
        self.assertIn('mv -fT -- "$env_tmp" "$env_path"', source)
        self.assertIn('cp -a -- "$env_path" "$record/session.env"', source)
        self.assertLess(source.index('cp -a -- "$env_path" "$record/session.env"'),
                        source.index('mv -fT -- "${tool_tmp[0]}" "${tool_paths[0]}"'))
        self.assertIn('tool_record_keys=(selector updater)', source)
        self.assertLess(source.index('cp -a -- "${tool_paths[$i]}" "$record/$name"'),
                        source.index('mv -fT -- "${tool_tmp[0]}" "${tool_paths[0]}"'))
        # Nothing is written before the rendered file has been verified.
        self.assertLess(source.index("verify_candidate_closure "),
                        source.index("apply_selected_closure\n"))

    def test_every_component_is_fetched_and_compared_before_rendering(self):
        source = SELECT.read_text()
        self.assertIn("prepare_component_ancestry_checks", source)
        self.assertIn("--no-tags --no-recurse-submodules", source)
        self.assertIn('merge-base --is-ancestor "$installed" "$target"', source)
        self.assertIn('merge-base --is-ancestor "$target" "$installed"', source)
        self.assertLess(
            source.index("prepare_component_ancestry_checks\n"),
            source.index("render_candidate_session_env "),
        )

    def test_upgrade_policy_names_the_concrete_command(self):
        text = UPGRADING.read_text()
        self.assertIn("plebian-os-select-closure", text)
        self.assertLess(text.index("plebian-os-select-closure"),
                        text.index("plebian-os-update --restart"))

    def test_release_procedure_requires_a_selection_mechanism_per_release(self):
        text = RELEASING.read_text()
        self.assertIn("plebian-os-select-closure", text)

    def test_plain_updater_selects_latest_before_the_stack_transaction(self):
        source = UPDATE.read_text()
        invocation = source.rindex("\nselect_latest_release_if_needed\n")
        transaction = source.rindex("\nbegin_stack_transaction\n")
        self.assertLess(invocation, transaction)
        self.assertIn("select_latest_release=1", source)
        self.assertIn("--revalidate-current) select_latest_release=0", source)
        self.assertIn("git ls-remote --refs --tags", source)
        self.assertIn(
            'exec "${relaunch_env[@]}" /usr/local/bin/plebian-os-update',
            source,
        )

    def test_upgrade_docs_make_latest_the_default(self):
        text = UPGRADING.read_text()
        self.assertIn("plain `plebian-os-update`", text)
        self.assertIn("highest version", text)
        self.assertIn("--revalidate-current", text)

    def test_target_release_notes_name_the_operator_command(self):
        text = NOTES.read_text()
        self.assertIn("plebian-os-select-closure", text)
        self.assertIn("provision/plebian-os-select-closure.sh", text)

    def test_selector_is_installed_by_every_os_delivery_path(self):
        destination = "/usr/local/bin/plebian-os-select-closure"
        update = UPDATE.read_text()
        provision = (ROOT / "provision" / "plebian-os-provision.sh").read_text()
        remaster = (ROOT / "build" / "remaster-iso.sh").read_text()
        preseed = (ROOT / "preseed" / "preseed.cfg").read_text()
        for text in (update, provision, preseed):
            self.assertIn(destination, text)
        self.assertIn("plebian-os-select-closure.sh", remaster)
        self.assertIn('[ "${#expected_hashes[@]}" -eq "$staged_count" ]', update)


FAKE_RM = r"""#!/bin/bash
/bin/rm "$@"; rc=$?
if [ -e "$ARM_FILE" ]; then
    for a in "$@"; do
        case "$a" in
            */selection-pending) /bin/rm -f "$ARM_FILE"; kill -TERM "$PPID" ;;
        esac
    done
fi
exit $rc
"""


class SelectionAttemptWindowTests(unittest.TestCase):
    """A finished cross-version selection must still roll back when a signal
    lands while selection-pending is removed."""

    def _helper(self):
        return ClosureSelectionTests(
            "test_rollback_restores_the_previous_closure_byte_for_byte")

    def _window(self, layout, signal_in_window):
        helper = self._helper()
        base = Path(self._td.name)
        env_path = helper._machine(base)
        helper._source(base)
        before_session = env_path.read_bytes()
        closure = base / "root/etc/pleb/closure.env"
        before_closure = closure.read_bytes() if closure.exists() else None
        shim = base / "shim"
        shim.mkdir()
        (shim / "rm").write_text(FAKE_RM)
        (shim / "rm").chmod(0o755)
        arm = base / "arm"
        if signal_in_window:
            arm.write_text("1\n")
        extra = {"PATH": f"{shim}:{os.environ['PATH']}", "ARM_FILE": str(arm)}
        if layout:
            extra["PLEBIAN_OS_CLOSURE_LAYOUT"] = layout
        selected = helper._run(base, "0.1.8", "--offline", env_extra=extra)
        state = base / "home/.local/gpu_terminal/pleb/state"
        attempt = state / "selection-attempt"
        pending = state / "selection-pending"
        tag = subprocess.run(
            ["git", "-C", str(base / "src"), "rev-parse", "refs/tags/v0.1.8"],
            capture_output=True, text=True, check=True).stdout.strip()
        facts = {
            "select_rc": selected.returncode,
            "select_err": (selected.stdout + selected.stderr)[-500:],
            "selection_changed_closure": (
                env_path.read_bytes() != before_session
                or (closure.exists() and closure.read_bytes() != before_closure)),
            "attempt_left": attempt.exists(),
            "pending_left": pending.exists(),
        }
        if signal_in_window:
            rollback_env = {"PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA": tag}
            if layout:
                rollback_env["PLEBIAN_OS_CLOSURE_LAYOUT"] = layout
            rolled = helper._run(base, "--rollback", env_extra=rollback_env)
            facts["rollback_rc"] = rolled.returncode
            facts["rollback_tail"] = (rolled.stdout + rolled.stderr)[-500:]
            facts["session_restored"] = env_path.read_bytes() == before_session
            facts["closure_restored"] = (
                (not closure.exists()) if before_closure is None
                else closure.read_bytes() == before_closure)
        return facts

    def test_a_signal_while_removing_pending_still_rolls_the_closure_back(self):
        for layout in (None, "split"):
            with self.subTest(layout=layout):
                self._td = tempfile.TemporaryDirectory()
                self.addCleanup(self._td.cleanup)
                facts = self._window(layout, True)
                self.assertTrue(facts["selection_changed_closure"], facts)
                self.assertTrue(facts["session_restored"], facts)
                self.assertTrue(facts["closure_restored"], facts)
                self.assertFalse(facts["attempt_left"], facts)

    def test_selection_without_that_signal_commits(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        facts = self._window(None, False)
        self.assertEqual(facts["select_rc"], 0, facts)
        self.assertTrue(facts["selection_changed_closure"], facts)
        self.assertFalse(facts["attempt_left"], facts)
        self.assertFalse(facts["pending_left"], facts)

    def test_a_recorded_match_is_not_an_interrupted_reselect_after_the_version_moves(self):
        helper = self._helper()
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            helper._machine(base)
            helper._source(base)
            selected = helper._run(base, "0.1.8", "--offline")
            self.assertEqual(selected.returncode, 0, selected.stderr)
            tag = subprocess.run(
                ["git", "-C", str(base / "src"), "rev-parse", "refs/tags/v0.1.8"],
                capture_output=True, text=True, check=True).stdout.strip()
            changed = False
            for path in (base / "root/etc/pleb/closure.env",
                         base / "root/etc/pleb/session.env"):
                if not path.is_file():
                    continue
                text = path.read_text()
                for old, new in (
                        ("PLEBIAN_OS_VERSION='0.1.8'", "PLEBIAN_OS_VERSION='0.1.7'"),
                        ("PLEBIAN_OS_VERSION=0.1.8", "PLEBIAN_OS_VERSION=0.1.7")):
                    if old in text:
                        path.write_text(text.replace(old, new, 1))
                        changed = True
                        break
                if changed:
                    break
            self.assertTrue(changed, "installed version was not 0.1.8")
            attempt = base / "home/.local/gpu_terminal/pleb/state/selection-attempt"
            attempt.parent.mkdir(parents=True, exist_ok=True)
            attempt.write_text(
                f"format=1\ntag={tag}\ntarget=0.1.8\ninstalled=0.1.8\n")
            rolled = helper._run(
                base, "--rollback",
                env_extra={"PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA": tag})
            combined = rolled.stdout + rolled.stderr
            self.assertNotIn("interrupted reselect", combined)
            self.assertFalse(attempt.exists())

    def test_a_different_recorded_version_is_not_an_interrupted_reselect(self):
        helper = self._helper()
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            helper._machine(base)
            helper._source(base)
            selected = helper._run(base, "0.1.8", "--offline")
            self.assertEqual(selected.returncode, 0, selected.stderr)
            tag = subprocess.run(
                ["git", "-C", str(base / "src"), "rev-parse", "refs/tags/v0.1.8"],
                capture_output=True, text=True, check=True).stdout.strip()
            attempt = base / "home/.local/gpu_terminal/pleb/state/selection-attempt"
            attempt.parent.mkdir(parents=True, exist_ok=True)
            attempt.write_text(
                f"format=1\ntag={tag}\ntarget=0.1.8\ninstalled=0.1.7\n")
            rolled = helper._run(
                base, "--rollback",
                env_extra={"PLEBIAN_OS_TRUSTED_TAG_OBJECT_SHA": tag})
            combined = rolled.stdout + rolled.stderr
            self.assertNotIn("interrupted reselect", combined)
            self.assertFalse(attempt.exists())

    def test_a_failure_before_pending_removes_the_attempt(self):
        helper = self._helper()
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            helper._machine(base)
            helper._source(base)
            hold = base / "hold"
            hold.write_text("not-a-fifo\n")
            result = helper._run(
                base, "0.1.8", "--offline",
                env_extra={"PLEBIAN_OS_SELECT_TEST_HOLD_BEFORE_PENDING": str(hold)})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "PLEBIAN_OS_SELECT_TEST_HOLD_BEFORE_PENDING must be a fifo",
                result.stderr)
            attempt = base / "home/.local/gpu_terminal/pleb/state/selection-attempt"
            self.assertFalse(
                attempt.exists(),
                attempt.read_text() if attempt.exists() else "")


if __name__ == "__main__":
    unittest.main()
