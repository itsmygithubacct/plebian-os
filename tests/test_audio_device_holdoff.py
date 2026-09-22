"""The image must not come up with a daemon holding the default sound card.

A Debian package may ship a systemd *user* unit, and dh_installsystemduser's
postinst enables it for every account on the machine. A unit that opens the
default sound card at login holds the same card dictation records from, so
such an image ships degraded — or absent — voice capture out of the box.

These tests assert that capability, not a package name. The rule under test is
the one the image itself carries (``enabled_audio_holding_user_units`` and
``disable_audio_holding_user_units`` in ``plebian-os-provision.sh``); nothing
here restates its verdict, so the guard and the shipped behaviour cannot
drift. Every fixture unit below is named for what it does, never after any
package: a rule that only caught one spelling would pass these and still ship
the defect.

Two exceptions, both deliberate and both narrow. ``model_the_image`` restates
what *dpkg* does when it installs a unit, because the test has to build the
image before it can ask about it. And ``units_the_install_path_never_asked_for``
is an independent, deliberately coarse oracle over the same modelled image; it
decides only whether this machine can exercise the arm's teeth, never whether
the image is acceptable. It exists because a zero from a query is evidence
about the query: without it, "the rule reported nothing" cannot be told apart
from "the rule was blinded", and a mutation that widens the rule's exemption
until it swallows the real daemon passes unnoticed.

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
UPDATE = ROOT / "provision" / "plebian-os-update.sh"
INSTALL_DEPS = ROOT / "provision" / "install-deps.sh"
PRESEED = ROOT / "preseed" / "preseed.cfg"
BUILD_VM = ROOT / "build" / "build_vm_image.py"

DPKG_INFO = Path("/var/lib/dpkg/info")
USER_UNIT_DIRS = ("/usr/lib/systemd/user/", "/lib/systemd/user/")

# The root-owned, on-disk members of the user-unit search path, as
# `systemd-analyze --user unit-paths` reports them and as the provisioner
# enumerates them. The per-user and per-boot directories systemd also searches
# are outside the image and outside what provisioning may touch; the arm below
# that proves `systemctl --user enable` survives is the other half of that.
UNIT_DIRS_UNDER_ROOT = (
    "etc/systemd/user",
    "run/systemd/user",
    "usr/local/share/systemd/user",
    "usr/share/systemd/user",
    "usr/local/lib/systemd/user",
    "usr/lib/systemd/user",
)

# The three directory suffixes systemd honours as enablement, from
# [Install] WantedBy=, RequiredBy= and UpheldBy= respectively.
ENABLEMENT_SUFFIXES = (".wants", ".requires", ".upholds")
INSTALL_KEYS = {"wants": "WantedBy", "requires": "RequiredBy",
                "upholds": "UpheldBy"}

# The runtime pieces Kilix Amp actually uses. Amp links libfluidsynth into its
# own process and renders MIDI through a General MIDI SoundFont; it never runs
# the fluidsynth player and never speaks to its daemon. The versioned soname is
# what a running program loads — the unversioned `libfluidsynth.so` belongs to
# the -dev package and is a link-time artefact, not a runtime one.
AMP_RUNTIME_SONAME = re.compile(r"/libfluidsynth\.so\.\d")
AMP_SOUNDFONT_PATHS = re.compile(r"^/usr/share/(sounds/sf2|soundfonts)/.*\.sf[23]$")

AUDIO_CLIENT_LIBRARY = re.compile(r"lib(asound|pulse|pipewire|jack)")
INSTALL_SECTION_ENABLES = re.compile(r"^(WantedBy|RequiredBy|UpheldBy)=(\S+)",
                                     flags=re.MULTILINE)
EXEC_START_PROGRAM = re.compile(r"^ExecStart=[-@+!:]*(\S+)", flags=re.MULTILINE)


def clean_env(**extra):
    """A minimal environment: no inherited session, no Kilix state."""
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
           "HOME": "/nonexistent", "LC_ALL": "C"}
    env.update(extra)
    return env


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


def held_units(root, env=None):
    """The unit names the image's own rule says hold the default sound card."""
    result = provision_call("enabled_audio_holding_user_units", root, env=env)
    if result.returncode != 0:
        raise AssertionError(
            f"enumeration failed ({result.returncode}): {result.stderr}")
    return sorted(line.split("\t")[0]
                  for line in result.stdout.splitlines() if line.strip())


def apply_holdoff(root, env=None):
    return provision_call("DRY_RUN=0\ndisable_audio_holding_user_units", root,
                          env=env)


def make_root(tmp):
    """An image-shaped root: real /usr/bin, so ExecStart programs resolve."""
    root = Path(tmp)
    (root / "etc/systemd/user/default.target.wants").mkdir(parents=True)
    (root / "usr/lib/systemd/user").mkdir(parents=True)
    (root / "usr").joinpath("bin").symlink_to("/usr/bin")
    return root


def install_unit(root, name, text, enable=True, wants="default.target",
                 kind="wants", unit_dir="usr/lib/systemd/user",
                 link_dir="etc/systemd/user"):
    """Install a user unit the way a Debian package and its postinst would.

    `kind` selects the enablement shape: "wants", "requires" or "upholds" —
    what systemd creates for [Install] WantedBy=, RequiredBy= and UpheldBy=.
    `unit_dir` and `link_dir` select where in the user-unit search path the
    unit file and its enablement link land.
    """
    unit_path = root / unit_dir / name
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(text)
    if enable:
        link = root / link_dir / f"{wants}{kind if kind.startswith('.') else '.' + kind}" / name
        link.parent.mkdir(parents=True, exist_ok=True)
        # Debian writes these absolute; the rule must resolve them inside the
        # root rather than following them out onto the build host.
        link.symlink_to(f"/{unit_dir}/{name}")
    return unit_path


def a_holding_unit(description, execstart="/usr/bin/midi-render-daemon -is",
                   install="WantedBy=default.target"):
    """A unit that says, in systemd's own words, that it wants the sound stack.

    Wants= is a real dependency: it says this unit should be pulled up with the
    sound stack. It is not the same as After=, which only orders.
    """
    return f"""[Unit]
Description={description}
Wants=pipewire.service pulseaudio.service
[Service]
ExecStart={execstart}
[Install]
{install}
"""


def enablement_links(root, unit):
    """Every enablement link naming `unit`, anywhere on the search path."""
    found = []
    for directory in UNIT_DIRS_UNDER_ROOT:
        base = root / directory
        if not base.is_dir():
            continue
        for suffix in ENABLEMENT_SUFFIXES:
            found.extend(str(p) for p in base.glob(f"*{suffix}/{unit}"))
    return sorted(found)


def unit_is_masked(root, unit):
    override = root / "etc/systemd/user" / unit
    return override.is_symlink() and os.readlink(override) == "/dev/null"


def unit_cannot_start_at_login(root, unit):
    """Measured on the filesystem, not taken from the rule's own report."""
    return unit_is_masked(root, unit) or not enablement_links(root, unit)


