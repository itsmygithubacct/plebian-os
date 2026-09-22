"""The image must not come up with a daemon holding the default sound card.

A Debian package may ship a systemd *user* unit, and dh_installsystemduser's
postinst enables it for every account on the machine. A unit that opens the
default sound card at login holds the same card dictation records from, so
such an image ships degraded — or absent — voice capture out of the box.

These tests assert that capability, not a package name. The rule under test is
the one the image itself carries (``enabled_audio_holding_user_units`` and
``disable_audio_holding_user_units`` in ``plebian-os-provision.sh``); nothing
here restates it, so the guard and the shipped behaviour cannot drift. Every
fixture unit below is named for what it does, never after any package: a rule
that only caught one spelling would pass these and still ship the defect.

Reach, stated rather than assumed. Two arms model the real image from the
build machine's own dpkg database, and a package that is not installed here
contributes no evidence — so those arms see less on a foreign runner than on a
Debian build host. They carry a constructed positive control so that "found
nothing" can never be confused with "looked at nothing"; the universal arm is
the acceptance check that runs this same rule inside a real installed image.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"
INSTALL_DEPS = ROOT / "provision" / "install-deps.sh"
PRESEED = ROOT / "preseed" / "preseed.cfg"
BUILD_VM = ROOT / "build" / "build_vm_image.py"

DPKG_INFO = Path("/var/lib/dpkg/info")
USER_UNIT_DIRS = ("/usr/lib/systemd/user/", "/lib/systemd/user/")

# The runtime pieces Kilix Amp actually uses. Amp links libfluidsynth into its
# own process and renders MIDI through a General MIDI SoundFont; it never runs
# the fluidsynth player and never speaks to its daemon. The versioned soname is
# what a running program loads — the unversioned `libfluidsynth.so` belongs to
# the -dev package and is a link-time artefact, not a runtime one.
AMP_RUNTIME_SONAME = re.compile(r"/libfluidsynth\.so\.\d")
AMP_SOUNDFONT_PATHS = re.compile(r"^/usr/share/(sounds/sf2|soundfonts)/.*\.sf[23]$")


def clean_env():
    """A minimal environment: no inherited session, no Kilix state."""
    return {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": "/nonexistent", "LC_ALL": "C"}


def provision_call(body, root, env=None):
    """Run one call into the shipped provisioner's library, nothing else."""
    script = ('set -uo pipefail\n'
              'export PLEBIAN_OS_PROVISION_LIB_ONLY=1\n'
              f'. "{PROVISION}"\n'
              f'{body}\n')
    environment = clean_env() if env is None else dict(env)
    environment["PLEBIAN_OS_AUDIO_HOLDOFF_ROOT"] = str(root)
    return subprocess.run(["bash", "-c", script], env=environment,
                          text=True, capture_output=True, check=False)


def held_units(root):
    """The unit names the image's own rule says hold the default sound card."""
    result = provision_call("enabled_audio_holding_user_units", root)
    if result.returncode != 0:
        raise AssertionError(
            f"enumeration failed ({result.returncode}): {result.stderr}")
    return sorted(line.split("\t")[0]
                  for line in result.stdout.splitlines() if line.strip())


def apply_holdoff(root):
    return provision_call("DRY_RUN=0\ndisable_audio_holding_user_units", root)


def make_root(tmp):
    """An image-shaped root: real /usr/bin, so ExecStart programs resolve."""
    root = Path(tmp)
    (root / "etc/systemd/user/default.target.wants").mkdir(parents=True)
    (root / "usr/lib/systemd/user").mkdir(parents=True)
    (root / "usr").joinpath("bin").symlink_to("/usr/bin")
    return root


def install_unit(root, name, text, enable=True, wants="default.target"):
    """Install a user unit the way a Debian package and its postinst would."""
    (root / "usr/lib/systemd/user" / name).write_text(text)
    if enable:
        link = root / "etc/systemd/user" / f"{wants}.wants" / name
        link.parent.mkdir(parents=True, exist_ok=True)
        # Debian writes these absolute; the rule must resolve them inside the
        # root rather than following them out onto the build host.
        link.symlink_to(f"/usr/lib/systemd/user/{name}")


