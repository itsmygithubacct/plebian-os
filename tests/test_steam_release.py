import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROVISION = ROOT / "provision"
PROVISIONER = PROVISION / "plebian-os-provision.sh"
SETUP = PROVISION / "plebian-os-steam-setup"
CLOSURE = PROVISION / "steam-closure.env"
CLOSURE_PIN = PROVISION / "steam-closure.sha256"
SOURCE = PROVISION / "steam-source.sources"
PIN = PROVISION / "steam-pin.pref"
MANIFEST = PROVISION / "policy-v1.manifest"


def values(path: Path) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith("#"):
            continue
        key, value = raw.split("=", 1)
        if key in parsed:
            raise AssertionError(f"duplicate key: {key}")
        parsed[key] = value
    return parsed


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SteamReleaseTests(unittest.TestCase):
    def test_policy_observation_is_exact_but_deliberately_unqualified(self):
        closure = values(CLOSURE)
        manifest = values(MANIFEST)
        self.assertEqual(CLOSURE_PIN.read_text(encoding="ascii"), digest(CLOSURE) + "\n")
        self.assertEqual(closure["STEAM_CLOSURE_QUALIFIED"], "0")
        self.assertEqual(closure["STEAM_BASE_SNAPSHOT"], "20260727T000000Z")
        self.assertEqual(
            closure["STEAM_ARCHIVE_URI"],
            "https://repo.steampowered.com/steam/",
        )
        self.assertEqual(closure["STEAM_ARCHIVE_SUITE"], "stable")
        self.assertEqual(closure["STEAM_ARCHIVE_COMPONENT"], "steam")
        self.assertEqual(closure["STEAM_SOURCE_SHA256"], digest(SOURCE))
        self.assertEqual(closure["STEAM_PIN_SHA256"], digest(PIN))
        self.assertEqual(
            manifest["authorization_schema"],
            "kilix.install.authorization/v2",
        )
        self.assertEqual(
            manifest["packages"],
            "steam-launcher,steam-libs-amd64:amd64,steam-libs-i386:i386",
        )
        self.assertEqual(manifest["archive_policy_sha256"], digest(SOURCE))
        self.assertEqual(manifest["pin_policy_sha256"], digest(PIN))

    def test_source_key_and_pin_scope_are_fixed(self):
        source = SOURCE.read_text(encoding="utf-8")
        pin = PIN.read_text(encoding="utf-8")
        closure = values(CLOSURE)
        self.assertIn("Types: deb\n", source)
        self.assertNotIn("deb-src", source)
        self.assertIn("Architectures: amd64 i386", source)
        self.assertIn("Signed-By: /usr/share/keyrings/steam.gpg", source)
        self.assertIn("Package: *\n", pin)
        self.assertIn("Pin-Priority: -1", pin)
        self.assertIn(
            "Package: steam-launcher steam-libs-amd64 steam-libs-i386\n",
            pin,
        )
        self.assertNotIn("steam-libs-i386 steam\n", pin)
        self.assertRegex(closure["STEAM_KEY_SHA256"], r"^[0-9a-f]{64}$")
        fingerprints = closure["STEAM_KEY_FINGERPRINTS"].split(",")
        self.assertEqual(len(fingerprints), 2)
        self.assertTrue(all(len(item) == 40 for item in fingerprints))

    def test_helper_exposes_only_three_fixed_action_modes(self):
        text = SETUP.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/bin/bash\n"))
        self.assertIn("--install) MODE=install", text)
        self.assertIn("--repair) MODE=repair", text)
        self.assertIn("--verify) MODE=verify", text)
        self.assertNotRegex(text, r"(?m)^[ \t]*sudo(?:[ \t]|$)")
        self.assertNotIn("apt-key", text)
        self.assertNotIn("eval ", text)
        self.assertIn("--no-install-recommends", text)
        self.assertIn("Acquire::AllowInsecureRepositories=false", text)
        self.assertIn("root_steam_processes_absent", text)
        self.assertIn("done < <(compgen -e)", text)
        self.assertIn("export PATH HOME USER LOGNAME LANG LC_ALL TZ", text)

    def test_provisioning_installs_policy_but_never_invokes_the_helper(self):
        provision = PROVISIONER.read_text(encoding="utf-8")
        self.assertIn("/usr/libexec/plebian-os-steam-setup", provision)
        for name in (
            "steam-closure.env",
            "steam-closure.sha256",
            "steam-source.sources",
            "steam-pin.pref",
            "policy-v1.manifest",
        ):
            self.assertIn(name, provision)
        self.assertIn("Provisioning never invokes it", provision)
        self.assertNotRegex(
            provision,
            r"plebian-os-steam-setup[\"']?\s+--(?:install|repair)",
        )

    def test_provisioning_builds_the_client_from_one_fixed_published_tree(self):
        provision = PROVISIONER.read_text(encoding="utf-8")
        self.assertIn(
            "KILIX_VALVE_CLIENT_REPO="
            "https://github.com/itsmygithubacct/kilix-game-sdk.git",
            provision,
        )
        self.assertIn(
            "KILIX_VALVE_CLIENT_REMOTE_REF=refs/heads/work/0.2.1-steam",
            provision,
        )
        self.assertIn(
            "KILIX_VALVE_CLIENT_COMMIT="
            "14c8bfbd6e91e05df0bb593a51fc8a8174445e13",
            provision,
        )
        self.assertIn(
            "KILIX_VALVE_CLIENT_TREE="
            "3d800e41d028104adbf5d096bdf7c40b781a982a",
            provision,
        )
        self.assertIn(
            "KILIX_VALVE_CLIENT_TARGET=/usr/bin/kilix-valve-client",
            provision,
        )
        self.assertIn("install_kilix_valve_client", provision)
        self.assertIn(
            '[ "$commit" = "$KILIX_VALVE_CLIENT_COMMIT" ]', provision
        )
        self.assertIn('[ "$tree" = "$KILIX_VALVE_CLIENT_TREE" ]', provision)
        self.assertIn(
            '"$candidate" "$KILIX_VALVE_CLIENT_TARGET"', provision
        )
        self.assertNotIn(
            'KILIX_VALVE_CLIENT_REPO="${KILIX_VALVE_CLIENT_REPO', provision
        )

    def test_fixed_client_build_installs_exact_runtime_metadata(self):
        temporary = Path(tempfile.mkdtemp(prefix="valve-client-package-"))
        self.addCleanup(shutil.rmtree, temporary, True)
        source = temporary / "source"
        component = source / "kilix-valve-client"
        component.mkdir(parents=True)
        (component / "LICENSE").write_text("fixture license\n", encoding="utf-8")
        (component / "VERSION").write_text("0.1.0\n", encoding="ascii")
        client = component / "client"
        client.write_text(
            "#!/bin/sh\n"
            "[ \"${1:-}\" = --help ] || exit 64\n"
            "printf 'fixed client help\\n'\n",
            encoding="utf-8",
        )
        client.chmod(0o755)
        (component / "Makefile").write_text(
            "all:\n"
            "\tmkdir -p build\n"
            "\tcp client build/kilix-valve-client\n"
            "\tchmod 0755 build/kilix-valve-client\n"
            "clean:\n"
            "\trm -rf build\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q", "-b", "main", str(source)], check=True)
        subprocess.run(
            ["git", "-C", str(source), "config", "user.name", "itsmygithubacct"],
            check=True,
        )
        subprocess.run(
            [
                "git", "-C", str(source), "config", "user.email",
                "itsmygithubacct@users.noreply.github.com",
            ],
            check=True,
        )
        subprocess.run(["git", "-C", str(source), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(source), "commit", "-q", "-m", "fixture"],
            check=True,
        )
        commit = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
        ).strip()
        tree = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD^{tree}"], text=True
        ).strip()

        build_base = temporary / "build-base"
        target = temporary / "root/usr/bin/kilix-valve-client"
        license_target = temporary / "root/usr/share/doc/client/copyright"
        version_target = temporary / "root/usr/share/doc/client/VERSION"
        build_base.mkdir()
        script = r'''
set -euo pipefail
PLEBIAN_OS_PROVISION_LIB_ONLY=1 source "$1"
KILIX_VALVE_CLIENT_REPO="$2"
KILIX_VALVE_CLIENT_REMOTE_REF=refs/heads/main
KILIX_VALVE_CLIENT_COMMIT="$3"
KILIX_VALVE_CLIENT_TREE="$4"
KILIX_VALVE_CLIENT_BUILD_BASE="$5"
KILIX_VALVE_CLIENT_BUILD_DIR=""
KILIX_VALVE_CLIENT_TARGET="$6"
KILIX_VALVE_CLIENT_LICENSE_TARGET="$7"
KILIX_VALVE_CLIENT_VERSION_TARGET="$8"
DRY_RUN=0
install_kilix_valve_client
'''
        completed = subprocess.run(
            [
                "bash", "-c", script, "bash", str(PROVISIONER), str(source),
                commit, tree, str(build_base), str(target), str(license_target),
                str(version_target),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("installed kilix-valve-client 0.1.0", completed.stdout)
        self.assertEqual(target.read_bytes(), client.read_bytes())
        self.assertEqual(license_target.read_text(), "fixture license\n")
        self.assertEqual(version_target.read_text(), "0.1.0\n")
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(license_target.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(version_target.stat().st_mode), 0o644)
        self.assertEqual(list(build_base.iterdir()), [])

    def test_license_and_archive_authorization_are_distinct_records(self):
        text = SETUP.read_text(encoding="utf-8")
        self.assertIn(
            "authorization_schema=kilix.install.authorization/v2", text
        )
        self.assertIn("license_schema=kilix.install.license/v1", text)
        self.assertIn("decisions_separate=1", text)
        self.assertIn("pre-mutation authorization-v2 mediator is unavailable", text)
        self.assertNotIn("TEST_LICENSE", text)

    def make_test_root(self, *, qualified: bool = True) -> Path:
        temporary = Path(tempfile.mkdtemp(prefix="steam-helper-"))
        temporary.chmod(0o700)
        policy = temporary / "policy"
        command_root = temporary / "test-bin"
        policy.mkdir(mode=0o700)
        command_root.mkdir(mode=0o700)
        shutil.copy2(SOURCE, policy / SOURCE.name)
        shutil.copy2(PIN, policy / PIN.name)
        closure_text = CLOSURE.read_text(encoding="utf-8")
        closure_text = closure_text.replace(
            "STEAM_CLOSURE_QUALIFIED=0",
            f"STEAM_CLOSURE_QUALIFIED={int(qualified)}",
        )
        fake_key = temporary / "fake-steam.gpg"
        fake_key.write_bytes(b"bounded fake Valve key fixture\n")
        closure_text = closure_text.replace(
            values(CLOSURE)["STEAM_KEY_SHA256"], digest(fake_key)
        )
        closure_text = closure_text.replace(
            values(CLOSURE)["STEAM_KEY_FINGERPRINTS"],
            "A" * 40 + "," + "B" * 40,
        )
        manifest_text = MANIFEST.read_text(encoding="utf-8").replace(
            values(CLOSURE)["STEAM_KEY_SHA256"], digest(fake_key)
        )
        (policy / MANIFEST.name).write_text(manifest_text, encoding="utf-8")
        closure_path = policy / CLOSURE.name
        closure_path.write_text(closure_text, encoding="utf-8")
        (policy / CLOSURE_PIN.name).write_text(
            digest(closure_path) + "\n", encoding="ascii"
        )
        self.write_fake_commands(temporary)
        return temporary

    @staticmethod
    def write_executable(path: Path, body: str) -> None:
        path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body,
                        encoding="utf-8")
        path.chmod(0o700)

    def write_fake_commands(self, root: Path) -> None:
        commands = root / "test-bin"
        self.write_executable(
            commands / "dpkg",
            r'''
state="$PLEBIAN_OS_STEAM_TEST_ROOT/test-state"
mkdir -p "$state"
case "${1:-}" in
  --print-architecture) printf 'amd64\n' ;;
  --print-foreign-architectures) [ ! -f "$state/i386" ] || printf 'i386\n' ;;
  --add-architecture) [ "${2:-}" = i386 ]; : >"$state/i386" ;;
  --remove-architecture) [ "${2:-}" = i386 ]; rm -f "$state/i386" ;;
  *) exit 64 ;;
esac
''',
        )
        self.write_executable(
            commands / "dpkg-query",
            r'''
state="$PLEBIAN_OS_STEAM_TEST_ROOT/test-state"
[ "${STEAM_TEST_DPKG_QUERY_FAIL:-0}" != 1 ] || exit 42
if [[ "$*" == *'${Architecture}'* ]]; then
  [ ! -f "$state/installed" ] || printf 'steam-libs-i386:i386\ti386\tii \n'
elif [ -f "$state/installed" ]; then
  case "$*" in
    *'${Version}'*) printf '1:1.0.0.87' ;;
    *) printf 'install ok installed' ;;
  esac
else
  exit 1
fi
''',
        )
        self.write_executable(
            commands / "apt-get",
            r'''
state="$PLEBIAN_OS_STEAM_TEST_ROOT/test-state"
mkdir -p "$state"
printf '%q ' "$@" >>"$state/apt.log"
printf '\n' >>"$state/apt.log"
for argument in "$@"; do
  if [ "$argument" = --print-uris ]; then
    [ "${STEAM_TEST_EMPTY_URI_PLAN:-0}" != 1 ] || exit 0
    scheme=${STEAM_TEST_URI_SCHEME:-https}
    printf "'%s://repo.steampowered.com/steam/pool/fixed.deb' fixed.deb 1024 SHA256:aa\n" "$scheme"
    exit 0
  fi
done
for argument in "$@"; do
  if [ "$argument" = update ]; then
    [ "${STEAM_TEST_APT_FAIL:-}" != update ] || exit 42
    exit 0
  fi
done
for argument in "$@"; do
  if [ "$argument" = install ]; then
    [ "${STEAM_TEST_APT_FAIL:-}" != install ] || exit 43
    : >"$state/installed"
    exit 0
  fi
done
exit 64
''',
        )
        self.write_executable(
            commands / "apt-cache",
            r'''
package=${!#}
architecture=amd64
case "$package" in *i386*) architecture=i386 ;; esac
printf '  Installed: 1:1.0.0.87\n'
printf '  Candidate: 1:1.0.0.87\n'
printf ' *** 1:1.0.0.87 500\n'
if [ "${STEAM_TEST_APT_PROVENANCE:-valve}" = valve ] \
    || { [ "${STEAM_TEST_APT_PROVENANCE:-valve}" = libs-other ] \
        && [ "$package" = steam-launcher ]; }; then
  printf '        500 https://repo.steampowered.com/steam/ stable/steam %s Packages\n' "$architecture"
else
  printf '        500 https://packages.example.invalid/ stable/main %s Packages\n' "$architecture"
fi
printf '        100 /var/lib/dpkg/status\n'
''',
        )
        self.write_executable(
            commands / "curl",
            r'''
output=
while [ "$#" -gt 0 ]; do
  if [ "$1" = --output ]; then output=$2; shift 2; else shift; fi
done
[ -n "$output" ]
cp "$PLEBIAN_OS_STEAM_TEST_ROOT/fake-steam.gpg" "$output"
''',
        )
        self.write_executable(
            commands / "gpg",
            "printf 'pub:-:2048:1:one:\\nfpr:::::::::%s:\\n' "
            "'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'\n"
            "printf 'pub:-:4096:1:two:\\nfpr:::::::::%s:\\n' "
            "'BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB'\n",
        )
        self.write_executable(
            commands / "timeout",
            r'''
while [ "$#" -gt 0 ]; do
  case "$1" in
    --signal=*|--kill-after=*) shift ;;
    [0-9]*) shift; break ;;
    *) exit 64 ;;
  esac
done
exec "$@"
''',
        )
        for command in ("sha256sum", "install", "flock", "sync"):
            self.write_executable(
                commands / command, f'exec /usr/bin/{command} "$@"\n'
            )

    @staticmethod
    def helper_environment(root: Path, *, authorized: bool = True) -> dict[str, str]:
        environment = {
            **os.environ,
            "PLEBIAN_OS_STEAM_TESTING": "1",
            "PLEBIAN_OS_STEAM_TEST_ROOT": str(root),
        }
        if authorized:
            environment["PLEBIAN_OS_STEAM_TEST_AUTHORIZATION_V2"] = (
                "kilix.install.authorization/v2:test-only"
            )
        else:
            environment.pop("PLEBIAN_OS_STEAM_TEST_AUTHORIZATION_V2", None)
        return environment

    def run_helper(
        self, root: Path, mode: str, *, authorized: bool = True,
        extra: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = self.helper_environment(root, authorized=authorized)
        if extra:
            environment.update(extra)
        return subprocess.run(
            [str(SETUP), mode],
            text=True,
            capture_output=True,
            env=environment,
            check=False,
        )

    def test_unqualified_closure_refuses_before_every_system_path(self):
        root = self.make_test_root(qualified=False)
        self.addCleanup(shutil.rmtree, root, True)
        result = self.run_helper(root, "--install")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("closure is unqualified", result.stderr)
        self.assertFalse((root / "etc").exists())
        self.assertFalse((root / "var/lib/plebian-os").exists())

    def test_missing_authorization_refuses_before_every_system_path(self):
        root = self.make_test_root()
        self.addCleanup(shutil.rmtree, root, True)
        result = self.run_helper(root, "--install", authorized=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pre-mutation authorization-v2 mediator", result.stderr)
        self.assertFalse((root / "etc").exists())
        self.assertFalse((root / "var/lib/plebian-os").exists())

    def test_private_fake_root_install_and_verify(self):
        root = self.make_test_root()
        self.addCleanup(shutil.rmtree, root, True)
        installed = self.run_helper(root, "--install")
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertEqual(
            (root / "etc/apt/sources.list.d/plebian-os-steam.sources").read_bytes(),
            SOURCE.read_bytes(),
        )
        self.assertEqual(
            (root / "etc/apt/preferences.d/plebian-os-steam.pref").read_bytes(),
            PIN.read_bytes(),
        )
        self.assertEqual(
            (root / "usr/share/keyrings/steam.gpg").read_bytes(),
            (root / "fake-steam.gpg").read_bytes(),
        )
        self.assertTrue((root / "test-state/i386").is_file())
        self.assertTrue((root / "test-state/installed").is_file())
        outcome = (root / "var/lib/plebian-os/steam/outcome").read_text()
        self.assertIn("state=VERIFIED\n", outcome)
        self.assertIn("authorization_schema=kilix.install.authorization/v2", outcome)
        self.assertIn("license_schema=kilix.install.license/v1", outcome)
        self.assertIn("decisions_separate=1", outcome)
        self.assertEqual(
            stat.S_IMODE((root / "var/lib/plebian-os/steam").stat().st_mode),
            0o755,
        )
        self.assertEqual(
            stat.S_IMODE((root / "var/lib/plebian-os/steam/outcome").stat().st_mode),
            0o644,
        )
        apt_log = (root / "test-state/apt.log").read_text()
        self.assertIn("--no-install-recommends", apt_log)
        self.assertIn("steam-launcher", apt_log)
        self.assertIn("steam-libs-i386:i386", apt_log)
        verified = self.run_helper(root, "--verify", authorized=False)
        self.assertEqual(verified.returncode, 0, verified.stderr)

    def test_verify_refuses_nonexact_or_unsafe_outcome_projection(self):
        root = self.make_test_root()
        self.addCleanup(shutil.rmtree, root, True)
        installed = self.run_helper(root, "--install")
        self.assertEqual(installed.returncode, 0, installed.stderr)
        outcome = root / "var/lib/plebian-os/steam/outcome"
        exact = outcome.read_bytes()

        outcome.write_bytes(exact.replace(
            b"authorization_schema=kilix.install.authorization/v2",
            b"authorization_schema=kilix.install.license/v1",
        ))
        wrong_authority = self.run_helper(root, "--verify", authorized=False)
        self.assertNotEqual(wrong_authority.returncode, 0)
        self.assertIn(
            "verified Steam transaction outcome is absent or different",
            wrong_authority.stderr,
        )

        outcome.write_bytes(exact + b"unexpected=scope-expansion\n")
        extra = self.run_helper(root, "--verify", authorized=False)
        self.assertNotEqual(extra.returncode, 0)
        self.assertIn(
            "verified Steam transaction outcome is absent or different",
            extra.stderr,
        )

        outcome.write_bytes(exact)
        outcome.chmod(0o666)
        writable = self.run_helper(root, "--verify", authorized=False)
        self.assertNotEqual(writable.returncode, 0)
        self.assertIn(
            "verified Steam transaction outcome is absent or different",
            writable.stderr,
        )

        outcome.chmod(0o644)
        outside = root / "outside-outcome"
        outside.write_bytes(exact)
        outcome.unlink()
        outcome.symlink_to(outside)
        symlinked = self.run_helper(root, "--verify", authorized=False)
        self.assertNotEqual(symlinked.returncode, 0)
        self.assertIn(
            "verified Steam transaction outcome is absent or different",
            symlinked.stderr,
        )
        self.assertEqual(outside.read_bytes(), exact)

    def test_update_failure_recovers_all_pre_package_mutations(self):
        root = self.make_test_root()
        self.addCleanup(shutil.rmtree, root, True)
        result = self.run_helper(
            root, "--install", extra={"STEAM_TEST_APT_FAIL": "update"}
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(
            (root / "etc/apt/sources.list.d/plebian-os-steam.sources").exists()
        )
        self.assertFalse(
            (root / "etc/apt/preferences.d/plebian-os-steam.pref").exists()
        )
        self.assertFalse((root / "usr/share/keyrings/steam.gpg").exists())
        self.assertFalse((root / "test-state/i386").exists())
        outcome = (root / "var/lib/plebian-os/steam/outcome").read_text()
        self.assertIn("state=RECOVERED_NO_CHANGE\n", outcome)

    def test_non_https_download_plan_is_rejected_and_recovered(self):
        root = self.make_test_root()
        self.addCleanup(shutil.rmtree, root, True)
        result = self.run_helper(
            root, "--install", extra={"STEAM_TEST_URI_SCHEME": "http"}
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("could not bound the Steam package download plan", result.stderr)
        self.assertFalse(
            (root / "etc/apt/sources.list.d/plebian-os-steam.sources").exists()
        )
        self.assertFalse((root / "test-state/i386").exists())
        outcome = (root / "var/lib/plebian-os/steam/outcome").read_text()
        self.assertIn("state=RECOVERED_NO_CHANGE\n", outcome)

    def test_exact_repair_accepts_a_zero_download_plan(self):
        root = self.make_test_root()
        self.addCleanup(shutil.rmtree, root, True)
        installed = self.run_helper(root, "--install")
        self.assertEqual(installed.returncode, 0, installed.stderr)

        repaired = self.run_helper(
            root, "--repair", extra={"STEAM_TEST_EMPTY_URI_PLAN": "1"}
        )

        self.assertEqual(repaired.returncode, 0, repaired.stderr)
        outcome = (root / "var/lib/plebian-os/steam/outcome").read_text()
        self.assertIn("state=VERIFIED\n", outcome)

    def test_launcher_candidate_must_resolve_only_to_valve_stable(self):
        root = self.make_test_root()
        self.addCleanup(shutil.rmtree, root, True)
        result = self.run_helper(
            root, "--install", extra={"STEAM_TEST_APT_PROVENANCE": "other"}
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "could not resolve steam-launcher to one exact Valve stable "
            "candidate",
            result.stderr,
        )
        outcome = (root / "var/lib/plebian-os/steam/outcome").read_text()
        self.assertIn("state=RECOVERED_NO_CHANGE\n", outcome)
        self.assertFalse((root / "test-state/installed").exists())

    def test_each_direct_package_must_resolve_only_to_valve_stable(self):
        root = self.make_test_root()
        self.addCleanup(shutil.rmtree, root, True)
        result = self.run_helper(
            root, "--install", extra={"STEAM_TEST_APT_PROVENANCE": "libs-other"}
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "could not resolve steam-libs-amd64:amd64 to one exact Valve "
            "stable candidate",
            result.stderr,
        )
        self.assertFalse((root / "test-state/installed").exists())

    def test_manifest_extra_bytes_are_rejected_before_mutation(self):
        root = self.make_test_root()
        self.addCleanup(shutil.rmtree, root, True)
        manifest = root / "policy/policy-v1.manifest"
        with manifest.open("a", encoding="utf-8") as stream:
            stream.write("unexpected=scope-expansion\n")

        result = self.run_helper(root, "--install")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("manifest bytes differ", result.stderr)
        self.assertFalse((root / "etc").exists())

    def test_unknown_i386_population_never_claims_complete_rollback(self):
        root = self.make_test_root()
        self.addCleanup(shutil.rmtree, root, True)
        result = self.run_helper(
            root,
            "--install",
            extra={
                "STEAM_TEST_APT_FAIL": "update",
                "STEAM_TEST_DPKG_QUERY_FAIL": "1",
            },
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((root / "test-state/i386").exists())
        outcome = (root / "var/lib/plebian-os/steam/outcome").read_text()
        self.assertIn("state=REPAIR_REQUIRED\n", outcome)
        self.assertIn("could not be proven 0/N", result.stderr)

    def test_conflicting_policy_is_named_and_never_overwritten(self):
        root = self.make_test_root()
        self.addCleanup(shutil.rmtree, root, True)
        target = root / "etc/apt/sources.list.d/plebian-os-steam.sources"
        target.parent.mkdir(parents=True)
        target.write_text("a different administrator policy\n", encoding="utf-8")
        before = target.read_bytes()
        result = self.run_helper(root, "--repair")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflicts with packaged Steam policy", result.stderr)
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse((root / "test-state/i386").exists())

    def test_unknown_or_caller_selected_actions_are_rejected(self):
        for arguments in (
            ["--install", "https://example.invalid"],
            ["--closure", "/tmp/foreign"],
            ["--package", "anything"],
        ):
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    [str(SETUP), *arguments],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
