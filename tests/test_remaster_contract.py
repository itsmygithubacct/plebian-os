import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMASTER = ROOT / "build" / "remaster-iso.sh"


class RemasterContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = REMASTER.read_text()

    def test_firstboot_environment_is_a_subset_of_build_provenance(self):
        manifest = set(re.findall(r"manifest_kv ([A-Z0-9_]+)", self.source))
        runtime = set(re.findall(r"env_kv ([A-Z0-9_]+)", self.source))
        self.assertTrue(runtime)
        self.assertFalse(runtime - manifest,
                         f"runtime keys missing from build-info: {runtime - manifest}")
        for key in ("PLEBIAN_OS_AUTOBOOT", "PLEBIAN_OS_UNATTENDED_DISK"):
            self.assertIn(key, manifest)

    def test_effective_preseed_controls_release_ssh_safety(self):
        self.assertIn("sed '/^[[:space:]]*#/d' \"$PRESEED\"", self.source)
        self.assertIn("(ssh-server|openssh-server)", self.source)
        self.assertIn("PLEBIAN_OS_SSH_ENABLED=1", self.source)
        self.assertIn("effective preseed that installs SSH", self.source)

    def test_release_runtime_self_update_uses_resolved_commit(self):
        self.assertIn('runtime_os_ref="$(git -C "$HERE" rev-parse HEAD', self.source)
        self.assertIn('env_kv PLEBIAN_OS_REF "$runtime_os_ref"', self.source)

    def test_release_mode_requires_complete_immutable_input_closure(self):
        for key in (
            "PLEBIAN_OS_REF", "PLEBIAN_OS_NETINST_URL",
            "PLEBIAN_OS_NETINST_SHA256", "PLEBIAN_OS_APT_SNAPSHOT",
            "PLEB_REF", "KILIX_REF", "KILIX95_REF",
            "KILIX_PREBUILT_VERSION", "KILIX_PREBUILT_SHA256",
            "PLEBIAN_OS_KILIX_GO_VERSION",
            "PLEBIAN_OS_KILIX_GO_SHA256_AMD64",
            "PLEBIAN_OS_KILIX_GO_SHA256_ARM64",
        ):
            self.assertIn(key, self.source)
        self.assertIn("status --porcelain --untracked-files=normal", self.source)
        self.assertIn('${PLEBIAN_OS_REF}^{commit}', self.source)

    def test_snapshot_covers_installer_and_firstboot(self):
        self.assertIn("mirror/http/hostname string snapshot.debian.org", self.source)
        self.assertIn("/archive/debian/$ts", self.source)
        self.assertIn("preseed/early_command", self.source)
        self.assertIn("02plebian-snapshot", self.source)
        self.assertIn("plebian-os-apt-snapshot-generator", self.source)
        mkdir = self.source.index("mkdir -p /usr/lib/apt-setup/generators")
        install = self.source.index(
            "install -m 0755 /cdrom/plebian-os/plebian-os-apt-snapshot-generator")
        self.assertLess(mkdir, install)

    def test_output_is_same_filesystem_staged_and_boot_validated(self):
        self.assertIn('refusing to overwrite the source ISO', self.source)
        self.assertIn('refusing to use a block device as ISO output', self.source)
        self.assertIn('mktemp -d --tmpdir="$(dirname "$OUT_ISO")"', self.source)
        self.assertIn("rebuilt ISO has no BIOS El Torito boot image", self.source)
        self.assertIn("rebuilt ISO has no UEFI El Torito boot image", self.source)
        self.assertIn("rebuilt ISO lacks an isohybrid MBR signature", self.source)

    def test_installer_late_command_cannot_mask_failure(self):
        preseed = (ROOT / "preseed" / "preseed.cfg").read_text()
        late = preseed.split("d-i preseed/late_command string", 1)[1]
        self.assertIn("set -e;", late)
        self.assertNotRegex(late, r";\s*\\?\s*true\s*$")

    def test_snapshot_generator_writes_target_apt_policy(self):
        generator = ROOT / "provision" / "plebian-os-apt-snapshot-generator"
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root = base / "target"
            marker = base / "generator-output"
            subprocess.run(
                ["sh", str(generator), str(marker)],
                env={**os.environ, "ROOT": str(root)}, check=True,
            )
            policy = root / "etc" / "apt" / "apt.conf.new"
            self.assertEqual(policy.read_text(),
                             'Acquire::Check-Valid-Until "false";\n')
            self.assertIn("snapshot validity policy", marker.read_text())


if __name__ == "__main__":
    unittest.main()