def an_audio_client_program():
    """Any real program on this machine that links an audio client library."""
    for candidate in sorted(Path("/usr/bin").glob("*")):
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            continue
        probe = subprocess.run(["ldd", str(candidate)], text=True,
                               capture_output=True, check=False)
        if probe.returncode != 0:
            continue
        if AUDIO_CLIENT_LIBRARY.search(probe.stdout):
            return candidate
    return None


def a_linkage_report_larger_than_a_pipe_buffer(directory):
    """A stub `ldd` whose report is far larger than a pipe buffer.

    The regression this exists to guard is a pipeline — `ldd prog | grep -q
    lib…`. grep exits at the first match, ldd is killed by SIGPIPE once the
    64 KiB pipe buffer fills, and under `set -o pipefail` the pipeline reports
    141, so a program that DOES link the sound stack reads as clean. A real
    binary's report is a few hundred bytes and never fills the buffer, which
    is why a fixture built from one cannot exercise this at all: the mutation
    that restores the bad shape passes against it. This one makes it fire, and
    the arm that uses it proves so before it proves anything else.
    """
    stub = directory / "ldd"
    stub.write_text(
        "#!/bin/sh\n"
        "printf '\\tlibasound.so.2 => /lib/x86_64-linux-gnu/libasound.so.2"
        " (0x00007f0000000000)\\n'\n"
        "awk 'BEGIN{for(i=0;i<8000;i++)"
        " printf \"\\tlibpadding%05d.so.0 => /usr/lib/libpadding%05d.so.0"
        " (0x0000000000000000)\\n\", i, i}'\n")
    stub.chmod(0o755)
    return stub


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


def shipped_user_units(resolved):
    """(package, path, text) for every user unit those packages ship."""
    for package, files in sorted(resolved.items()):
        for path in files:
            if not any(path.startswith(d) for d in USER_UNIT_DIRS):
                continue
            source = Path(path)
            if not source.is_file():
                continue
            yield package, source, source.read_text(errors="replace")


def enablement_of(text):
    """(target, kind) a package's postinst would enable this unit as, or None.

    A unit is enabled on installation exactly when it carries an [Install]
    WantedBy=, RequiredBy= or UpheldBy= — the three keys systemd turns into a
    `.wants/`, `.requires/` or `.upholds/` link, and the first two are what
    deb-systemd-helper acts on for dh_installsystemduser. A model that read
    only one of them would build an image with the defect left out, and the
    install-path arm would then prove the rule clean against a picture that
    could not contain the thing it exists to catch.
    """
    install = INSTALL_SECTION_ENABLES.search(text)
    if not install:
        return None
    return install.group(2), {"WantedBy": "wants", "RequiredBy": "requires",
                              "UpheldBy": "upholds"}[install.group(1)]


def model_the_image(root, resolved):
    """Recreate, under `root`, the user units the install path would enable."""
    enabled = []
    for _package, source, text in shipped_user_units(resolved):
        install = enablement_of(text)
        install_unit(root, source.name, text, enable=bool(install),
                     wants=install[0] if install else "default.target",
                     kind=install[1] if install else "wants")
        if install:
            enabled.append(source.name)
    return sorted(enabled)


def units_the_install_path_never_asked_for(resolved, named):
    """Enabled user units from packages the install path does not name, whose
    ExecStart program links an audio client library.

    An independent, deliberately narrow oracle. It is used for one thing only:
    to decide whether this machine's modelled image can exercise the teeth of
    the install-path arm. It never decides whether the image is acceptable.

    It asks the one question the rule cannot reasonably disagree with — does
    this program link an audio client library? — over the one set this whole
    wave is about: packages that arrive through the dependency closure without
    being named. Because it consults neither the rule's exemption list nor its
    declaration signal, a change that blinds the rule to such a unit cannot
    also blind this, which is what lets the arm tell "the hold-off cleared it"
    from "the rule never saw it".
    """
    holders = []
    for package, source, text in shipped_user_units(resolved):
        if package in named:
            continue
        if not INSTALL_SECTION_ENABLES.search(text):
            continue
        program = EXEC_START_PROGRAM.search(text)
        if not program:
            continue
        binary = program.group(1)
        if not binary.startswith("/") or not os.access(binary, os.X_OK):
            continue
        probe = subprocess.run(["ldd", binary], text=True,
                               capture_output=True, check=False)
        if probe.returncode == 0 and AUDIO_CLIENT_LIBRARY.search(probe.stdout):
            holders.append(source.name)
    return sorted(set(holders))