def an_audio_client_program():
    """Any real program on this machine that links an audio client library."""
    for candidate in sorted(Path("/usr/bin").glob("*")):
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            continue
        probe = subprocess.run(["ldd", str(candidate)], text=True,
                               capture_output=True, check=False)
        if probe.returncode != 0:
            continue
        if re.search(r"lib(asound|pulse|pipewire|jack)", probe.stdout):
            return candidate
    return None


# --- the install path, read the way the manifest tests read it ---------------

def preseed_packages():
    text = PRESEED.read_text()
    match = re.search(r"^d-i pkgsel/include string (?P<body>.*?)^d-i pkgsel/upgrade",
                      text, flags=re.MULTILINE | re.DOTALL)
    if not match:
        raise AssertionError("preseed pkgsel/include block not found")
    return set(match.group("body").replace("\\\n", " ").split())


def install_deps_packages():
    text = INSTALL_DEPS.read_text()
    packages = set()
    for match in re.finditer(r'^\s*"[^"|]+\|([^"]+)"', text, flags=re.MULTILINE):
        packages.update(match.group(1).split())
    if not packages:
        raise AssertionError("install-deps DEP_GROUPS not found")
    return packages


def install_path_packages():
    """Every package the two fresh-install routes name, version pins stripped."""
    return {name.split("=", 1)[0]
            for name in preseed_packages() | install_deps_packages()}


def dpkg_file_list(package):
    """The files a package ships, or None when this machine cannot say."""
    for name in (f"{package}.list", f"{package}:amd64.list",
                 f"{package}:all.list"):
        path = DPKG_INFO / name
        if path.is_file():
            return path.read_text().splitlines()
    return None


DPKG_STATUS = Path("/var/lib/dpkg/status")


def dependency_index():
    """{package: [dependencies]} from this machine's own dpkg status file.

    The install path names packages; what lands on the disk is their closure.
    The live defect arrives that way and not by being named: the FluidSynth
    *player* is a versioned hard Depends of libfluidsynth-dev, which Kilix Amp
    builds against and which is this image's only route to libpipewire-0.3-dev.
    A model built from named packages alone would not contain the very unit
    this test exists to catch.
    """
    if not DPKG_STATUS.is_file():
        return {}
    index, package, depends = {}, None, []
    for line in DPKG_STATUS.read_text(errors="replace").splitlines():
        if line.startswith("Package: "):
            if package:
                index[package] = depends
            package, depends = line[9:].strip(), []
        elif line.startswith(("Depends: ", "Pre-Depends: ")):
            body = line.split(": ", 1)[1]
            for group in body.split(","):
                # Take the first alternative: it is what apt installs when
                # nothing else already satisfies the group.
                first = group.split("|")[0].strip()
                name = first.split()[0] if first.split() else ""
                name = name.split(":", 1)[0]
                if name:
                    depends.append(name)
    if package:
        index[package] = depends
    return index


def install_closure(packages):
    """The named packages plus every dependency this machine can follow."""
    index = dependency_index()
    seen, queue = set(), list(packages)
    while queue:
        package = queue.pop()
        if package in seen:
            continue
        seen.add(package)
        queue.extend(index.get(package, ()))
    return seen


def resolve(packages):
    """{package: [files]} for each of these packages this machine can resolve."""
    resolved = {}
    for package in sorted(packages):
        files = dpkg_file_list(package)
        if files is not None:
            resolved[package] = files
    return resolved


def resolve_install_path(packages):
    """What lands on the disk: the named packages and their closure."""
    return resolve(install_closure(packages))


