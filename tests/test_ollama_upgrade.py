"""An upgrade installs the pinned Ollama runtime on a machine that has none.

A machine installed from an ISO built before Ollama shipped has the runtime
installer and its manifest but no runtime, carrier or service. These tests
drive the real provisioner functions (sourced in library mode, every absolute
path rewritten under a scratch root, as tests/test_lid_update.py does), the
real updater step around them, and the RC8 shim in install-image-models.py.
The runtime installer, curl and systemctl are fixtures; prlimit and timeout are
the real tools, so the byte cap is the real one. Nothing outside the scratch
root is touched.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_lid_update import under

ROOT = Path(__file__).resolve().parents[1]
UPDATE = ROOT / "provision" / "plebian-os-update.sh"
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"
REMASTER = ROOT / "build" / "remaster-iso.sh"
INSTALLER = ROOT / "provision" / "plebian-os-install-kilix-ollama-runtime"
IMAGE_MODELS = ROOT / "provision" / "install-image-models.py"
ENV = ROOT / "releases" / "0.2.3.env"
REQUIREMENTS = ROOT / "releases" / "0.2.3.requirements"
NOTES = ROOT / "releases" / "0.2.3-notes.md"

URL = ("https://github.com/itsmygithubacct/plebian-os/releases/download/v0.2.2/"
       "ollama-0.32.14-kilix-unix-vulkan-r1.tar.xz")
URL_PATTERN = (r"^https://github\.com/itsmygithubacct/plebian-os/releases/download/"
               r"[A-Za-z0-9._-]+/ollama-0\.32\.14-kilix-unix-vulkan-r1\.tar\.xz$")
# 4 KiB: the fixture curl logs its call under the same file-size limit as its output.
PAYLOAD = (b"fixture Ollama carrier bytes for the upgrade step\n" * 84)[:4096]


def manifest_values(path: Path) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for line in path.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values.setdefault(key, []).append(value)
    return values


def load_image_models():
    spec = importlib.util.spec_from_file_location("install_image_models_for_ollama", IMAGE_MODELS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Fixture:
    """A scratch root with the deployed OS layer an upgrade leaves behind."""

    def __init__(self, tc: unittest.TestCase, *, version="0.2.3", url=URL, payload=PAYLOAD):
        self.tmp = Path(tempfile.mkdtemp())
        tc.addCleanup(subprocess.run, ["rm", "-rf", str(self.tmp)])
        self.root = self.tmp / "root"
        for d in ("usr/local/share/plebian-os", "usr/local/sbin", "usr/bin", "etc/pleb",
                  "var/lib/plebian-os"):
            (self.root / d).mkdir(parents=True, exist_ok=True)
        self.share = self.root / "usr/local/share/plebian-os"
        self.state = self.root / "var/lib/plebian-os"
        self.archive = self.share / "ollama-runtime-carrier.tar.xz"
        self.receipt = self.state / "ollama-runtime-carrier.receipt"
        self.manifest = self.share / "ollama-release.env"
        self.prov = self.root / "usr/local/sbin/plebian-os-provision"
        self.installer = self.root / "usr/local/sbin/plebian-os-install-kilix-ollama-runtime"
        self.calls = self.tmp / "calls"
        self.verify_ok = self.tmp / "verify-ok"
        self.served = self.tmp / "served"
        self.curl_fail = self.tmp / "curl-fail"
        self.closure_fail = self.tmp / "closure-fail"
        self.shims = self.tmp / "shim-bin"
        self.shims.mkdir()
        self.payload = payload
        lines = [f"PLEBIAN_OS_VERSION={version}",
                 f"PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_BYTES={len(payload)}",
                 f"PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_SHA256={hashlib.sha256(payload).hexdigest()}"]
        if url is not None:
            lines.append(f"PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_URL={url}")
        self.manifest.write_text("\n".join(lines) + "\n")
        (self.share / "VERSION").write_text(version + "\n")
        self.installer.write_text("#!/bin/sh\nexit 0\n")
        self.installer.chmod(0o755)
        self.install_provisioner()
        self.write_shims()

    def install_provisioner(self, text=None):
        self.prov.write_text(text if text is not None else under(PROVISION.read_text(), self.root))
        self.prov.chmod(0o755)

    def shim(self, name: str, text: str, where: Path | None = None):
        path = (where or self.shims) / name
        path.write_text(text)
        path.chmod(0o755)

    def write_shims(self):
        # The pinned-size check the real installer makes, for the fixture payload.
        check = (
            'manifest=""; for a; do [ "$prev" = --manifest ] && manifest="$a"; prev="$a"; done\n'
            'want_bytes=$(sed -n "s/^PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_BYTES=//p" "$manifest")\n'
            'want_sha=$(sed -n "s/^PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_SHA256=//p" "$manifest")\n'
            'verify_file() { [ -f "$1" ] && [ "$(/usr/bin/stat -c %s -- "$1")" = "$want_bytes" ] '
            '&& [ "$(sha256sum -- "$1" | cut -d" " -f1)" = "$want_sha" ]; }\n'
        )
        self.shim("python3", "#!/bin/bash\n" + check + (
            'prev=""; target=""\n'
            'for a; do case "$prev" in --verify-carrier|--extract-carrier) target="$a" ;; esac; prev="$a"; done\n'
            'case " $* " in\n'
            '  *" --verify "*) echo verify >>"$FIXTURE_CALLS"; [ -f "$FIXTURE_VERIFY_OK" ] ;;\n'
            '  *" --verify-carrier "*) echo "verify-carrier $target" >>"$FIXTURE_CALLS"; verify_file "$target" ;;\n'
            '  *" --extract-carrier "*) echo extract >>"$FIXTURE_CALLS"; verify_file "$target" ;;\n'
            '  *" --closure "*) echo closure >>"$FIXTURE_CALLS"; [ ! -e "$FIXTURE_CLOSURE_FAIL" ] || exit 1;\n'
            '      : >"$FIXTURE_VERIFY_OK" ;;\n'
            '  *) echo "unexpected python3 fixture command: $*" >&2; exit 99 ;;\n'
            'esac\n'))
        self.shim("install", "#!/bin/bash\nargs=()\nwhile (($#)); do case \"$1\" in "
                  "-o|-g) shift 2 ;; *) args+=(\"$1\"); shift ;; esac; done\n"
                  "exec /usr/bin/install \"${args[@]}\"\n")
        self.shim("chown", "#!/bin/sh\nexit 0\n")
        self.shim("systemctl", "#!/bin/sh\nprintf 'systemctl %s\\n' \"$*\" >>\"$FIXTURE_CALLS\"\nexit 0\n")
        self.shim("stat", (
            "#!/bin/bash\nformat=\"$2\"; shift 2; [[ \"${1:-}\" == -- ]] && shift; path=\"$1\"\n"
            "case \"$path\" in \"$FIXTURE_ROOT\"/*)\n"
            "  case \"$format\" in\n"
            "    %u) echo 0 ;;\n"
            "    %u:%a) printf '0:'; /usr/bin/stat -c '%a' -- \"$path\" ;;\n"
            "    %u:%a:%h) printf '0:'; /usr/bin/stat -c '%a:%h' -- \"$path\" ;;\n"
            "    *) exec /usr/bin/stat -c \"$format\" -- \"$path\" ;;\n"
            "  esac ;;\n"
            "  *) exec /usr/bin/stat -c \"$format\" -- \"$path\" ;;\n"
            "esac\n"))
        # The rewritten provisioner runs <root>/usr/bin/{prlimit,timeout,curl}.
        # prlimit and timeout are the real tools; curl serves the fixture file.
        bin_dir = self.root / "usr/bin"
        self.shim("prlimit", '#!/bin/sh\nexec /usr/bin/prlimit "$@"\n', bin_dir)
        self.shim("timeout", '#!/bin/sh\nexec /usr/bin/timeout "$@"\n', bin_dir)
        self.shim("curl", (
            "#!/bin/bash\nout=''; url=''; while (($#)); do case \"$1\" in "
            "--output) out=\"$2\"; shift 2 ;; --url) url=\"$2\"; shift 2 ;; *) shift ;; esac; done\n"
            "echo \"curl $url\" >>\"$FIXTURE_CALLS\"\n"
            "[ ! -e \"$FIXTURE_CURL_FAIL\" ] || { echo 'curl: (6) Could not resolve host' >&2; exit 6; }\n"
            # dd, not cat: coreutils cat trips RLIMIT_FSIZE at exactly the limit; curl does not.
            "dd if=\"$FIXTURE_SERVED\" of=\"$out\" status=none\n"), bin_dir)

    def env(self) -> dict[str, str]:
        return {
            "PATH": f"{self.shims}:/usr/bin:/bin",
            "HOME": str(self.tmp),
            "LANG": "C.UTF-8",
            "FIXTURE_ROOT": str(self.root),
            "FIXTURE_CALLS": str(self.calls),
            "FIXTURE_VERIFY_OK": str(self.verify_ok),
            "FIXTURE_SERVED": str(self.served),
            "FIXTURE_CURL_FAIL": str(self.curl_fail),
            "FIXTURE_CLOSURE_FAIL": str(self.closure_fail),
        }

    def write_receipt(self):
        self.receipt.write_text(
            "schema=plebian.ollama-runtime-carrier-install/v1\n"
            f"carrier_bytes={len(self.payload)}\n"
            f"carrier_sha256={hashlib.sha256(self.payload).hexdigest()}\n"
            "runtime=ollama-0.32.14-kilix-unix-vulkan-r1\n"
            "service=plebian-os-ollama.service\n"
            "service_active=yes\nmodel_weights_carried=false\n")
        self.receipt.chmod(0o644)

    def call_lines(self) -> list[str]:
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def staging_leftovers(self) -> list[str]:
        session = self.state / "session"
        return sorted(p.name for p in session.iterdir()) if session.exists() else []

    def run_root_step(self, version="0.2.3"):
        """The provisioner's step, as the updater's root shell runs it."""
        script = ("set -uo pipefail\n. \"$0\" || exit 97\n"
                  "declare -F install_ollama_runtime_for_update >/dev/null || exit 98\n"
                  "DRY_RUN=0\ninstall_ollama_runtime_for_update\n")
        env = dict(self.env(), PLEBIAN_OS_PROVISION_LIB_ONLY="1",
                   PLEBIAN_OS_PROVISION_LOG_ACTIVE="1", PLEBIAN_OS_VERSION=version)
        return subprocess.run(["bash", "-c", script, str(self.prov)], env=env,
                              capture_output=True, text=True, timeout=120)

    def run_update_step(self, extra=""):
        """The real updater function, with sudo as a pass-through."""
        self.shim("sudo", '#!/bin/sh\nexec "$@"\n')
        script = ("set -euo pipefail\nexport PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
                  f"export PLEBIAN_OS_UPDATE_TEST_PROVISION_SCRIPT={self.prov}\n"
                  f"source {UPDATE}\nPLEBIAN_OS_VERSION=0.2.3\n"
                  "install_ollama_runtime_update\necho step-returned\n" + extra)
        return subprocess.run(["bash", "-c", script], env=self.env(),
                              capture_output=True, text=True, timeout=120)


class ProvisionerUpdateStepTests(unittest.TestCase):
    def assert_installed_from(self, fx, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(fx.archive.read_bytes(), fx.payload)
        self.assertEqual(fx.archive.stat().st_mode & 0o777, 0o644)
        receipt = fx.receipt.read_text()
        self.assertIn(f"carrier_bytes={len(fx.payload)}\n", receipt)
        self.assertIn(f"carrier_sha256={hashlib.sha256(fx.payload).hexdigest()}\n", receipt)
        calls = fx.call_lines()
        self.assertEqual(calls.count("extract"), 1)
        self.assertEqual(calls.count("closure"), 1)
        self.assertIn("systemctl enable --now plebian-os-ollama.service", calls)
        self.assertEqual(fx.staging_leftovers(), [])

    def test_installed_runtime_with_matching_receipt_only_starts_the_service(self):
        fx = Fixture(self)
        fx.verify_ok.touch()
        fx.write_receipt()
        result = fx.run_root_step()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = fx.call_lines()
        self.assertFalse([c for c in calls if c.startswith(("curl", "verify-carrier"))], calls)
        self.assertNotIn("extract", calls)
        self.assertNotIn("closure", calls)
        self.assertIn("systemctl enable --now plebian-os-ollama.service", calls)
        self.assertFalse(fx.archive.exists())

    def test_verified_runtime_without_a_receipt_is_not_trusted(self):
        fx = Fixture(self)
        fx.verify_ok.touch()
        fx.served.write_bytes(fx.payload)
        self.assert_installed_from(fx, fx.run_root_step())
        self.assertIn(f"curl {URL}", fx.call_lines())

    def test_retained_carrier_is_installed_without_a_download(self):
        fx = Fixture(self)
        fx.archive.write_bytes(fx.payload)
        fx.archive.chmod(0o644)
        result = fx.run_root_step()
        self.assert_installed_from(fx, result)
        self.assertFalse([c for c in fx.call_lines() if c.startswith("curl")])
        self.assertIn("retained", result.stdout)

    def test_missing_carrier_is_downloaded_verified_retained_and_installed(self):
        fx = Fixture(self)
        fx.served.write_bytes(fx.payload)
        result = fx.run_root_step()
        self.assert_installed_from(fx, result)
        calls = fx.call_lines()
        self.assertIn(f"curl {URL}", calls)
        verified = [c for c in calls if c.startswith("verify-carrier ")]
        # The download is checked where it landed, before it is retained.
        self.assertTrue(verified and "/var/lib/plebian-os/session/ollama-download." in verified[-1], calls)
        self.assertLess(calls.index(verified[-1]), calls.index("extract"))
        # A second update finds it installed and downloads nothing.
        fx.calls.unlink()
        result = fx.run_root_step()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse([c for c in fx.call_lines() if c.startswith(("curl", "verify-carrier"))])
        self.assertNotIn("closure", fx.call_lines())

    def test_corrupt_retained_carrier_is_replaced_by_the_download(self):
        fx = Fixture(self)
        fx.archive.write_bytes(b"x" * len(fx.payload))
        fx.served.write_bytes(fx.payload)
        self.assert_installed_from(fx, fx.run_root_step())

    def test_failed_download_changes_nothing_and_reports_unavailable(self):
        fx = Fixture(self)
        fx.curl_fail.touch()
        result = fx.run_root_step()
        self.assertEqual(result.returncode, 75, result.stderr)
        self.assertIn("could not download the Ollama runtime carrier", result.stderr)
        self.assertFalse(fx.archive.exists())
        self.assertFalse(fx.receipt.exists())
        self.assertNotIn("closure", fx.call_lines())
        self.assertEqual(fx.staging_leftovers(), [])

    def test_oversized_download_is_stopped_at_the_pinned_size(self):
        fx = Fixture(self)
        fx.served.write_bytes(fx.payload + b"y" * 65536)
        result = fx.run_root_step()
        self.assertEqual(result.returncode, 75, result.stderr)
        self.assertFalse(fx.archive.exists())
        self.assertNotIn("closure", fx.call_lines())
        self.assertEqual(fx.staging_leftovers(), [])

    def test_download_with_the_wrong_digest_fails_and_is_not_retained(self):
        fx = Fixture(self)
        fx.served.write_bytes(b"z" * len(fx.payload))
        result = fx.run_root_step()
        self.assertNotIn(result.returncode, (0, 75), result.stderr)
        self.assertIn("does not match the 0.2.3 release pins", result.stderr)
        self.assertFalse(fx.archive.exists())
        self.assertFalse(fx.receipt.exists())
        self.assertNotIn("extract", fx.call_lines())
        self.assertEqual(fx.staging_leftovers(), [])

    def test_installer_failure_after_extraction_fails(self):
        fx = Fixture(self)
        fx.served.write_bytes(fx.payload)
        fx.closure_fail.touch()
        result = fx.run_root_step()
        self.assertNotIn(result.returncode, (0, 75), result.stderr)
        self.assertIn("offline Ollama runtime installation failed", result.stderr)
        self.assertFalse(fx.receipt.exists())
        self.assertNotIn("systemctl enable --now plebian-os-ollama.service", fx.call_lines())

    def test_manifest_without_a_url_downloads_nothing(self):
        for url in (None, "http://github.com/itsmygithubacct/plebian-os/releases/download/v0.2.2/"
                    "ollama-0.32.14-kilix-unix-vulkan-r1.tar.xz",
                    "https://github.com/someone-else/plebian-os/releases/download/v0.2.2/"
                    "ollama-0.32.14-kilix-unix-vulkan-r1.tar.xz",
                    URL.replace("vulkan-r1", "vulkan-r2")):
            with self.subTest(url=url):
                fx = Fixture(self, url=url)
                fx.served.write_bytes(fx.payload)
                result = fx.run_root_step()
                self.assertEqual(result.returncode, 75, result.stderr)
                self.assertIn("names no Ollama carrier download", result.stderr)
                self.assertFalse([c for c in fx.call_lines() if c.startswith("curl")])

    def test_duplicate_url_lines_download_nothing(self):
        fx = Fixture(self)
        with fx.manifest.open("a") as handle:
            handle.write(f"PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_URL={URL}\n")
        fx.served.write_bytes(fx.payload)
        self.assertEqual(fx.run_root_step().returncode, 75)
        self.assertFalse([c for c in fx.call_lines() if c.startswith("curl")])

    def test_release_without_the_runtime_does_nothing(self):
        fx = Fixture(self, version="0.2.1")
        fx.served.write_bytes(fx.payload)
        result = fx.run_root_step(version="0.2.1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(fx.call_lines(), [])


class UpdaterStepTests(unittest.TestCase):
    def test_update_installs_a_missing_runtime(self):
        fx = Fixture(self)
        fx.served.write_bytes(fx.payload)
        result = fx.run_update_step()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("step-returned", result.stdout)
        self.assertEqual(fx.archive.read_bytes(), fx.payload)
        self.assertTrue(fx.receipt.exists())

    def test_failed_download_warns_and_the_update_carries_on(self):
        fx = Fixture(self)
        fx.curl_fail.touch()
        result = fx.run_update_step()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("step-returned", result.stdout)
        self.assertIn("next one tries again", result.stderr)
        self.assertFalse(fx.archive.exists())

    def test_bad_digest_and_installer_failure_fail_the_update(self):
        for case in ("digest", "installer"):
            with self.subTest(case=case):
                fx = Fixture(self)
                if case == "digest":
                    fx.served.write_bytes(b"z" * len(fx.payload))
                else:
                    fx.served.write_bytes(fx.payload)
                    fx.closure_fail.touch()
                result = fx.run_update_step()
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("step-returned", result.stdout)
                self.assertIn("the Ollama runtime installation failed", result.stderr)

    def test_provisioner_without_the_step_is_reported_not_fatal(self):
        fx = Fixture(self)
        fx.install_provisioner(under(PROVISION.read_text(), fx.root).replace(
            "install_ollama_runtime_for_update() {", "renamed_ollama_runtime_for_update() {"))
        fx.served.write_bytes(fx.payload)
        result = fx.run_update_step()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cannot install the Ollama", result.stderr)
        self.assertEqual(fx.call_lines(), [])

    def test_unsafe_provisioner_is_refused(self):
        fx = Fixture(self)
        fx.prov.chmod(0o777)
        fx.served.write_bytes(fx.payload)
        result = fx.run_update_step()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(fx.call_lines(), [])

    def test_step_runs_after_the_dependency_refresh_inside_the_transaction(self):
        text = UPDATE.read_text()
        main = text[text.rindex("\nbegin_stack_transaction\n"):]
        # Called once, from the main sequence only.
        self.assertEqual(text.count("\ninstall_ollama_runtime_update\n"), 1)
        step = main.index("\ninstall_ollama_runtime_update\ntest_fail_after_boundary ollama-runtime\n")
        self.assertLess(main.index("\nrefresh_os_dependencies\n"), step)
        self.assertLess(main.index("\nself_update_os_layer\n"), step)
        self.assertLess(main.index("\ninstall_model_setup_software\n"), step)
        self.assertLess(step, main.index("apply_selected_native_runtime"))
        self.assertLess(step, main.index("commit_stack_transaction"))
        # Its own step, apart from Neuronte's.
        self.assertNotIn("install_ollama_runtime_update", self.function(text, "install_neuronte_update"))
        # It uses first boot's install without naming it (see test_ollama_reprovision).
        self.assertNotIn("install_ollama_runtime_from_carrier", text)
        # The image-model root step must not install it a second time.
        self.assertIn('--install-paradee-runtime \\\n        --no-ollama-runtime \\\n', text)

    @staticmethod
    def function(text: str, name: str) -> str:
        start = text.index(f"{name}() {{")
        return text[start:text.index("\n}\n", start)]


class RC8UpdaterShimTests(unittest.TestCase):
    """RC8's updater has no Ollama step; it runs RC9's --install-paradee-runtime as root."""

    def setUp(self):
        self.models = load_image_models()

    def shim_run(self, fx):
        def run(argv, env, **kwargs):
            return subprocess.run(argv, env={**fx.env(), **env, "PATH": f"{fx.shims}:{env['PATH']}"},
                                  **kwargs)
        return run

    def call(self, fx):
        return self.models.install_ollama_runtime_for_an_older_updater(
            provisioner=fx.prov, version="0.2.3", safe=lambda path: True, run=self.shim_run(fx))

    def test_shim_installs_the_missing_runtime(self):
        fx = Fixture(self)
        fx.served.write_bytes(fx.payload)
        self.assertEqual(self.call(fx), 0)
        self.assertEqual(fx.archive.read_bytes(), fx.payload)
        self.assertTrue(fx.receipt.exists())
        self.assertIn(f"curl {URL}", fx.call_lines())

    def test_shim_reports_a_failed_download_and_continues(self):
        fx = Fixture(self)
        fx.curl_fail.touch()
        self.assertEqual(self.call(fx), 0)
        self.assertFalse(fx.archive.exists())

    def test_shim_fails_on_a_bad_carrier_or_installer_failure(self):
        fx = Fixture(self)
        fx.served.write_bytes(b"z" * len(fx.payload))
        with self.assertRaisesRegex(ValueError, "Ollama runtime installation failed"):
            self.call(fx)
        fx = Fixture(self)
        fx.served.write_bytes(fx.payload)
        fx.closure_fail.touch()
        with self.assertRaisesRegex(ValueError, "Ollama runtime installation failed"):
            self.call(fx)

    def test_shim_skips_a_provisioner_without_the_step(self):
        fx = Fixture(self)
        fx.install_provisioner(under(PROVISION.read_text(), fx.root).replace(
            "install_ollama_runtime_for_update() {", "renamed_ollama_runtime_for_update() {"))
        calls = []
        result = self.models.install_ollama_runtime_for_an_older_updater(
            provisioner=fx.prov, version="0.2.3", safe=lambda path: True,
            run=lambda *a, **k: calls.append(a))
        self.assertEqual(result, 0)
        self.assertEqual(calls, [])

    def test_shim_refuses_an_unsafe_provisioner(self):
        fx = Fixture(self)
        calls = []
        with self.assertRaisesRegex(ValueError, "missing or unsafe"):
            self.models.install_ollama_runtime_for_an_older_updater(
                provisioner=fx.prov, version="0.2.3", run=lambda *a, **k: calls.append(a))
        self.assertEqual(calls, [])

    def test_root_control_check(self):
        check = self.models.provisioner_is_root_controlled
        self.assertTrue(check(Path("/usr/bin/env")))
        with tempfile.TemporaryDirectory() as td:
            mine = Path(td) / "provision"
            mine.write_text("#!/bin/sh\n")
            self.assertFalse(check(mine))
            self.assertTrue(check(mine, owner=os.getuid()) is False)  # / is not ours
            link = Path(td) / "link"
            link.symlink_to("/usr/bin/env")
            self.assertFalse(check(link))
        self.assertFalse(check(Path("/nonexistent/plebian-os-provision")))

    def test_main_runs_the_shim_only_for_an_older_online_updater(self):
        source = IMAGE_MODELS.read_text()
        branch = source[source.index("    if args.install_paradee_runtime:"):]
        branch = branch[:branch.index("    archive = resolve_basic_pitch")]
        self.assertIn("if not args.offline and not args.no_ollama_runtime:", branch)
        self.assertIn("return install_ollama_runtime_for_an_older_updater()", branch)
        # RC8's updater makes exactly this call, with neither flag.
        rc8 = subprocess.run(["git", "-C", str(ROOT), "show", "v0.2.3-rc8:provision/plebian-os-update.sh"],
                             capture_output=True, text=True, check=False)
        if rc8.returncode != 0:
            self.skipTest("v0.2.3-rc8 is not in this clone")
        self.assertIn('"$PLEBIAN_OS_DIR/provision/install-image-models.py" --install-paradee-runtime \\\n'
                      '        || die "required Paradee runtime staging failed"', rc8.stdout)
        self.assertNotIn("install_ollama_runtime", rc8.stdout)

    def test_main_parses_the_flag(self):
        argv = []
        original = self.models.install_paradee_runtime
        shim = self.models.install_ollama_runtime_for_an_older_updater
        try:
            self.models.install_paradee_runtime = lambda *a, **k: argv.append("paradee")
            self.models.install_ollama_runtime_for_an_older_updater = lambda: argv.append("ollama") or 0
            self.assertEqual(self.models.main(["--install-paradee-runtime", "--no-ollama-runtime"]), 0)
            self.assertEqual(argv, ["paradee"])
            self.assertEqual(self.models.main(["--install-paradee-runtime", "--offline"]), 0)
            self.assertEqual(argv, ["paradee", "paradee"])
            self.assertEqual(self.models.main(["--install-paradee-runtime"]), 0)
            self.assertEqual(argv, ["paradee", "paradee", "paradee", "ollama"])
        finally:
            self.models.install_paradee_runtime = original
            self.models.install_ollama_runtime_for_an_older_updater = shim


class OllamaCarrierPinTests(unittest.TestCase):
    def test_release_pins_the_published_asset_beside_its_size_and_digest(self):
        values = manifest_values(ENV)
        self.assertEqual(values["PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_URL"], [URL])
        self.assertEqual(values["PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_BYTES"], ["20689764"])
        self.assertEqual(values["PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_SHA256"],
                         ["47cdb94ae64351242aee2e4391e87de1c7ff7f8cb579006b8dfd56353aaa6914"])
        self.assertRegex(URL, URL_PATTERN)
        generation = re.search(r'^GENERATION_NAME = "([^"]+)"$', INSTALLER.read_text(), re.M).group(1)
        self.assertEqual(URL.rsplit("/", 1)[1], generation + ".tar.xz")

    def test_requirements_bind_the_whole_triple(self):
        env, requirements = manifest_values(ENV), manifest_values(REQUIREMENTS)
        for key in ("PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_URL", "PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_BYTES",
                    "PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_SHA256"):
            self.assertEqual(requirements[key], env[key], key)

    def test_every_check_accepts_the_same_url_shape(self):
        provision = PROVISION.read_text()
        self.assertIn(f"OLLAMA_CARRIER_URL_PATTERN='{URL_PATTERN}'", provision)
        remaster = REMASTER.read_text()
        self.assertIn(f'=~ {URL_PATTERN} ]]', remaster)
        update = UPDATE.read_text()
        self.assertIn('r"https://github\\.com/itsmygithubacct/plebian-os/releases/download/"\n'
                      '        r"[A-Za-z0-9._-]+/ollama-0\\.32\\.14-kilix-unix-vulkan-r1\\.tar\\.xz", url)',
                      update)

    def run_deploy_validator(self, manifest_text: str):
        text = UPDATE.read_text()
        start = text.index("<<'PY_MANIFEST'\n") + len("<<'PY_MANIFEST'\n")
        program = text[start:text.index("\nPY_MANIFEST\n", start)]
        with tempfile.TemporaryDirectory() as td:
            manifest, version = Path(td) / "m.env", Path(td) / "VERSION"
            manifest.write_text(manifest_text)
            version.write_text("0.2.3\n")
            return subprocess.run(["python3", "-", str(manifest), str(version)], input=program,
                                  capture_output=True, text=True, check=False)

    def test_deployed_manifest_url_is_optional_but_canonical(self):
        base = ("PLEBIAN_OS_VERSION=0.2.3\nPLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_BYTES=20689764\n"
                "PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_SHA256=" + "a" * 64 + "\n")
        self.assertEqual(self.run_deploy_validator(base).returncode, 0)
        good = base + f"PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_URL={URL}\n"
        self.assertEqual(self.run_deploy_validator(good).returncode, 0)
        self.assertEqual(self.run_deploy_validator(ENV.read_text()).returncode, 0)
        for bad in (URL.replace("https:", "http:"), URL + "?x", URL.replace("itsmygithubacct", "other")):
            result = self.run_deploy_validator(base + f"PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_URL={bad}\n")
            self.assertNotEqual(result.returncode, 0, bad)
            self.assertIn("invalid selected Ollama carrier URL pin", result.stderr)
        result = self.run_deploy_validator(good + f"PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_URL={URL}\n")
        self.assertIn("duplicate selected Ollama manifest field", result.stderr)

    def test_remaster_records_it_in_build_info_and_clears_it_for_older_closures(self):
        remaster = REMASTER.read_text()
        self.assertIn('manifest_kv PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_URL '
                      '"${PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_URL:-}"', remaster)
        loader = remaster[remaster.index("load_release_manifest() {"):]
        loader = loader[:loader.index("while IFS= read -r line")]
        self.assertIn("    PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_URL=\n", loader)

    def test_release_notes_say_upgrades_install_it(self):
        notes = NOTES.read_text()
        self.assertIn("Install the pinned Ollama runtime on upgrade", notes)
        self.assertIn("`PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_URL`", notes)


if __name__ == "__main__":
    unittest.main()