class AudioHoldoffRuleTests(unittest.TestCase):
    """The rule itself: what it catches, what it leaves alone."""

    def setUp(self):
        self.root = make_root(self.enterContext(
            tempfile.TemporaryDirectory()))

    def test_a_login_daemon_that_asks_for_the_sound_stack_is_disabled(self):
        install_unit(self.root, "midi-render-daemon.service",
                     a_holding_unit("A synthesiser nobody asked to run"))
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

    def test_every_enablement_shape_systemd_honours_is_caught(self):
        """WantedBy=, RequiredBy= and UpheldBy= are three ways to say "enabled".

        systemd.unit(5) turns them into `.wants/`, `.requires/` and
        `.upholds/` links respectively, and deb-systemd-helper writes the
        first two from a package's own [Install] section. A rule that
        enumerated only one of them would report a clean image while the card
        was held — and so would the acceptance check that runs it.
        """
        for kind, key in sorted(INSTALL_KEYS.items()):
            with self.subTest(enablement=kind):
                root = make_root(self.enterContext(
                    tempfile.TemporaryDirectory()))
                install_unit(root, "midi-render-daemon.service",
                             a_holding_unit(f"Enabled through {key}",
                                            install=f"{key}=default.target"),
                             kind=kind)
                link = (root / "etc/systemd/user"
                        / f"default.target.{kind}"
                        / "midi-render-daemon.service")
                self.assertTrue(link.is_symlink(), link)
                self.assertEqual(held_units(root),
                                 ["midi-render-daemon.service"])
                self.assertEqual(apply_holdoff(root).returncode, 0)
                self.assertEqual(held_units(root), [])
                self.assertFalse(link.exists())

    def test_an_enablement_anywhere_on_the_search_path_is_caught(self):
        """systemd reads six root-owned unit directories, not two.

        `/usr/local/lib/systemd/user/*.wants/` is where a local admin or a
        third-party installer puts one, and nothing about it is exotic: it is
        on the path `systemd-analyze --user unit-paths` prints. Enumerating
        only /etc and /usr/lib leaves four directories in which a daemon can
        hold the card while the check says the image is clean.
        """
        for directory in UNIT_DIRS_UNDER_ROOT:
            with self.subTest(unit_directory=directory):
                root = make_root(self.enterContext(
                    tempfile.TemporaryDirectory()))
                install_unit(root, "midi-render-daemon.service",
                             a_holding_unit(f"Enabled under /{directory}"),
                             unit_dir=directory, link_dir=directory)
                self.assertEqual(held_units(root),
                                 ["midi-render-daemon.service"])
                self.assertEqual(apply_holdoff(root).returncode, 0)
                self.assertEqual(held_units(root), [])
                self.assertTrue(
                    unit_cannot_start_at_login(
                        root, "midi-render-daemon.service"))

    def test_a_dropin_on_the_login_target_is_caught(self):
        """The third shape: no link anywhere, and the daemon still starts.

        A `default.target.d/*.conf` fragment that says `Wants=` pulls its unit
        up at login exactly as a `.wants/` link does, and no glob over
        `*.wants/` will ever see it. The login target is reached by
        definition, so this needs no dependency-graph reasoning.
        """
        install_unit(self.root, "midi-render-daemon.service",
                     a_holding_unit("Pulled in by a drop-in, not a link"),
                     enable=False)
        dropin = self.root / "etc/systemd/user/default.target.d/50-extra.conf"
        dropin.parent.mkdir(parents=True)
        dropin.write_text("[Unit]\nWants=midi-render-daemon.service\n")
        self.assertEqual(held_units(self.root), ["midi-render-daemon.service"])
        self.assertEqual(apply_holdoff(self.root).returncode, 0)
        self.assertEqual(held_units(self.root), [])
        # A fragment is not a link: it is neutralised with the override that
        # outlives a package upgrade, and the admin's own file is left intact
        # so the change is inspectable rather than mysterious.
        self.assertTrue(unit_is_masked(self.root, "midi-render-daemon.service"))
        self.assertTrue(dropin.is_file())

    def test_ordering_alone_does_not_condemn_a_unit_that_never_opens_the_card(self):
        """After= is ordering. Ordering is not use.

        `After=pipewire.service` says only *when* a unit may start. A
        well-behaved desktop helper that wants to run once audio is up says
        exactly that and opens nothing, and disabling it would be a plain
        false positive. Both directions are proved here, because dropping a
        signal is only safe if what the signal was for is still caught.
        """
        install_unit(self.root, "notes-sync.service", """[Unit]
Description=Notes sync, ordered after the sound stack only
After=pipewire.service pulseaudio.service
After=sound.target
[Service]
ExecStart=/bin/true
[Install]
WantedBy=default.target
""")
        install_unit(self.root, "midi-render-daemon.service",
                     a_holding_unit("Wants the sound stack, not merely after it",
                                    execstart="/bin/true"))
        self.assertEqual(held_units(self.root), ["midi-render-daemon.service"],
                         "ordering alone must not condemn, and a declared "
                         "dependency must still condemn")
        self.assertEqual(apply_holdoff(self.root).returncode, 0)
        self.assertTrue(
            (self.root / "etc/systemd/user/default.target.wants"
             / "notes-sync.service").is_symlink(),
            "a unit that only asked to start after audio was killed for it")

    def test_a_unit_ordered_after_the_sound_stack_that_opens_the_card_still_dies(self):
        """The other direction: ordering is not a licence, either."""
        donor = an_audio_client_program()
        if donor is None:
            self.skipTest("no program on this machine links an audio client "
                          "library, so the linkage signal cannot be exercised "
                          "here")
        program = self.root / "usr/lib/systemd/ordered-audio-client"
        program.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(donor, program)
        program.chmod(0o755)
        install_unit(self.root, "ordered-audio-client.service", """[Unit]
Description=Declares only an ordering relation, and opens the card anyway
After=pipewire.service
[Service]
ExecStart=/usr/lib/systemd/ordered-audio-client
[Install]
WantedBy=default.target
""")
        self.assertEqual(held_units(self.root), ["ordered-audio-client.service"])
        self.assertEqual(apply_holdoff(self.root).returncode, 0)
        self.assertEqual(held_units(self.root), [])

    def test_a_login_daemon_that_declares_nothing_is_still_caught(self):
        """The second signal: what the program links, not what it declares."""
        donor = an_audio_client_program()
        if donor is None:
            self.skipTest("no program on this machine links an audio client "
                          "library, so the linkage signal cannot be exercised "
                          "here; the declaration signal above still runs")
        program = self.root / "usr/lib/systemd/quiet-audio-client"
        program.parent.mkdir(parents=True, exist_ok=True)
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

    def test_a_linkage_report_larger_than_a_pipe_buffer_is_not_read_as_clean(self):
        """The SIGPIPE shape, exercised on a fixture that can actually fail it.

        `ldd prog | grep -q lib…` reports 141 under `set -o pipefail` once the
        report outgrows the pipe buffer, so the unit reads as clean. Every
        real binary on this machine produces a few hundred bytes, which is far
        too little: against such a fixture the bad shape passes, and a mutant
        that restores it survives. The arm proves its own fixture first.
        """
        stub_dir = Path(self.enterContext(tempfile.TemporaryDirectory()))
        a_linkage_report_larger_than_a_pipe_buffer(stub_dir)
        env = clean_env(PATH=f"{stub_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}")

        program = self.root / "usr/lib/systemd/large-linkage-client"
        program.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2("/bin/true", program)
        program.chmod(0o755)
        install_unit(self.root, "large-linkage-client.service", """[Unit]
Description=Declares nothing; its linkage report is enormous
[Service]
ExecStart=/usr/lib/systemd/large-linkage-client
[Install]
WantedBy=default.target
""")

        # Control on the control. Before asserting that the shipped checker
        # gets this right, prove the fixture is capable of making the wrong
        # shape fail — otherwise this arm guards nothing.
        report = subprocess.run(["ldd", str(program)], env=env, text=True,
                                capture_output=True, check=False)
        self.assertGreater(
            len(report.stdout), 65536,
            "the fixture's linkage report fits in a pipe buffer, so the shape "
            "this arm exists to catch cannot fail against it")
        bad_shape = subprocess.run(
            ["bash", "-c",
             'set -uo pipefail; ldd "$1" | grep -qE '
             '"lib(asound|pulse|pipewire|jack)"',
             "bad-shape", str(program)],
            env=env, text=True, capture_output=True, check=False)
        self.assertNotEqual(
            bad_shape.returncode, 0,
            "the piped form succeeded on this fixture, so the fixture cannot "
            "distinguish the shipped checker from the broken one")

        # And now the thing that matters: the shipped checker sees it.
        self.assertEqual(held_units(self.root, env=env),
                         ["large-linkage-client.service"])
        self.assertEqual(apply_holdoff(self.root, env=env).returncode, 0)
        self.assertEqual(held_units(self.root, env=env), [])

    def test_the_machines_own_sound_server_is_never_disabled(self):
        """Disabling the sound server would take the card away, not free it."""
        for unit in ("pulseaudio.service", "pipewire.service",
                     "wireplumber.service"):
            install_unit(self.root, unit,
                         a_holding_unit(f"{unit} — this machine's sound server",
                                        execstart=f"/usr/bin/{unit.split('.')[0]}"))
        self.assertEqual(held_units(self.root), [])
        self.assertEqual(apply_holdoff(self.root).returncode, 0)
        for unit in ("pulseaudio.service", "pipewire.service",
                     "wireplumber.service"):
            self.assertTrue(
                (self.root / "etc/systemd/user/default.target.wants"
                 / unit).is_symlink(), unit)

    def test_a_unit_that_is_installed_but_not_enabled_is_left_alone(self):
        """Only an *enabled* unit runs at login, and only that is the defect."""
        install_unit(self.root, "midi-render-daemon.service",
                     a_holding_unit("Present but not wanted by any target"),
                     enable=False)
        self.assertEqual(held_units(self.root), [])

    def test_a_vendor_enabled_unit_is_overridden_where_dpkg_cannot_undo_it(self):
        install_unit(self.root, "midi-render-daemon.service",
                     a_holding_unit("Enabled by a link the package owns"),
                     enable=False)
        vendor = self.root / "usr/lib/systemd/user/default.target.wants"
        vendor.mkdir(parents=True)
        (vendor / "midi-render-daemon.service").symlink_to(
            "/usr/lib/systemd/user/midi-render-daemon.service")
        self.assertEqual(held_units(self.root), ["midi-render-daemon.service"])
        self.assertEqual(apply_holdoff(self.root).returncode, 0)
        self.assertEqual(held_units(self.root), [])
        override = self.root / "etc/systemd/user/midi-render-daemon.service"
        self.assertEqual(os.readlink(override), "/dev/null")


    def the_login_targets(self, root):
        """default.target and basic.target as systemd ships them."""
        units = root / "usr/lib/systemd/user"
        (units / "default.target").write_text(
            "[Unit]\nDescription=Main User Target\nRequires=basic.target\n"
            "After=basic.target\nAllowIsolate=yes\n")
        (units / "basic.target").write_text(
            "[Unit]\nDescription=Basic System\n"
            "Wants=sockets.target timers.target paths.target\n")
        for name in ("sockets.target", "timers.target", "paths.target"):
            (units / name).write_text(f"[Unit]\nDescription={name}\n")

    def test_what_the_login_target_pulls_in_is_caught_however_it_does(self):
        """A link is not the only thing that starts a unit at login.

        Each shape below was checked against `systemd-analyze --user verify
        default.target` on systemd 257, which puts a start job on the daemon
        for every one of them — and each gave "no login audio daemon" before
        the walk from the login target existed. The helper is the realistic
        one: a package that splits an innocent helper from its daemon.
        """
        unit = "midi-render-daemon.service"
        wants = f"[Unit]\nWants={unit}\n"

        def dropin_on(directory):
            def plant(root):
                path = root / "etc/systemd/user" / directory / "50-midi.conf"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(wants)
            return plant

        def override_default(root):
            (root / "etc/systemd/user/default.target").write_text(
                "[Unit]\nDescription=Main User Target\nRequires=basic.target\n"
                f"Wants={unit}\n")

        def alias_default(root):
            etc = root / "etc/systemd/user"
            (etc / "mylogin.target").write_text(
                "[Unit]\nDescription=My login target\nRequires=basic.target\n")
            (etc / "default.target").symlink_to("mylogin.target")
            dropin_on("mylogin.target.d")(root)

        def helper(root):
            install_unit(root, "midi-helper.service", f"""[Unit]
Description=An innocent helper that wants the daemon
Wants={unit}
[Service]
ExecStart=/bin/true
[Install]
WantedBy=default.target
""")

        shapes = {
            "drop-in on default.target": dropin_on("default.target.d"),
            "drop-in on basic.target": dropin_on("basic.target.d"),
            "type-level target.d drop-in": dropin_on("target.d"),
            "full default.target override in /etc": override_default,
            "default.target aliased to a target with a drop-in": alias_default,
            "enabled helper that Wants= the daemon": helper,
        }
        for shape, plant in shapes.items():
            with self.subTest(shape=shape):
                root = make_root(self.enterContext(
                    tempfile.TemporaryDirectory()))
                self.the_login_targets(root)
                install_unit(root, unit,
                             a_holding_unit(f"Started by: {shape}"),
                             enable=False)
                self.assertEqual(held_units(root), [],
                                 "the fixture holds the card before the shape "
                                 "is planted, so it proves nothing")
                plant(root)
                self.assertEqual(held_units(root), [unit])
                result = apply_holdoff(root)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(held_units(root), [])
                # Neither a link nor ours to edit: the daemon itself is
                # masked, and whatever pulled it in is left as it was.
                self.assertTrue(unit_is_masked(root, unit))
                if shape.startswith("enabled helper"):
                    self.assertTrue(
                        (root / "etc/systemd/user/default.target.wants"
                         / "midi-helper.service").is_symlink(),
                        "the innocent helper was disabled instead of the "
                        "daemon it pulls in")

    def test_a_link_is_read_by_its_name_as_systemd_reads_it(self):
        """systemd uses a `.wants/` link's NAME, not the file it points at.

        A link written with a build-root prefix dangles inside the image, and
        one aimed at the wrong file still starts the unit its name resolves
        to — systemd 257 says so itself ("has different name") and loads the
        named unit from the search path.
        """
        unit = "midi-render-daemon.service"
        for shape, target in (("dangling", "/usr/lib/systemd/user/no-such.service"),
                              ("misnamed", "/usr/lib/systemd/user/notes-sync.service")):
            with self.subTest(shape=shape):
                root = make_root(self.enterContext(
                    tempfile.TemporaryDirectory()))
                install_unit(root, unit, a_holding_unit(f"Reached by a {shape} link"),
                             enable=False)
                install_unit(root, "notes-sync.service",
                             "[Unit]\nDescription=Innocent\n[Service]\n"
                             "ExecStart=/bin/true\n", enable=False)
                link = root / "etc/systemd/user/default.target.wants" / unit
                link.symlink_to(target)
                self.assertEqual(held_units(root), [unit])
                self.assertEqual(apply_holdoff(root).returncode, 0)
                self.assertEqual(held_units(root), [])
                self.assertFalse(link.is_symlink())

    def test_signal_one_reads_what_systemd_reads(self):
        """Upholds= is a wanting verb; blanks around `=` are still the key."""
        for shape, line in (("Upholds=", "Upholds=pipewire.service"),
                            ("blanks around =", "Wants = pipewire.service")):
            with self.subTest(shape=shape):
                root = make_root(self.enterContext(
                    tempfile.TemporaryDirectory()))
                install_unit(root, "midi-render-daemon.service", f"""[Unit]
Description=Declares the sound stack as {shape}
{line}
[Service]
ExecStart=/bin/true
[Install]
WantedBy=default.target
""")
                self.assertEqual(held_units(root), ["midi-render-daemon.service"])

    def test_an_execstart_set_by_a_dropin_is_what_is_checked(self):
        """A placeholder fragment and a drop-in that sets the real program."""
        donor = an_audio_client_program()
        if donor is None:
            self.skipTest("no program on this machine links an audio client "
                          "library, so the linkage signal cannot be exercised "
                          "here")
        program = self.root / "usr/lib/systemd/quiet-audio-client"
        program.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(donor, program)
        program.chmod(0o755)
        install_unit(self.root, "quiet-audio-client.service", """[Unit]
Description=Placeholder fragment; the drop-in says what really runs
[Service]
ExecStart=/bin/true
[Install]
WantedBy=default.target
""")
        self.assertEqual(held_units(self.root), [])
        dropin = self.root / "etc/systemd/user/quiet-audio-client.service.d/override.conf"
        dropin.parent.mkdir(parents=True)
        dropin.write_text("[Service]\nExecStart=\n"
                          "ExecStart = /usr/lib/systemd/quiet-audio-client\n")
        self.assertEqual(held_units(self.root), ["quiet-audio-client.service"])
        self.assertEqual(apply_holdoff(self.root).returncode, 0)
        self.assertEqual(held_units(self.root), [])

    def test_a_mask_is_never_written_over_what_is_already_there(self):
        """An administrator's own unit file is not ours to replace.

        A drop-in pulls in `midi.service`, and the only `midi.service` is one
        someone wrote by hand in /etc. `ln -sf /dev/null` there destroyed it
        with no backup. The hold-off must refuse, say so, record it, and fail
        — the card is still held, and pretending otherwise would be worse —
        leaving what was there byte for byte as it was. A link in the same
        place (an alias, or `systemctl link`) is somebody's too.
        """
        admin_unit = (b"[Unit]\nDescription=My own synth\n"
                      b"Wants=pipewire.service\n[Service]\n"
                      b"ExecStart=/usr/bin/fluidsynth -is /srv/my.sf2\n"
                      b"# hand-written, not packaged\n")

        def regular_file(etc):
            (etc / "midi.service").write_bytes(admin_unit)
            return "midi.service"

        def systemctl_link(etc):
            (etc / "midi-alias.service").symlink_to(
                "/usr/lib/systemd/user/midi-render-daemon.service")
            return "midi-alias.service"

        def snapshot(path):
            return os.readlink(path) if path.is_symlink() else path.read_bytes()

        for case, plant in (("a regular file", regular_file),
                            ("a systemctl link", systemctl_link)):
            with self.subTest(already_there=case):
                root = make_root(self.enterContext(
                    tempfile.TemporaryDirectory()))
                etc = root / "etc/systemd/user"
                install_unit(root, "midi-render-daemon.service",
                             a_holding_unit("The unit a systemctl link names"),
                             enable=False)
                unit = plant(etc)
                before = snapshot(etc / unit)
                dropin = etc / "default.target.d/50-midi.conf"
                dropin.parent.mkdir(parents=True)
                dropin.write_text(f"[Unit]\nWants={unit}\n")
                self.assertEqual(held_units(root), [unit])

                result = apply_holdoff(root)
                self.assertNotEqual(result.returncode, 0,
                                    "the card is still held; the hold-off "
                                    "must not report success")
                self.assertIn("will NOT mask", result.stderr)
                self.assertEqual(snapshot(etc / unit), before,
                                 f"{case} at /etc/systemd/user/{unit} was "
                                 "changed by the hold-off")
                self.assertIn("\trefused", (root / "var/lib/plebian-os/"
                                            "audio-holdoff.log").read_text())

