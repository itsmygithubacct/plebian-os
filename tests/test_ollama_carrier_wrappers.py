import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMASTER = ROOT / "build" / "remaster-iso.sh"


class OllamaCarrierWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = REMASTER.read_text()
        start = source.index("resolve_ollama_carrier() {")
        end = source.index("\ndefault_iso_name=", start)
        cls.resolver = source[start:end]

    def run_resolver(self, argument=None, configured=None):
        harness = (
            "set -euo pipefail\n"
            + self.resolver
            + '\nresolve_ollama_carrier "${1:-}"\n'
            + 'printf "%s\\n" "$OLLAMA_CARRIER"\n'
        )
        argv = ["bash", "-c", harness, "carrier-resolver-test"]
        if argument is not None:
            argv.append(str(argument))
        env = os.environ.copy()
        env.pop("PLEBIAN_OS_OLLAMA_CARRIER", None)
        if configured is not None:
            env["PLEBIAN_OS_OLLAMA_CARRIER"] = str(configured)
        return subprocess.run(argv, env=env, text=True, capture_output=True)

    def test_remaster_selects_argument_or_environment_and_canonicalizes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            carrier = root / "carrier.tar.xz"
            alias = root / "carrier-alias.tar.xz"
            carrier.write_bytes(b"carrier")
            alias.symlink_to(carrier)

            env_only = self.run_resolver(configured=alias)
            self.assertEqual(env_only.returncode, 0, env_only.stderr)
            self.assertEqual(env_only.stdout.strip(), str(carrier))

            argument_only = self.run_resolver(argument=carrier)
            self.assertEqual(argument_only.returncode, 0, argument_only.stderr)
            self.assertEqual(argument_only.stdout.strip(), str(carrier))

            same_file = self.run_resolver(argument=carrier, configured=alias)
            self.assertEqual(same_file.returncode, 0, same_file.stderr)
            self.assertEqual(same_file.stdout.strip(), str(carrier))

            different = root / "different.tar.xz"
            different.write_bytes(b"different")
            mismatch = self.run_resolver(argument=carrier, configured=different)
            self.assertNotEqual(mismatch.returncode, 0)
            self.assertIn("resolve to different files", mismatch.stderr)

            missing = self.run_resolver(configured=root / "missing.tar.xz")
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("PLEBIAN_OS_OLLAMA_CARRIER is missing", missing.stderr)

    def test_building_wrapper_dry_runs_show_the_shared_carrier(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            carrier = root / "carrier input.tar.xz"
            env = os.environ.copy()
            env.update({
                "HOME": td,
                "PLEBIAN_OS_OLLAMA_CARRIER": str(carrier),
                "PLEBIAN_OS_RELEASE": "0.2.2",
                "PLEBIAN_OS_ARTIFACTS": str(root / "artifacts"),
                "PLEBIAN_OS_CACHE": str(root / "cache"),
                "PLEBIAN_OS_SESSION_HOME": str(root / "session"),
            })
            env.pop("PLEBIAN_OS_VM_PASSWORD", None)

            usb = subprocess.run(
                ["bash", str(ROOT / "build" / "make-usb.sh"), "--dry-run"],
                env=env, text=True, capture_output=True,
            )
            self.assertEqual(usb.returncode, 0, usb.stderr)
            self.assertIn(f"Ollama carrier: {carrier}", usb.stdout)
            self.assertIn("remaster-iso.sh", usb.stdout)

            usb_builder = subprocess.run(
                [sys.executable, str(ROOT / "build" / "build_usb_image.py"),
                 "--yes", "--dry-run", "--out", str(root / "usb.iso")],
                env=env, text=True, capture_output=True,
            )
            self.assertEqual(usb_builder.returncode, 0, usb_builder.stderr)
            self.assertIn(f"Ollama carrier: {carrier}", usb_builder.stdout)
            self.assertIn(str(carrier), usb_builder.stdout)

            vm_from_usb = subprocess.run(
                ["bash", str(ROOT / "build" / "install-vm-from-usb-iso.sh"),
                 "--dry-run"],
                env={**env, "PLEBIAN_OS_VM_ISO": str(root / "usb.iso")},
                text=True, capture_output=True,
            )
            self.assertEqual(vm_from_usb.returncode, 0, vm_from_usb.stderr)
            self.assertIn(f"Ollama carrier: {carrier}", vm_from_usb.stdout)
            self.assertIn("VM not started", vm_from_usb.stdout)

            vm_builder = subprocess.run(
                [sys.executable, str(ROOT / "build" / "build_vm_image.py"),
                 "--yes", "--dry-run", "--username", "operator",
                 "--hostname", "test-host", "--generate-one-time-password",
                 "--sudo-nopasswd", "--out", str(root / "vm.iso")],
                env=env, text=True, capture_output=True,
            )
            self.assertEqual(vm_builder.returncode, 0, vm_builder.stderr)
            self.assertIn(f"Ollama carrier: {carrier}", vm_builder.stdout)
            self.assertIn(str(carrier), vm_builder.stdout)
            self.assertIn("would now create + boot the VM", vm_builder.stdout)

    def test_acceptance_and_prebuilt_iso_wrappers_report_the_carrier_contract(self):
        acceptance_vm = (ROOT / "build" / "acceptance-vm.sh").read_text()
        self.assertIn('PLEBIAN_OS_OLLAMA_CARRIER:-<unset; required for 0.2.2>',
                      acceptance_vm)
        self.assertIn('exec "$HERE/build_vm_image.py"', acceptance_vm)
        self.assertNotIn("unset PLEBIAN_OS_OLLAMA_CARRIER", acceptance_vm)

        acceptance_iso = (ROOT / "build" / "acceptance-release-iso.sh").read_text()
        self.assertIn(
            "embedded Ollama carrier ollama-0.32.14-kilix-unix-vulkan-r1.tar.xz",
            acceptance_iso,
        )
        self.assertIn("PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_BYTES", acceptance_iso)
        self.assertIn("PLEBIAN_OS_OLLAMA_RUNTIME_CARRIER_SHA256", acceptance_iso)
        self.assertNotIn('"$HERE/remaster-iso.sh"', acceptance_iso)

    def test_release_docs_pin_and_publish_the_carrier_asset(self):
        docs = (ROOT / "RELEASING.md").read_text()
        for expected in (
            "PLEBIAN_OS_OLLAMA_CARRIER",
            "ollama-0.32.14-kilix-unix-vulkan-r1.tar.xz",
            "20,689,764",
            "47cdb94ae64351242aee2e4391e87de1c7ff7f8cb579006b8dfd56353aaa6914",
            "SHA256SUMS",
            "verified Kilix Ollama source closure",
            "tagged source checkout",
            "this carrier asset can rebuild the ISO",
        ):
            self.assertIn(expected, docs)

    def test_ci_workflows_do_not_build_iso_without_the_external_carrier(self):
        workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertTrue(workflows)
        for workflow in workflows:
            source = workflow.read_text()
            for invocation in ("remaster-iso.sh", "make-usb.sh",
                               "acceptance-vm.sh", "build_usb_image.py"):
                self.assertNotIn(invocation, source, workflow.name)
if __name__ == "__main__":
    unittest.main()