def model_the_image(root, resolved):
    """Recreate, under `root`, the user units the install path would enable.

    A package's unit is enabled on installation exactly when it carries an
    [Install] WantedBy — that is what dh_installsystemduser's postinst acts on.
    """
    enabled = []
    for files in resolved.values():
        for path in files:
            if not any(path.startswith(d) for d in USER_UNIT_DIRS):
                continue
            source = Path(path)
            if not source.is_file():
                continue
            text = source.read_text(errors="replace")
            wants = re.search(r"^WantedBy=(\S+)", text, flags=re.MULTILINE)
            install_unit(root, source.name, text, enable=bool(wants),
                         wants=wants.group(1) if wants else "default.target")
            if wants:
                enabled.append(source.name)
    return sorted(enabled)


class AudioHoldoffRuleTests(unittest.TestCase):
    """The rule itself: what it catches, what it leaves alone."""

    def setUp(self):
        self.root = make_root(self.enterContext(
            tempfile.TemporaryDirectory()))

    def test_a_login_daemon_that_asks_for_the_sound_stack_is_disabled(self):
        install_unit(self.root, "midi-render-daemon.service", """[Unit]
Description=A synthesiser nobody asked to run
After=sound.target
Wants=pipewire.service pulseaudio.service
[Service]
ExecStart=/usr/bin/midi-render-daemon -is
[Install]
WantedBy=default.target
""")
        install_unit(self.root, "notes-sync.service", """[Unit]
Description=Something that never touches audio
[Service]
ExecStart=/bin/true
[Install]
WantedBy=default.target
""")
        self.assertEqual(held_units(self.root), ["midi-render-daemon.service"])
        result = apply_holdoff(self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        # The capability, re-measured rather than inferred from the removal.
        self.assertEqual(held_units(self.root), [])
        self.assertFalse(
            (self.root / "etc/systemd/user/default.target.wants"
             / "midi-render-daemon.service").exists())
        # And the unrelated login unit is still enabled: this disables what
        # holds the card, not everything that starts at login.
        self.assertTrue(
            (self.root / "etc/systemd/user/default.target.wants"
             / "notes-sync.service").is_symlink())

    def test_a_login_daemon_that_declares_nothing_is_still_caught(self):
        """The second signal: what the program links, not what it declares."""
        donor = an_audio_client_program()
        if donor is None:
            self.skipTest("no program on this machine links an audio client "
                          "library, so the linkage signal cannot be exercised "
                          "here; the declaration signal above still runs")
        program = self.root / "usr/lib/systemd/quiet-audio-client"
        shutil.copy2(donor, program)
        program.chmod(0o755)
        install_unit(self.root, "quiet-audio-client.service", f"""[Unit]
Description=Declares no dependency on the sound stack at all
[Service]
ExecStart=/usr/lib/systemd/quiet-audio-client
[Install]
WantedBy=default.target
""")
        self.assertEqual(held_units(self.root), ["quiet-audio-client.service"])
        self.assertEqual(apply_holdoff(self.root).returncode, 0)
        self.assertEqual(held_units(self.root), [])

    def test_the_machines_own_sound_server_is_never_disabled(self):
        """Disabling the sound server would take the card away, not free it."""
        for unit in ("pulseaudio.service", "pipewire.service",
                     "wireplumber.service"):
            install_unit(self.root, unit, f"""[Unit]
Description={unit} — this machine's sound server
After=sound.target
[Service]
ExecStart=/usr/bin/{unit.split('.')[0]}
[Install]
WantedBy=default.target
""")
        self.assertEqual(held_units(self.root), [])
        self.assertEqual(apply_holdoff(self.root).returncode, 0)
        for unit in ("pulseaudio.service", "pipewire.service",
                     "wireplumber.service"):
            self.assertTrue(
                (self.root / "etc/systemd/user/default.target.wants"
                 / unit).is_symlink(), unit)

    def test_a_unit_that_is_installed_but_not_enabled_is_left_alone(self):
        """Only an *enabled* unit runs at login, and only that is the defect."""
        install_unit(self.root, "midi-render-daemon.service", """[Unit]
Description=Present but not wanted by any target
After=sound.target
[Service]
ExecStart=/usr/bin/midi-render-daemon
""", enable=False)
        self.assertEqual(held_units(self.root), [])

    def test_a_vendor_enabled_unit_is_overridden_where_dpkg_cannot_undo_it(self):
        install_unit(self.root, "midi-render-daemon.service", """[Unit]
Description=Enabled by a link the package owns
After=sound.target
[Service]
ExecStart=/usr/bin/midi-render-daemon
[Install]
WantedBy=default.target
""", enable=False)
        vendor = self.root / "usr/lib/systemd/user/default.target.wants"
        vendor.mkdir(parents=True)
        (vendor / "midi-render-daemon.service").symlink_to(
            "/usr/lib/systemd/user/midi-render-daemon.service")
        self.assertEqual(held_units(self.root), ["midi-render-daemon.service"])
        self.assertEqual(apply_holdoff(self.root).returncode, 0)
        self.assertEqual(held_units(self.root), [])
        override = self.root / "etc/systemd/user/midi-render-daemon.service"
        self.assertEqual(os.readlink(override), "/dev/null")


class InstallPathAudioHoldoffTests(unittest.TestCase):
    """The install path, modelled from this machine's real package contents."""

    def setUp(self):
        self.tmp = self.enterContext(
            tempfile.TemporaryDirectory())

    def test_the_install_path_leaves_nothing_holding_the_default_sound_card(self):
        resolved = resolve_install_path(install_path_packages())
        # Absent is not the same as invisible: a scan that resolved nothing
        # would "find no defect" without having looked at anything.
        self.assertGreater(
            len(resolved), 0,
            "no package named by the install path could be resolved on this "
            "machine, so this arm saw nothing and proves nothing")
        root = make_root(self.tmp)
        enabled = model_the_image(root, resolved)

        # Positive control, constructed so it fires wherever this runs: the
        # same modelled image, plus one login daemon that holds the card.
        control = make_root(
            self.enterContext(tempfile.TemporaryDirectory()))
        model_the_image(control, resolved)
        install_unit(control, "midi-render-daemon.service", """[Unit]
Description=Control — a login daemon that holds the default sound card
After=sound.target
Wants=pulseaudio.service
[Service]
ExecStart=/usr/bin/midi-render-daemon
[Install]
WantedBy=default.target
""")
        self.assertIn("midi-render-daemon.service", held_units(control),
                      "the rule failed to see a planted login audio daemon, "
                      "so its verdict on the real image means nothing")

        # The capability: after the image's own hold-off runs, nothing that
        # starts at login holds the card. Packages named by the install path
        # that this machine cannot resolve are reported, not assumed clean.
        self.assertEqual(apply_holdoff(root).returncode, 0)
        self.assertEqual(
            held_units(root), [],
            f"modelled from {len(resolved)} resolvable packages "
            f"({len(enabled)} enabled user units)")

    def test_the_install_path_provides_what_kilix_amp_loads_at_runtime(self):
        """Amp needs the library and a SoundFont — proven by test, not read.

        Masking each piece in turn under a private mount namespace: without the
        player package Amp renders and plays identically; without the SoundFont
        it reports a zero-length track; without the versioned library it cannot
        start at all. So these two are what the image owes it.
        """
        # Resolved over the packages the install path *names*, not over their
        # closure. install-deps.sh states the policy in its own words —
        # "keep the runtime libraries explicit rather than relying on the -dev
        # toolchain" — and it is load-bearing: the closure supplies Amp's
        # library today only because libfluidsynth-dev is in the image, so an
        # image that ever drops the build toolchain would lose Amp's library
        # without a single list changing. This arm is what notices.
        resolved = resolve(install_path_packages())
        self.assertGreater(len(resolved), 0, "nothing resolvable here")
        library = sorted(package for package, files in resolved.items()
                         if any(AMP_RUNTIME_SONAME.search(f) for f in files))
        soundfont = sorted(package for package, files in resolved.items()
                           if any(AMP_SOUNDFONT_PATHS.match(f) for f in files))
        if not library and not soundfont:
            self.skipTest(
                "neither the FluidSynth runtime library nor a General MIDI "
                "SoundFont is installed on this machine, so the install "
                f"path's provision of them is invisible here ({len(resolved)} "
                "packages resolved)")
        self.assertTrue(
            library,
            "the install path names no package providing a versioned "
            "libfluidsynth soname; Kilix Amp would not start. The -dev "
            "package's unversioned libfluidsynth.so is a link-time artefact "
            "and does not count.")
        self.assertTrue(
            soundfont,
            "the install path names no package providing a General MIDI "
            "SoundFont on a path Kilix Amp searches; MIDI playback would "
            "render a zero-length track.")


class AudioHoldoffWiringTests(unittest.TestCase):
    """That the rule is reached — on a real install and on a real image."""

    def test_provisioning_runs_the_holdoff_after_everything_installs(self):
        """It must run last, not merely after this repository's own apt call.

        `pleb install` is the final step that installs packages, and it
        installs some this repository never names — its own runtime set, and
        whatever the pinned Kilix build-dependency installer pulls in. A
        hold-off that ran only before it would be undone by it.
        """
        text = PROVISION.read_text()
        sequence = text.split("begin_provision_root_transaction\n")[-1]
        self.assertIn("disable_audio_holding_user_units", sequence)
        deps = text.index('bash "$DEPS_SCRIPT"')
        pleb_install = text.index('"$PLEB_DIR/bin/pleb" install')
        calls = [m.start() for m in
                 re.finditer(r"^disable_audio_holding_user_units$", text,
                             flags=re.MULTILINE)]
        self.assertTrue(calls, "the hold-off is never called")
        self.assertTrue(any(call > deps for call in calls),
                        "the hold-off must run after this repository's own "
                        "package install")
        self.assertTrue(any(call > pleb_install for call in calls),
                        "the hold-off must run after `pleb install`, which is "
                        "the last step that can add a package — and which "
                        "installs the FluidSynth player by name at the pinned "
                        "PLEB_REF, and again through the pinned Kilix's "
                        "scripts/install-build-deps.sh")

    def test_the_image_is_accepted_on_the_capability_not_on_a_package_list(self):
        text = BUILD_VM.read_text()
        self.assertIn('("no login audio daemon", audio_holdoff)', text)
        self.assertIn("enabled_audio_holding_user_units", text)
        # The guest asks the installed system, using the provisioner's own
        # rule; it must not carry a second copy that could drift.
        self.assertNotIn("libasound", text)
        self.assertNotIn("fluidsynth", text)

    def test_a_check_that_cannot_run_is_a_failure_and_never_a_pass(self):
        """The guest command's three outcomes, run here against real roots."""
        guest = (
            'export PLEBIAN_OS_PROVISION_LIB_ONLY=1; '
            '. "$1" >/dev/null 2>&1 || exit 2; '
            'held=$(enabled_audio_holding_user_units) || exit 2; '
            'test -z "$held" || { echo "$held" >&2; exit 1; }'
        )
        tmp = Path(self.enterContext(
            tempfile.TemporaryDirectory()))
        clean = make_root(tmp / "clean")
        dirty = make_root(tmp / "dirty")
        install_unit(dirty, "midi-render-daemon.service", """[Unit]
After=sound.target
[Service]
ExecStart=/usr/bin/midi-render-daemon
[Install]
WantedBy=default.target
""")

        def run(script, root):
            env = clean_env()
            env["PLEBIAN_OS_AUDIO_HOLDOFF_ROOT"] = str(root)
            return subprocess.run(["bash", "-c", guest, "guest", str(script)],
                                  env=env, text=True, capture_output=True,
                                  check=False).returncode

        self.assertEqual(run(PROVISION, clean), 0)
        self.assertEqual(run(PROVISION, dirty), 1)
        self.assertEqual(run(tmp / "absent.sh", clean), 2)


if __name__ == "__main__":
    unittest.main()