class DeliberateEnablementTests(unittest.TestCase):
    """Someone enabled it on purpose. That is not the same as a package did."""

    def setUp(self):
        self.root = make_root(self.enterContext(
            tempfile.TemporaryDirectory()))
        self.record = self.root / "var/lib/plebian-os/audio-holdoff.log"

    def enable_as_a_package_would(self, unit, target="default.target",
                                  kind="wants"):
        """The state file deb-systemd-helper writes beside every link it makes."""
        state = (self.root / "var/lib/systemd/deb-systemd-user-helper-enabled"
                 / f"{target}.{kind}" / unit)
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(f"/usr/lib/systemd/user/{unit}\n")

    def test_a_machine_wide_choice_nobody_packaged_is_removed_but_never_silently(self):
        """Decided, and made visible: removed, warned about, and recorded.

        The image promises voice capture works out of the box, and its own
        acceptance check fails the image while the card is held, so leaving a
        deliberate enablement in place is not available. What is available is
        refusing to do it quietly: say whose choice it was, say where the
        record is, and say where the same choice can be kept instead.
        """
        install_unit(self.root, "midi-render-daemon.service",
                     a_holding_unit("Enabled by hand, machine-wide"))
        result = apply_holdoff(self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("on purpose", result.stderr)
        self.assertIn("systemctl --user enable midi-render-daemon.service",
                      result.stderr)
        self.assertEqual(held_units(self.root), [])
        record = self.record.read_text()
        self.assertIn("deliberate", record)
        self.assertIn("midi-render-daemon.service", record)

    def test_a_package_created_enablement_is_removed_without_the_warning(self):
        """A vendor default is not a choice, and must not read like one."""
        install_unit(self.root, "midi-render-daemon.service",
                     a_holding_unit("Enabled by the package's own postinst"))
        self.enable_as_a_package_would("midi-render-daemon.service")
        result = apply_holdoff(self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("on purpose", result.stderr)
        self.assertEqual(held_units(self.root), [])
        self.assertIn("package", self.record.read_text())

    def test_a_per_account_choice_is_not_touched_at_all(self):
        """`systemctl --user enable` writes where provisioning never looks.

        This is the boundary that makes the branch above narrow enough to be
        defensible: a person's own account keeps whatever they enabled, and
        the only choice the provisioner ever overrides is a machine-wide one.
        """
        home = self.root / "home/someone/.config/systemd/user"
        install_unit(self.root, "midi-render-daemon.service",
                     a_holding_unit("Enabled for one account only"),
                     enable=False)
        link = home / "default.target.wants/midi-render-daemon.service"
        link.parent.mkdir(parents=True)
        link.symlink_to("/usr/lib/systemd/user/midi-render-daemon.service")
        self.assertEqual(held_units(self.root), [])
        self.assertEqual(apply_holdoff(self.root).returncode, 0)
        self.assertTrue(link.is_symlink(),
                        "a per-account enablement was removed by provisioning")


    def test_a_link_no_package_writes_is_masked_but_never_silently(self):
        """/run and /usr/local are not where dpkg puts links."""
        for directory, announced in (("usr/local/lib/systemd/user", True),
                                     ("run/systemd/user", True),
                                     ("usr/lib/systemd/user", False)):
            with self.subTest(link_directory=directory):
                root = make_root(self.enterContext(
                    tempfile.TemporaryDirectory()))
                install_unit(root, "midi-render-daemon.service",
                             a_holding_unit(f"Enabled under /{directory}"),
                             link_dir=directory)
                result = apply_holdoff(root)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(held_units(root), [])
                self.assertEqual("not where a" in result.stderr, announced,
                                 result.stderr)


class InstallPathAudioHoldoffTests(unittest.TestCase):
    """The install path, modelled from this machine's real package contents."""

    def setUp(self):
        self.tmp = self.enterContext(
            tempfile.TemporaryDirectory())

    def test_the_model_reads_every_install_spelling_a_postinst_acts_on(self):
        """The test's own model of dpkg must not be narrower than dpkg is.

        This is the one place the suite restates someone else's behaviour, so
        it is asserted directly rather than trusted: the arm below builds its
        whole image through it, and a model blind to a spelling would hand
        that arm an image with the defect quietly left out.
        """
        for kind, key in sorted(INSTALL_KEYS.items()):
            with self.subTest(install_key=key):
                self.assertEqual(
                    enablement_of(a_holding_unit("x", install=f"{key}=some.target")),
                    ("some.target", kind))
        self.assertIsNone(
            enablement_of("[Unit]\n[Service]\nExecStart=/bin/true\n"),
            "a unit with no [Install] section is not enabled by installing it")

    def test_the_install_path_leaves_nothing_holding_the_default_sound_card(self):
        named = install_path_packages()
        resolved = resolve_install_path(named)
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
        install_unit(control, "midi-render-daemon.service",
                     a_holding_unit("Control — a login daemon that holds the "
                                    "default sound card"))
        self.assertIn("midi-render-daemon.service", held_units(control),
                      "the rule failed to see a planted login audio daemon, "
                      "so its verdict on the real image means nothing")

        # The pre-state, measured and asserted rather than printed. Without
        # this the arm cannot tell "the hold-off cleared the daemon" from "the
        # rule never saw the daemon", and a rule widened until it is blind to
        # the real defect passes. The oracle is independent of the rule, so
        # blinding the rule cannot also blind the precondition.
        never_asked = units_the_install_path_never_asked_for(resolved, named)
        before = held_units(root)
        with self.subTest(check="the rule sees what the oracle names"):
            if not never_asked:
                # Visible, not vacuous: on a runner with no unnamed audio
                # holder installed this half of the arm has nothing to bite
                # on, and the counts must say so rather than report a pass.
                self.skipTest(
                    "this machine's modelled image enables no unit from an "
                    "unnamed package that links an audio client library, so "
                    "a rule blinded to such a unit cannot be caught here; the "
                    "rest of the arm still runs")
            self.assertLessEqual(
                set(never_asked), set(before),
                f"the modelled image enables {never_asked} — units from "
                "packages this install path never names, whose programs link "
                "an audio client library — and the image's own rule reports "
                f"only {before} holding the card. That is a blind rule, not a "
                "clean image.")

        # The capability: after the image's own hold-off runs, nothing that
        # starts at login holds the card. Packages named by the install path
        # that this machine cannot resolve are reported, not assumed clean.
        self.assertEqual(apply_holdoff(root).returncode, 0)
        self.assertEqual(
            held_units(root), [],
            f"modelled from {len(resolved)} resolvable packages "
            f"({len(enabled)} enabled user units, {len(before)} holding the "
            "card before the hold-off)")
        # Re-measured on the filesystem, not taken from the rule's own report:
        # a rule that stopped seeing these units would report success here too.
        for unit in never_asked:
            self.assertTrue(
                unit_cannot_start_at_login(root, unit),
                f"{unit} still starts at login on the modelled image: "
                f"{enablement_links(root, unit)}")

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
    """That the rule is reached — on a real install, an update and an image."""

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

    def test_an_update_re_checks_the_card_after_everything_it_installs(self):
        """A remedy an update reverses is not a remedy.

        `plebian-os-update` installs packages at four sites — the OS dependency
        closure, the selected native runtime `.deb`, `pleb install` and the
        whole component update — and any of them can bring a package whose
        user unit Debian enables for every login. Provisioning-time-only would
        mean the first such update quietly undoes the fix and nothing notices
        until someone tries to dictate.
        """
        text = UPDATE.read_text()
        calls = [m.start() for m in
                 re.finditer(r"^[ \t]*reapply_audio_holdoff$", text,
                             flags=re.MULTILINE)]
        self.assertTrue(
            calls, "plebian-os-update installs packages and never re-checks "
                   "whether one of them took the default sound card")
        for site in ('\nrefresh_os_dependencies\n',
                     '\napply_selected_native_runtime "$_STACK_TXN_DIR"',
                     '"$PLEB_DIR/bin/pleb" install\n',
                     '"$PLEB_DIR/bin/pleb" update --no-restart\n'):
            with self.subTest(install_site=site.strip()):
                position = text.rindex(site)
                self.assertTrue(
                    any(call > position for call in calls),
                    "the update's hold-off must run after every step that can "
                    f"install a package; it does not run after {site.strip()}")

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
        install_unit(dirty, "midi-render-daemon.service",
                     a_holding_unit("A login daemon holding the card"))
        # The shape that used to go green on a held card: same daemon, same
        # body, enabled the other way systemd and dpkg both honour.
        requires = make_root(tmp / "requires")
        install_unit(requires, "midi-render-daemon.service",
                     a_holding_unit("Enabled by RequiredBy=",
                                    install="RequiredBy=default.target"),
                     kind="requires")

        def run(script, root):
            env = clean_env(PLEBIAN_OS_AUDIO_HOLDOFF_ROOT=str(root))
            return subprocess.run(["bash", "-c", guest, "guest", str(script)],
                                  env=env, text=True, capture_output=True,
                                  check=False).returncode

        self.assertEqual(run(PROVISION, clean), 0)
        self.assertEqual(run(PROVISION, dirty), 1)
        self.assertEqual(
            run(PROVISION, requires), 1,
            "the acceptance check accepted an image whose card is held, "
            "because the daemon was enabled through RequiredBy= instead of "
            "WantedBy=")
        self.assertEqual(run(tmp / "absent.sh", clean), 2)


class UpdateReinstallTests(unittest.TestCase):
    """An update that reinstalls the player must still leave the card free."""

    def run_the_updates_holdoff_step(self, **env):
        """Run the updater's own step, out of the shipped updater itself.

        Sourced in the updater's existing library-only mode, so this is the
        real function with the real log/warn/die around it — not a fragment
        copied into the test, which could drift from what ships. `sudo` is
        replaced after the source because the step elevates when it is not
        already root, and a test must never reach for real privilege.
        """
        script = ('set -uo pipefail\n'
                  'export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n'
                  f'. "{UPDATE}"\n'
                  'sudo() { "$@"; }\n'
                  'reapply_audio_holdoff\n')
        return subprocess.run(["bash", "-c", script], cwd=ROOT,
                              env=clean_env(**env), text=True,
                              capture_output=True, check=False)

    def test_a_package_reinstalled_by_an_update_does_not_keep_the_card(self):
        """End to end, with the real deb-systemd-helper doing the enabling.

        This is the exposure F9 names: a package installed during an OS-layer
        update brings a user unit its postinst enables, and the hold-off ran
        only at provisioning time. The arm reproduces it with the machinery
        Debian actually uses — `deb-systemd-helper --user enable` against a
        DPKG_ROOT — and then runs the updater's own step over the result.
        """
        helper = shutil.which("deb-systemd-helper")
        if helper is None:
            self.skipTest("deb-systemd-helper is not installed here, so the "
                          "real enablement machinery cannot be exercised")
        root = make_root(self.enterContext(tempfile.TemporaryDirectory()))
        # The installed image carries the provisioner; self_update_os_layer has
        # already replaced it with the target release's copy by the time the
        # updater reaches this step, which is why the updater sources it
        # rather than carrying a second copy of the rule.
        installed = root / "usr/local/sbin/plebian-os-provision"
        installed.parent.mkdir(parents=True)
        shutil.copy2(PROVISION, installed)

        unit = "midi-render-daemon.service"
        install_unit(root, unit,
                     a_holding_unit("Reinstalled during an OS-layer update",
                                    install="RequiredBy=default.target"),
                     enable=False)
        enable = subprocess.run(
            [helper, "--user", "enable", unit],
            env=clean_env(DPKG_MAINTSCRIPT_PACKAGE="midi-render-daemon",
                          DPKG_ROOT=str(root)),
            text=True, capture_output=True, check=False)
        self.assertEqual(enable.returncode, 0, enable.stderr)
        self.assertEqual(held_units(root), [unit],
                         "the fixture did not reproduce the defect, so what "
                         "follows would prove nothing")

        result = self.run_the_updates_holdoff_step(
            PLEBIAN_OS_AUDIO_HOLDOFF_ROOT=str(root),
            PLEBIAN_OS_UPDATE_TEST_PROVISION_SCRIPT=str(installed))
        self.assertEqual(result.returncode, 0,
                         f"{result.stdout}\n{result.stderr}")
        self.assertEqual(held_units(root), [])
        self.assertTrue(unit_cannot_start_at_login(root, unit))

        # And it stays fixed: `was-enabled` is what the package's own postinst
        # asks on every later install, and it is now false.
        was_enabled = subprocess.run(
            [helper, "--quiet", "--user", "was-enabled", unit],
            env=clean_env(DPKG_MAINTSCRIPT_PACKAGE="midi-render-daemon",
                          DPKG_ROOT=str(root)),
            text=True, capture_output=True, check=False)
        self.assertEqual(was_enabled.returncode, 1,
                         "deb-systemd-helper still reports the unit as "
                         "enabled, so the next upgrade would re-enable it")

    def test_the_updates_step_fails_loudly_when_it_cannot_run(self):
        """A step that cannot run must never be mistaken for a clean card."""
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        result = self.run_the_updates_holdoff_step(
            PLEBIAN_OS_UPDATE_TEST_PROVISION_SCRIPT=str(tmp / "absent"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing or unsafe", result.stderr)

        # A symlink where the provisioner should be is refused for the same
        # reason the dependency helper refuses one: it is a redirection nobody
        # asked for, and this step runs as root.
        planted = tmp / "planted"
        planted.write_text("#!/bin/bash\n")
        link = tmp / "linked-provisioner"
        link.symlink_to(planted)
        result = self.run_the_updates_holdoff_step(
            PLEBIAN_OS_UPDATE_TEST_PROVISION_SCRIPT=str(link))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing or unsafe", result.stderr)


    # -- the provisioner a shipped machine actually has -------------------------

    def a_provisioner_from_before_the_holdoff(self, directory, library_only=True):
        """The shape of every provisioner released before this hold-off.

        Every v0.1.x, v0.2.0 and v0.2.1 provisioner lacks
        disable_audio_holding_user_units, and v0.1.0's has no library-only
        return either — sourcing that one would run a full provisioning pass.
        The marker proves whether the step sourced it at all.
        """
        directory.mkdir(parents=True, exist_ok=True)
        marker = directory / "sourced"
        body = ["#!/usr/bin/env bash", "set -euo pipefail",
                f": > '{marker}'",
                'log() { printf "%s\\n" "$*"; }']
        if library_only:
            body += ['if [ "${PLEBIAN_OS_PROVISION_LIB_ONLY:-0}" = 1 ]; then',
                     "    return 0 2>/dev/null || exit 0", "fi"]
        body += [f": > '{directory / 'provisioned'}'"]
        script = directory / "plebian-os-provision"
        script.write_text("\n".join(body) + "\n")
        script.chmod(0o755)
        return script, marker

    def test_an_update_without_self_update_on_a_shipped_machine_is_not_failed(self):
        """PLEBIAN_OS_SELF_UPDATE=0 is documented, and shipped machines lack the rule.

        With self-update disabled the installed provisioner is whatever the
        machine already had. Calling a function it does not define used to
        fail every such update at its last step — and report a held card that
        nobody had measured. The step must say, truthfully, that it did not
        re-check, and let the update finish.
        """
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        cases = {}
        script, marker = self.a_provisioner_from_before_the_holdoff(
            tmp / "no-function")
        cases["no hold-off function"] = (script, marker)
        script, marker = self.a_provisioner_from_before_the_holdoff(
            tmp / "no-lib-only", library_only=False)
        cases["no library-only mode either (v0.1.0)"] = (script, marker)
        # Text that looks like the rule but never defines it: only
        # `declare -F`, after sourcing, can tell.
        script, marker = self.a_provisioner_from_before_the_holdoff(tmp / "text-only")
        script.write_text(script.read_text().replace(
            "fi\n", "fi\nif false; then\ndisable_audio_holding_user_units() {\n"
            "    :\n}\nfi\n", 1))
        cases["the rule's text, never defined"] = (script, marker)
        released = subprocess.run(
            ["git", "-C", str(ROOT), "show",
             "v0.2.1:provision/plebian-os-provision.sh"],
            capture_output=True, check=False)
        if released.returncode == 0:
            (tmp / "v0.2.1").mkdir()
            script = tmp / "v0.2.1/plebian-os-provision"
            script.write_bytes(released.stdout)
            script.chmod(0o755)
            cases["the released v0.2.1 provisioner"] = (script, None)

        for case, (script, marker) in cases.items():
            with self.subTest(installed=case, self_update="0"):
                result = self.run_the_updates_holdoff_step(
                    PLEBIAN_OS_SELF_UPDATE="0",
                    PLEBIAN_OS_AUDIO_HOLDOFF_ROOT=str(tmp / "no-root"),
                    PLEBIAN_OS_UPDATE_TEST_PROVISION_SCRIPT=str(script))
                self.assertEqual(result.returncode, 0,
                                 f"{result.stdout}\n{result.stderr}")
                self.assertIn("did NOT check", result.stderr)
                self.assertNotIn("still holds", result.stderr + result.stdout)
                self.assertNotIn("command not found", result.stderr)
                if case.startswith("no library-only"):
                    self.assertFalse(marker.exists(),
                                     "a provisioner with no library-only mode "
                                     "was sourced, which runs it for real")
                if case.startswith("the rule's text"):
                    self.assertTrue(marker.exists(), "never sourced, so "
                                    "`declare -F` was never what decided")
            with self.subTest(installed=case, self_update="1"):
                # With self-update on, the file was just deployed by this very
                # release; lacking the rule means the OS layer is not ours.
                result = self.run_the_updates_holdoff_step(
                    PLEBIAN_OS_SELF_UPDATE="1",
                    PLEBIAN_OS_UPDATE_TEST_PROVISION_SCRIPT=str(script))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("does not carry the audio hold-off", result.stderr)
                self.assertNotIn("still holds", result.stderr + result.stdout)
        if released.returncode != 0:
            with self.subTest(installed="the released v0.2.1 provisioner"):
                self.skipTest("no v0.2.1 tag in this checkout, so the released "
                              "provisioner itself was not exercised; the "
                              "constructed shapes above were")

    def test_the_updates_step_fails_when_the_rule_it_runs_fails(self):
        """A step whose rule fails must fail the update, not be swallowed.

        Driven through the real rule: a drop-in pulls in a unit someone wrote
        by hand in /etc, which the hold-off refuses to mask over, so the card
        is still held and the provisioner's own re-measure dies.
        """
        root = make_root(self.enterContext(tempfile.TemporaryDirectory()))
        installed = root / "usr/local/sbin/plebian-os-provision"
        installed.parent.mkdir(parents=True)
        shutil.copy2(PROVISION, installed)
        etc = root / "etc/systemd/user"
        (etc / "midi.service").write_text(
            "[Unit]\nWants=pipewire.service\n[Service]\nExecStart=/bin/true\n")
        (etc / "default.target.d").mkdir()
        (etc / "default.target.d/50-midi.conf").write_text(
            "[Unit]\nWants=midi.service\n")
        result = self.run_the_updates_holdoff_step(
            PLEBIAN_OS_AUDIO_HOLDOFF_ROOT=str(root),
            PLEBIAN_OS_UPDATE_TEST_PROVISION_SCRIPT=str(installed))
        self.assertNotEqual(result.returncode, 0,
                            f"{result.stdout}\n{result.stderr}")
        self.assertIn("did not complete", result.stderr)
        self.assertIn("will NOT mask", result.stderr)
        self.assertEqual((etc / "midi.service").read_text(),
                         "[Unit]\nWants=pipewire.service\n[Service]\n"
                         "ExecStart=/bin/true\n")

    def test_the_test_seam_is_ignored_outside_a_test(self):
        """The provisioner override exists for the suite, and only for it.

        The step sources that file as root. Outside the updater's library-only
        test mode the variable must not select anything: the default path is
        the one self_update_os_layer deploys. `sudo` here only records what it
        was asked to run; it never runs it.
        """
        if os.geteuid() == 0:
            self.skipTest("running as root, where the step would not go "
                          "through the recording sudo")
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        payload = tmp / "payload.sh"
        ran = tmp / "payload-ran"
        payload.write_text(f"#!/bin/bash\n: > '{ran}'\n"
                           "disable_audio_holding_user_units() { :; }\n"
                           'if [ "${PLEBIAN_OS_PROVISION_LIB_ONLY:-0}" = 1 ]; then\n'
                           "    return 0\nfi\n")
        payload.chmod(0o755)
        argv = tmp / "sudo-argv"
        script = ('set -uo pipefail\n'
                  'export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n'
                  f'. "{UPDATE}"\n'
                  'unset PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY\n'
                  f'sudo() {{ printf "%s\\n" "$@" >> "{argv}"; return 0; }}\n'
                  'reapply_audio_holdoff\n')
        result = subprocess.run(
            ["bash", "-c", script], cwd=ROOT,
            env=clean_env(PLEBIAN_OS_UPDATE_TEST_PROVISION_SCRIPT=str(payload),
                          PLEBIAN_OS_SELF_UPDATE="0",
                          PLEBIAN_OS_AUDIO_HOLDOFF_ROOT=str(tmp / "no-root")),
            text=True, capture_output=True, check=False)
        asked = argv.read_text() if argv.exists() else ""
        self.assertFalse(ran.exists(), "the override was sourced outside a test")
        self.assertNotIn(str(payload), asked + result.stderr + result.stdout)
        # Whatever this machine has installed, the step used — or refused, or
        # reported on — the default path, and nothing else.
        self.assertIn("/usr/local/sbin/plebian-os-provision",
                      asked + result.stderr + result.stdout,
                      f"{result.stdout}\n{result.stderr}")

    def test_a_provisioner_others_can_write_is_refused(self):
        """Sourced as root, so group- or world-writable is not safe."""
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        installed = tmp / "plebian-os-provision"
        shutil.copy2(PROVISION, installed)
        installed.chmod(0o775)
        result = self.run_the_updates_holdoff_step(
            PLEBIAN_OS_AUDIO_HOLDOFF_ROOT=str(tmp),
            PLEBIAN_OS_UPDATE_TEST_PROVISION_SCRIPT=str(installed))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing or unsafe", result.stderr)

    def test_no_update_writes_a_provisioning_banner(self):
        """Sourcing the provisioner is not provisioning, and the log must not say it is.

        Two guards, each with its own arm: the current provisioner skips its
        log in library-only mode, and the step marks the log already active so
        that an OLDER installed provisioner, which lacks that skip, does not
        write a false "plebian-os-provision starting" banner either.
        """
        root = make_root(self.enterContext(tempfile.TemporaryDirectory()))
        log_path = root / "provision.log"
        current = root / "current-provision"
        shutil.copy2(PROVISION, current)
        older = root / "older-provision"
        text = PROVISION.read_text()
        skip = '    && [ "${PLEBIAN_OS_PROVISION_LIB_ONLY:-0}" != 1 ] \\\n'
        self.assertIn(skip, text)
        older.write_text(text.replace(skip, "", 1))
        older.chmod(0o755)
        with self.subTest(guard="library-only mode skips the log"):
            result = provision_call(":", root,
                                    env=clean_env(PLEBIAN_OS_PROVISION_LOG=str(log_path)))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(log_path.exists() and "starting" in log_path.read_text(),
                             "sourcing the library wrote a provisioning banner")
        with self.subTest(guard="the step marks the log active"):
            result = self.run_the_updates_holdoff_step(
                PLEBIAN_OS_AUDIO_HOLDOFF_ROOT=str(root),
                PLEBIAN_OS_PROVISION_LOG=str(log_path),
                PLEBIAN_OS_UPDATE_TEST_PROVISION_SCRIPT=str(older))
            self.assertEqual(result.returncode, 0,
                             f"{result.stdout}\n{result.stderr}")
            self.assertFalse(log_path.exists() and "starting" in log_path.read_text(),
                             "an update wrote a false provisioning banner")
        # Control: the older shape really does write one when nothing stops it.
        control = subprocess.run(
            ["bash", "-c", f'export PLEBIAN_OS_PROVISION_LIB_ONLY=1; . "{older}" >/dev/null 2>&1'],
            env=clean_env(PLEBIAN_OS_PROVISION_LOG=str(log_path)),
            text=True, capture_output=True, check=False)
        self.assertEqual(control.returncode, 0, control.stderr)
        self.assertIn("plebian-os-provision starting", log_path.read_text(),
                      "the older-provisioner fixture writes no banner, so the "
                      "arm above proves nothing")


if __name__ == "__main__":
    unittest.main()
