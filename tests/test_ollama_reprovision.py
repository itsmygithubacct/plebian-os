import hashlib
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"
UPDATE = ROOT / "provision" / "plebian-os-update.sh"


def extract_shell_function(source: str, name: str) -> str:
    start = source.index(f"{name}() {{")
    end = source.index("\n}\n", start) + 2
    return source[start:end]


class OllamaReprovisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = PROVISION.read_text()
        receipt_function = extract_shell_function(
            source, "ollama_carrier_receipt_matches_manifest"
        )
        install_function = extract_shell_function(
            source, "install_ollama_runtime_from_carrier"
        )
        cls.ollama_functions = receipt_function + "\n" + install_function
        preflight_start = source.index("preflight_ollama_carrier() {")
        preflight_end = source.index('\n}\n\nscan_ollama_carrier_arguments "$@"', preflight_start) + 2
        cls.preflight_function = source[preflight_start:preflight_end]
        cls.provision_source = source
        cls.update_source = UPDATE.read_text()

    def make_fixture(self, root: Path, *, with_carrier: bool):
        media = root / "media"
        installed_sbin = root / "installed-sbin"
        provision_dir = root / "provision"
        state_root = root / "var" / "lib" / "plebian-os"
        shim_dir = root / "shim-bin"
        for directory in (media, installed_sbin, provision_dir, shim_dir):
            directory.mkdir(parents=True)

        payload = b"fixture Ollama carrier bytes\n"
        digest = hashlib.sha256(payload).hexdigest()
        archive = media / "ollama-runtime-carrier.tar.xz"
        if with_carrier:
            archive.write_bytes(payload)
        manifest = media / "0.2.2.env"
        manifest.write_text(
            "PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_BYTES="
            f"{len(payload)}\n"
            "PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_SHA256="
            f"{digest}\n"
        )
        source_installer = provision_dir / "plebian-os-install-kilix-ollama-runtime"
        source_installer.write_text("#!/bin/sh\nexit 0\n")
        source_installer.chmod(0o755)

        calls = root / "calls"
        verify_ok = root / "verify-ok"
        install_shim = shim_dir / "install"
        install_shim.write_text(
            "#!/bin/bash\n"
            "args=()\n"
            "while (($#)); do\n"
            "  case \"$1\" in\n"
            "    -o|-g) shift 2 ;;\n"
            "    *) args+=(\"$1\"); shift ;;\n"
            "  esac\n"
            "done\n"
            "exec /usr/bin/install \"${args[@]}\"\n"
        )
        install_shim.chmod(0o755)

        stat_shim = shim_dir / "stat"
        stat_shim.write_text(
            "#!/bin/bash\n"
            "format=\"$2\"\n"
            "shift 2\n"
            "[[ \"${1:-}\" == -- ]] && shift\n"
            "path=\"$1\"\n"
            "case \"$path\" in\n"
            "  \"$FIXTURE_STATE_ROOT\"|\"$FIXTURE_STATE_ROOT\"/*)\n"
            "    case \"$format\" in\n"
            "      %u) echo 0 ;;\n"
            "      %u:%a) printf '0:'; /usr/bin/stat -c '%a' -- \"$path\" ;;\n"
            "      %u:%a:%h) printf '0:'; /usr/bin/stat -c '%a:%h' -- \"$path\" ;;\n"
            "      *) exec /usr/bin/stat -c \"$format\" -- \"$path\" ;;\n"
            "    esac\n"
            "    ;;\n"
            "  *) exec /usr/bin/stat -c \"$format\" -- \"$path\" ;;\n"
            "esac\n"
        )
        stat_shim.chmod(0o755)

        python_shim = shim_dir / "python3"
        python_shim.write_text(
            "#!/bin/sh\n"
            "case \" $* \" in\n"
            "  *\" --verify \"*) printf 'verify\\n' >>\"$FIXTURE_CALLS\"; "
            "    [ -f \"$FIXTURE_VERIFY_OK\" ] ;;\n"
            "  *\" --extract-carrier \"*) printf 'extract\\n' >>\"$FIXTURE_CALLS\"; exit 0 ;;\n"
            "  *\" --closure \"*) printf 'closure\\n' >>\"$FIXTURE_CALLS\"; exit 0 ;;\n"
            "  *) echo \"unexpected python3 fixture command: $*\" >&2; exit 99 ;;\n"
            "esac\n"
        )
        python_shim.chmod(0o755)

        chown_shim = shim_dir / "chown"
        chown_shim.write_text("#!/bin/sh\nexit 0\n")
        chown_shim.chmod(0o755)
        systemctl_shim = shim_dir / "systemctl"
        systemctl_shim.write_text(
            "#!/bin/sh\nprintf 'systemctl %s\\n' \"$*\" >>\"$FIXTURE_CALLS\"\nexit 0\n"
        )
        systemctl_shim.chmod(0o755)

        functions = self.ollama_functions
        functions = functions.replace("/usr/local/share/plebian-os", str(media))
        functions = functions.replace(
            "/usr/local/sbin/plebian-os-install-kilix-ollama-runtime",
            str(installed_sbin / "plebian-os-install-kilix-ollama-runtime"),
        )
        functions = functions.replace("/var/lib/plebian-os", str(state_root))
        prelude = "\n".join((
            "set -euo pipefail",
            "log() { :; }",
            'die() { printf "%s\\n" "$*" >&2; exit 1; }',
            "PLEBIAN_OS_VERSION=0.2.2",
            "DRY_RUN=0",
            f"SELF_DIR={shlex.quote(str(provision_dir))}",
            functions,
        ))
        env = os.environ.copy()
        env.update({
            "PATH": f"{shim_dir}:/usr/bin:/bin",
            "FIXTURE_CALLS": str(calls),
            "FIXTURE_VERIFY_OK": str(verify_ok),
            "FIXTURE_STATE_ROOT": str(state_root),
        })
        return {
            "prelude": prelude,
            "env": env,
            "archive": archive,
            "calls": calls,
            "verify_ok": verify_ok,
            "receipt": state_root / "ollama-runtime-carrier.receipt",
            "digest": digest,
            "payload_size": len(payload),
        }

    def run_fixture(self, fixture, body: str):
        return subprocess.run(
            ["bash", "-c", fixture["prelude"] + "\n" + body],
            env=fixture["env"], text=True, capture_output=True, check=False,
        )

    def test_second_provision_reuses_verified_runtime_and_keeps_carrier(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = self.make_fixture(Path(td), with_carrier=True)
            result = self.run_fixture(
                fixture,
                "install_ollama_runtime_from_carrier\n"
                'touch "$FIXTURE_VERIFY_OK"\n'
                "install_ollama_runtime_from_carrier\n",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(fixture["archive"].is_file())
            self.assertTrue(fixture["receipt"].is_file())
            receipt = fixture["receipt"].read_text()
            self.assertIn(f"carrier_bytes={fixture['payload_size']}\n", receipt)
            self.assertIn(f"carrier_sha256={fixture['digest']}\n", receipt)
            calls = fixture["calls"].read_text().splitlines()
            self.assertEqual(calls.count("verify"), 2)
            self.assertEqual(calls.count("extract"), 1)
            self.assertEqual(calls.count("closure"), 1)
            self.assertEqual(
                calls.count("systemctl is-active --quiet plebian-os-ollama.service"),
                2,
            )

    def test_unverified_runtime_without_carrier_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = self.make_fixture(Path(td), with_carrier=False)
            result = self.run_fixture(fixture, "install_ollama_runtime_from_carrier\n")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("offline Ollama carrier is missing or unsafe", result.stderr)
            self.assertEqual(fixture["calls"].read_text().splitlines(), ["verify"])

    def test_updater_library_and_apt_reconcile_paths_exit_before_ollama_install(self):
        updater = self.update_source
        self.assertNotIn("install_ollama_runtime_from_carrier", updater)
        self.assertIn('"$helper" --reconcile-apt-sources', updater)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            marker = root / "installer-reached"
            script = "\n".join((
                "set -euo pipefail",
                f"install_ollama_runtime_from_carrier() {{ : > {shlex.quote(str(marker))}; }}",
                "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1",
                f"PLEB_STATE_HOME={shlex.quote(str(root / 'state'))}",
                f"source {shlex.quote(str(UPDATE))}",
                f"test ! -e {shlex.quote(str(marker))}",
            ))
            result = subprocess.run(
                ["bash", "-c", script], text=True, capture_output=True,
                env={**os.environ, "HOME": td}, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            reconcile = updater_provision_reconcile_harness(
                self.provision_source, marker)
            result = subprocess.run(
                ["bash", "-c", reconcile], text=True, capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(marker.exists())


class OllamaCarrierPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = PROVISION.read_text()
        scanner_start = source.index("scan_ollama_carrier_arguments() {")
        scanner_end = source.index("\n}\n\n# The 0.2.2 Ollama runtime", scanner_start) + 2
        cls.argument_scanner = source[scanner_start:scanner_end]
        receipt_function = extract_shell_function(
            source, "ollama_carrier_receipt_matches_manifest"
        )
        pin_start = source.index("ollama_verify_carrier_pins() {")
        start = source.index("preflight_ollama_carrier() {")
        end = source.index('\n}\n\nscan_ollama_carrier_arguments "$@"', start) + 2
        cls.preflight_function = receipt_function + "\n" + source[pin_start:end]
        cls.install_function = extract_shell_function(
            source, "install_ollama_runtime_from_carrier"
        )
        prefix_end = source.index("\n# Keep a copy of this script's own output")
        cls.entry_prefix = source[:prefix_end]

    def make_fixture(self, root: Path, *, carrier_payload: bytes):
        checkout = root / "checkout"
        provision_dir = checkout / "provision"
        release_dir = checkout / "releases"
        stage_root = root / "usr-local-share-plebian-os"
        installed_sbin = root / "installed-sbin"
        state_root = root / "var" / "lib" / "plebian-os"
        shim_dir = root / "shim-bin"
        for directory in (provision_dir, release_dir, installed_sbin, state_root, shim_dir):
            directory.mkdir(parents=True)

        digest = hashlib.sha256(carrier_payload).hexdigest()
        manifest = release_dir / "0.2.2.env"
        manifest.write_text(
            "PLEBIAN_OS_VERSION=0.2.2\n"
            "PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_BYTES="
            f"{len(carrier_payload)}\n"
            "PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_SHA256="
            f"{digest}\n",
            encoding="utf-8",
        )
        installer = provision_dir / "plebian-os-install-kilix-ollama-runtime"
        installer.write_bytes((ROOT / "provision" / installer.name).read_bytes())
        installer.chmod(0o755)
        carrier = root / "ollama-0.32.14-kilix-unix-vulkan-r1.tar.xz"
        carrier.write_bytes(carrier_payload)

        install_shim = shim_dir / "install"
        install_shim.write_text(
            "#!/bin/bash\n"
            "args=()\n"
            "while (($#)); do\n"
            "  case \"$1\" in\n"
            "    -o|-g) shift 2 ;;\n"
            "    *) args+=(\"$1\"); shift ;;\n"
            "  esac\n"
            "done\n"
            "exec /usr/bin/install \"${args[@]}\"\n",
            encoding="utf-8",
        )
        install_shim.chmod(0o755)
        stat_shim = shim_dir / "stat"
        stat_shim.write_text(
            "#!/bin/bash\n"
            "format=\"$2\"\n"
            "shift 2\n"
            "[[ \"${1:-}\" == -- ]] && shift\n"
            "path=\"$1\"\n"
            "case \"$path\" in\n"
            "  \"$FIXTURE_STAGE_ROOT\"|\"$FIXTURE_STAGE_ROOT\"/*|\"$FIXTURE_STATE_ROOT\"|\"$FIXTURE_STATE_ROOT\"/*|\"$FIXTURE_INSTALLED_SBIN\"|\"$FIXTURE_INSTALLED_SBIN\"/*)\n"
            "    case \"$format\" in\n"
            "      %u:%a) printf '0:'; /usr/bin/stat -c '%a' -- \"$path\" ;;\n"
            "      %u:%a:%h) printf '0:'; /usr/bin/stat -c '%a:%h' -- \"$path\" ;;\n"
            "      *) exec /usr/bin/stat -c \"$format\" -- \"$path\" ;;\n"
            "    esac ;;\n"
            "  *) exec /usr/bin/stat -c \"$format\" -- \"$path\" ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        stat_shim.chmod(0o755)

        python_shim = shim_dir / "python3"
        python_shim.write_text(
            "#!/bin/sh\n"
            "case \" $* \" in\n"
            "  *\" --verify \"*) printf 'verify\\n' >>\"$FIXTURE_CALLS\"; [ -f \"$FIXTURE_VERIFY_OK\" ] ;;\n"
            "  *) echo \"unexpected python3 fixture command: $*\" >&2; exit 99 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        python_shim.chmod(0o755)
        systemctl_shim = shim_dir / "systemctl"
        systemctl_shim.write_text(
            "#!/bin/sh\nprintf 'systemctl %s\\n' \"$*\" >>\"$FIXTURE_CALLS\"\nexit 0\n",
            encoding="utf-8",
        )
        systemctl_shim.chmod(0o755)

        source = self.preflight_function
        source = source.replace("/usr/local/share/plebian-os", str(stage_root))
        source = source.replace(
            "/usr/local/sbin/plebian-os-install-kilix-ollama-runtime",
            str(installed_sbin / "plebian-os-install-kilix-ollama-runtime"),
        )
        source = source.replace(
            "/var/lib/plebian-os/ollama-runtime-carrier.receipt",
            str(state_root / "ollama-runtime-carrier.receipt"),
        )
        marker = root / "package-mutation-marker"
        env = os.environ.copy()
        env.pop("PLEBIAN_OS_OLLAMA_CARRIER", None)
        env.update({
            "PATH": f"{shim_dir}:/usr/bin:/bin",
            "FIXTURE_STAGE_ROOT": str(stage_root),
            "FIXTURE_STATE_ROOT": str(state_root),
            "FIXTURE_INSTALLED_SBIN": str(installed_sbin),
            "FIXTURE_MUTATION_MARKER": str(marker),
            "FIXTURE_CALLS": str(root / "calls"),
            "FIXTURE_VERIFY_OK": str(root / "verify-ok"),
        })
        return {
            "root": root,
            "stage_root": stage_root,
            "installed_sbin": installed_sbin,
            "installed_helper": installed_sbin / "plebian-os-install-kilix-ollama-runtime",
            "state_root": state_root,
            "checkout": checkout,
            "manifest": manifest,
            "carrier": carrier,
            "payload": carrier_payload,
            "source_installer": installer,
            "source": source,
            "marker": marker,
            "env": env,
        }

    def run_preflight(self, fixture, *, option="", environment="", dry_run=False):
        script = "\n".join((
            "set -euo pipefail",
            "log() { printf '[fixture] %s\\n' \"$*\"; }",
            'die() { printf "%s\\n" "$*" >&2; exit 1; }',
            "PLEBIAN_OS_VERSION=0.2.2",
            f"DRY_RUN={1 if dry_run else 0}",
            f"PLEBIAN_OS_OLLAMA_CARRIER_ARG={shlex.quote(option)}",
            f"SELF_DIR={shlex.quote(str(fixture['checkout'] / 'provision'))}",
            fixture["source"],
            "preflight_ollama_carrier",
            'if [ "$DRY_RUN" != 1 ]; then touch "$FIXTURE_MUTATION_MARKER"; fi',
        ))
        env = fixture["env"].copy()
        if environment:
            env["PLEBIAN_OS_OLLAMA_CARRIER"] = environment
        return subprocess.run(
            ["/bin/bash", "-c", script], env=env, text=True,
            capture_output=True, check=False,
        )

    def run_real_entry_prefix(self, fixture, *, option="", path=None, follow_install=False):
        source = self.entry_prefix.replace(
            'SELF_DIR="$(cd "$(dirname "$0")" && pwd)"',
            f"SELF_DIR={shlex.quote(str(fixture['checkout'] / 'provision'))}",
        ).replace("/usr/local/share/plebian-os", str(fixture["stage_root"]))
        source = source.replace(
            "/usr/local/sbin/plebian-os-install-kilix-ollama-runtime",
            str(fixture["installed_helper"]),
        ).replace(
            "/var/lib/plebian-os/ollama-runtime-carrier.receipt",
            str(fixture["state_root"] / "ollama-runtime-carrier.receipt"),
        )
        script = source + '\nprintf \'entry-prefix-complete\\n\'\n'
        if follow_install:
            install_function = self.install_function.replace(
                "/usr/local/share/plebian-os", str(fixture["stage_root"])
            ).replace(
                "/usr/local/sbin/plebian-os-install-kilix-ollama-runtime",
                str(fixture["installed_helper"]),
            ).replace("/var/lib/plebian-os", str(fixture["state_root"]))
            script += install_function + "\ninstall_ollama_runtime_from_carrier\n"
        env = fixture["env"].copy()
        env["PLEBIAN_OS_VERSION"] = "0.2.2"
        env.pop("PLEBIAN_OS_PROVISION_LIB_ONLY", None)
        env.pop("PLEBIAN_OS_OLLAMA_CARRIER", None)
        if path is not None:
            env["PATH"] = str(path)
        return subprocess.run(
            ["/bin/bash", "-c", script, "plebian-os-provision", *(
                ["--ollama-carrier", option] if option else []
            )],
            cwd=fixture["checkout"], env=env, text=True,
            capture_output=True, check=False,
        )

    def prepare_carrier_free_installation(self, fixture, *, verified):
        fixture["installed_helper"].write_bytes(fixture["source_installer"].read_bytes())
        fixture["installed_helper"].chmod(0o755)
        receipt = fixture["state_root"] / "ollama-runtime-carrier.receipt"
        receipt.write_text(
            "schema=plebian.ollama-runtime-carrier-install/v1\n"
            f"carrier_bytes={len(fixture['payload'])}\n"
            f"carrier_sha256={hashlib.sha256(fixture['payload']).hexdigest()}\n"
            "runtime=ollama-0.32.14-kilix-unix-vulkan-r1\n"
            "service=plebian-os-ollama.service\n"
            "service_active=yes\n"
            "model_weights_carried=false\n",
            encoding="utf-8",
        )
        receipt.chmod(0o644)
        fixture["carrier"].unlink()
        if verified:
            Path(fixture["env"]["FIXTURE_VERIFY_OK"]).touch()

    def make_no_python_path(self, fixture):
        path = fixture["root"] / "no-python-path"
        path.mkdir()
        for tool in ("awk", "cmp", "dirname", "install", "mktemp", "mv", "readlink", "rm", "sha256sum"):
            source = Path("/usr/bin") / tool
            if not source.exists():
                source = Path("/bin") / tool
            (path / tool).symlink_to(source)
        install_shim = path / "install"
        install_shim.unlink()
        install_shim.write_text(
            "#!/bin/bash\n"
            "args=()\n"
            "while (($#)); do\n"
            "  case \"$1\" in\n"
            "    -o|-g) shift 2 ;;\n"
            "    *) args+=(\"$1\"); shift ;;\n"
            "  esac\n"
            "done\n"
            "exec /usr/bin/install \"${args[@]}\"\n",
            encoding="utf-8",
        )
        install_shim.chmod(0o755)
        stat_shim = path / ".stat-shim"
        stat_shim.write_text(
            "#!/bin/bash\n"
            "format=\"$2\"; shift 2; [[ \"${1:-}\" == -- ]] && shift; path=\"$1\"\n"
            "case \"$path\" in\n"
            "  \"$FIXTURE_STAGE_ROOT\"|\"$FIXTURE_STAGE_ROOT\"/*|\"$FIXTURE_STATE_ROOT\"|\"$FIXTURE_STATE_ROOT\"/*|\"$FIXTURE_INSTALLED_SBIN\"|\"$FIXTURE_INSTALLED_SBIN\"/*)\n"
            "    case \"$format\" in\n"
            "      %u:%a) printf '0:'; /usr/bin/stat -c '%a' -- \"$path\" ;;\n"
            "      %u:%a:%h) printf '0:'; /usr/bin/stat -c '%a:%h' -- \"$path\" ;;\n"
            "      *) exec /usr/bin/stat -c \"$format\" -- \"$path\" ;;\n"
            "    esac ;;\n"
            "  *) exec /usr/bin/stat -c \"$format\" -- \"$path\" ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        stat_shim.chmod(0o755)
        (path / "stat").symlink_to(stat_shim)
        return path

    def test_cli_option_is_captured_for_preflight_and_consumed_later(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = str(Path(directory) / "carrier.tar.xz")
            script = "\n".join((
                "set -euo pipefail",
                'die() { printf "%s\\n" "$*" >&2; exit 1; }',
                "DRY_RUN=0",
                'PLEBIAN_OS_OLLAMA_CARRIER_ARG=""',
                "OLLAMA_PREFLIGHT_SKIP=0",
                self.argument_scanner,
                'scan_ollama_carrier_arguments "$@"',
                'test "$PLEBIAN_OS_OLLAMA_CARRIER_ARG" = "$EXPECTED_CARRIER"',
                'test "$DRY_RUN" = 1',
            ))
            result = subprocess.run(
                ["bash", "-c", script, "bash", "--ollama-carrier", archive, "--dry-run"],
                env={**os.environ, "EXPECTED_CARRIER": archive},
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_preflight_runs_before_logging_or_dependency_mutation(self):
        source = PROVISION.read_text()
        call = source.index("    preflight_ollama_carrier\n")
        logger = source.index('PROVISION_LOG="${PLEBIAN_OS_PROVISION_LOG:-')
        dependencies = source.index('bash "$DEPS_SCRIPT" || die "dependency install failed')
        self.assertLess(call, logger)
        self.assertLess(logger, dependencies)
        self.assertIn("PLEBIAN_OS_OLLAMA_CARRIER", self.preflight_function)
        self.assertNotIn("curl", self.preflight_function)
        self.assertNotIn("wget", self.preflight_function)

    def test_missing_carrier_fails_before_staging_or_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.make_fixture(Path(directory), carrier_payload=b"pinned carrier\n")
            fixture["carrier"].unlink()
            result = self.run_preflight(fixture)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("offline 0.2.2 release asset", result.stderr)
            self.assertIn("--ollama-carrier PATH", result.stderr)
            self.assertFalse(fixture["marker"].exists())
            self.assertFalse(fixture["stage_root"].exists())

    def test_real_entry_accepts_verified_carrier_free_retry_and_enables_service(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.make_fixture(Path(directory), carrier_payload=b"pinned carrier\n")
            self.prepare_carrier_free_installation(fixture, verified=True)
            result = self.run_real_entry_prefix(fixture, follow_install=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("entry-prefix-complete", result.stdout)
            self.assertTrue((fixture["stage_root"] / "0.2.2.env").is_file())
            self.assertFalse((fixture["stage_root"] / "ollama-runtime-carrier.tar.xz").exists())
            calls = Path(fixture["env"]["FIXTURE_CALLS"]).read_text().splitlines()
            self.assertEqual(calls.count("verify"), 2)
            self.assertIn("systemctl enable --now plebian-os-ollama.service", calls)
            self.assertIn(
                "systemctl is-active --quiet plebian-os-ollama.service", calls
            )

    def test_real_entry_rejects_unverified_carrier_free_retry_before_staging_or_service_change(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.make_fixture(Path(directory), carrier_payload=b"pinned carrier\n")
            self.prepare_carrier_free_installation(fixture, verified=False)
            result = self.run_real_entry_prefix(fixture, follow_install=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("0.2.2 Ollama carrier is missing", result.stderr)
            self.assertIn("installed Ollama runtime verification failed", result.stderr)
            self.assertNotIn("entry-prefix-complete", result.stdout)
            self.assertFalse(fixture["stage_root"].exists())
            calls = Path(fixture["env"]["FIXTURE_CALLS"]).read_text().splitlines()
            self.assertEqual(calls, ["verify"])

    def test_carrier_free_retry_without_python_is_reported_as_unverified(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.make_fixture(Path(directory), carrier_payload=b"pinned carrier\n")
            self.prepare_carrier_free_installation(fixture, verified=True)
            no_python_path = self.make_no_python_path(fixture)
            result = self.run_real_entry_prefix(
                fixture, path=no_python_path, follow_install=True
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("0.2.2 Ollama carrier is missing", result.stderr)
            self.assertIn("python3 is unavailable to verify the installed runtime", result.stderr)
            self.assertFalse(fixture["stage_root"].exists())

    def test_plain_debian_carrier_stages_manifest_and_archive_with_safe_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.make_fixture(Path(directory), carrier_payload=b"pinned carrier\n")
            result = self.run_preflight(fixture, option=str(fixture["carrier"]))
            self.assertEqual(result.returncode, 0, result.stderr)
            staged_manifest = fixture["stage_root"] / "0.2.2.env"
            staged_carrier = fixture["stage_root"] / "ollama-runtime-carrier.tar.xz"
            self.assertEqual(staged_manifest.read_bytes(), fixture["manifest"].read_bytes())
            self.assertEqual(staged_carrier.read_bytes(), fixture["payload"])
            for path in (staged_manifest, staged_carrier):
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(path.stat().st_mode & 0o777, 0o644)
                self.assertEqual(os.stat(path).st_nlink, 1)
            self.assertTrue(fixture["marker"].exists())

    def test_real_entry_preflight_works_without_python3_and_stages_both_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.make_fixture(Path(directory), carrier_payload=b"pinned carrier\n")
            no_python_path = self.make_no_python_path(fixture)
            result = self.run_real_entry_prefix(
                fixture, option=str(fixture["carrier"]), path=no_python_path
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("entry-prefix-complete", result.stdout)
            self.assertFalse((no_python_path / "python3").exists())
            staged_manifest = fixture["stage_root"] / "0.2.2.env"
            staged_carrier = fixture["stage_root"] / "ollama-runtime-carrier.tar.xz"
            self.assertEqual(staged_manifest.read_bytes(), fixture["manifest"].read_bytes())
            self.assertEqual(staged_carrier.read_bytes(), fixture["payload"])

    def test_real_entry_preflight_without_python_reports_wrong_size_and_hash(self):
        cases = (
            (b"pinned carrier\nextra", "Ollama carrier size does not match"),
            (b"wrong carrier!\n", "Ollama carrier SHA-256 does not match"),
        )
        for payload, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                fixture = self.make_fixture(Path(directory), carrier_payload=b"pinned carrier\n")
                fixture["carrier"].write_bytes(payload)
                no_python_path = self.make_no_python_path(fixture)
                result = self.run_real_entry_prefix(
                    fixture, option=str(fixture["carrier"]), path=no_python_path
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertNotIn("entry-prefix-complete", result.stdout)
                self.assertFalse(fixture["stage_root"].exists())

    def test_real_entry_preflight_without_python_rejects_malformed_and_duplicate_pin_keys(self):
        cases = (
            ("malformed", "not-decimal", "carrier byte count must be decimal"),
            ("duplicate", "duplicate", "exactly one PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_BYTES"),
        )
        for case, _mutation, message in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                fixture = self.make_fixture(Path(directory), carrier_payload=b"pinned carrier\n")
                if case == "malformed":
                    manifest_text = fixture["manifest"].read_text(encoding="utf-8")
                    manifest_text = manifest_text.replace(
                        f"PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_BYTES={len(fixture['payload'])}\n",
                        "PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_BYTES=not-decimal\n",
                    )
                    fixture["manifest"].write_text(manifest_text, encoding="utf-8")
                else:
                    with fixture["manifest"].open("a", encoding="utf-8") as manifest:
                        manifest.write(
                            f"PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_BYTES={len(fixture['payload'])}\n"
                        )
                no_python_path = self.make_no_python_path(fixture)
                result = self.run_real_entry_prefix(
                    fixture, option=str(fixture["carrier"]), path=no_python_path
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertNotIn("entry-prefix-complete", result.stdout)
                self.assertFalse(fixture["stage_root"].exists())

    def test_real_entry_reports_missing_preflight_tool_without_calling_it_a_hash_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.make_fixture(Path(directory), carrier_payload=b"pinned carrier\n")
            no_python_path = self.make_no_python_path(fixture)
            (no_python_path / "sha256sum").unlink()
            result = self.run_real_entry_prefix(
                fixture, option=str(fixture["carrier"]), path=no_python_path
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("required preflight tool missing: sha256sum", result.stderr)
            self.assertNotIn("SHA-256", result.stderr)
            self.assertFalse(fixture["stage_root"].exists())

    def test_environment_carrier_is_honored_and_dry_run_only_reports_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.make_fixture(Path(directory), carrier_payload=b"pinned carrier\n")
            result = self.run_preflight(
                fixture, environment=str(fixture["carrier"]), dry_run=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("stage carrier as root:root mode 0644", result.stdout)
            self.assertFalse(fixture["stage_root"].exists())
            self.assertFalse(fixture["marker"].exists())

    def test_wrong_hash_carrier_fails_before_staging_or_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.make_fixture(Path(directory), carrier_payload=b"pinned carrier\n")
            fixture["carrier"].write_bytes(b"x" * len(fixture["payload"]))
            result = self.run_preflight(fixture, option=str(fixture["carrier"]))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SHA-256 does not match", result.stderr)
            self.assertFalse(fixture["marker"].exists())
            self.assertFalse(fixture["stage_root"].exists())

    def test_different_iso_and_checkout_manifests_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.make_fixture(Path(directory), carrier_payload=b"pinned carrier\n")
            fixture["stage_root"].mkdir()
            fixture["stage_root"].chmod(0o755)
            staged_manifest = fixture["stage_root"] / "0.2.2.env"
            staged_manifest.write_bytes(fixture["manifest"].read_bytes() + b"# staged\n")
            staged_manifest.chmod(0o644)
            result = self.run_preflight(fixture, option=str(fixture["carrier"]))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("staged and checkout 0.2.2 release manifests differ", result.stderr)
            self.assertFalse(fixture["marker"].exists())
            self.assertFalse((fixture["stage_root"] / "ollama-runtime-carrier.tar.xz").exists())


def updater_provision_reconcile_harness(source: str, marker: Path) -> str:
    function_start = source.index("reconcile_apt_sources_and_exit() {")
    function_end = source.index("\n}", function_start) + 2
    reconcile_function = source[function_start:function_end]
    handler = (
        'if [ "$RECONCILE_APT_ONLY" = 1 ]; then\n'
        "    reconcile_apt_sources_and_exit\n"
        "fi\n"
    )
    handler_start = source.index(handler)
    installer_call = source.index("\ninstall_ollama_runtime_from_carrier\n\n# The first-run wizard")
    if handler_start >= installer_call:
        raise AssertionError("apt reconciliation moved after Ollama installation")
    return "\n".join((
        "set -euo pipefail",
        "log() { :; }",
        "release_apt_lifecycle() { return 1; }",
        f"{reconcile_function}",
        f"RECONCILE_APT_ONLY=1",
        "install_ollama_runtime_from_carrier() { : > "
        + shlex.quote(str(marker))
        + "; }",
        handler,
        "install_ollama_runtime_from_carrier",
    ))


if __name__ == "__main__":
    unittest.main()
