"""Root-filesystem transaction coverage for ``plebian-os-provision``.

The provisioner is sourced in library mode and pointed at an isolated tree.
The production script does not accept those path overrides; they exist here so
real EXIT failures can exercise the same snapshot, restore, and commit code
without touching the host's /etc or /usr trees.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROVISION = ROOT / "provision" / "plebian-os-provision.sh"


class ProvisionRootTransactionTests(unittest.TestCase):
    maxDiff = None

    def _run(self, body: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "bash",
                "-c",
                "set -euo pipefail\n"
                "export PLEBIAN_OS_PROVISION_LIB_ONLY=1\n"
                f"source {str(PROVISION)!r}\n"
                + body,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    @staticmethod
    def _quoted(path: Path) -> str:
        return repr(str(path))

    def _layout(self, root: Path) -> tuple[str, dict[str, Path]]:
        managed = root / "managed"
        nested = managed / "nested"
        created = managed / "created"
        state = root / "state"
        nested.mkdir(parents=True)
        state.mkdir()
        existing = nested / "existing.conf"
        link = nested / "published-link"
        new = created / "new.conf"
        existing.write_text("before\n")
        existing.chmod(0o640)
        link.symlink_to("old-target")
        paths = {
            "root": root,
            "managed": managed,
            "nested": nested,
            "created": created,
            "state": state,
            "existing": existing,
            "link": link,
            "new": new,
            "sudoers": root / "temporary-sudoers",
        }
        q = self._quoted
        setup = (
            f"PROVISION_ROOT_TRANSACTION_BASE={q(state)}\n"
            f"PROVISION_ROOT_TRANSACTION_TRUSTED_DIRS=({q(root)})\n"
            "PROVISION_ROOT_TRANSACTION_MANAGED_DIRS=("
            f"{q(managed)} {q(nested)} {q(created)})\n"
            "PROVISION_ROOT_TRANSACTION_PATHS=("
            f"{q(existing)} {q(link)} {q(new)})\n"
            f"SUDOERS={q(paths['sudoers'])}\n"
            "TARGET_USER=\n"
        )
        return setup, paths

    def test_exit_failure_restores_files_links_modes_and_absence(self):
        with tempfile.TemporaryDirectory() as td:
            setup, paths = self._layout(Path(td))
            q = self._quoted
            result = self._run(
                setup
                + "begin_provision_root_transaction\n"
                + f"printf 'after\\n' > {q(paths['existing'])}\n"
                + f"chmod 0600 {q(paths['existing'])}\n"
                + f"rm -f {q(paths['link'])}\n"
                + f"ln -s new-target {q(paths['link'])}\n"
                + f"mkdir -p {q(paths['created'])}\n"
                + f"printf 'new\\n' > {q(paths['new'])}\n"
                + "exit 41\n"
            )
            self.assertEqual(result.returncode, 41, result.stderr)
            self.assertEqual(paths["existing"].read_text(), "before\n")
            self.assertEqual(paths["existing"].stat().st_mode & 0o777, 0o640)
            self.assertTrue(paths["link"].is_symlink())
            self.assertEqual(os.readlink(paths["link"]), "old-target")
            self.assertFalse(paths["new"].exists())
            self.assertFalse(paths["created"].exists())
            self.assertEqual(list(paths["state"].glob("provision-rollback.*")), [])
            self.assertIn("restored the pre-provision", result.stdout)

    def test_each_induced_failure_boundary_rolls_back_prior_writes(self):
        for boundary in ("assets", "helpers", "session"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as td:
                setup, paths = self._layout(Path(td))
                q = self._quoted
                mutations = [
                    f"printf 'changed\\n' > {q(paths['existing'])}\n",
                    f"mkdir -p {q(paths['created'])}\n"
                    f"printf 'created\\n' > {q(paths['new'])}\n",
                    f"rm -f {q(paths['link'])}\n"
                    f"ln -s changed-target {q(paths['link'])}\n",
                ]
                count = {"assets": 1, "helpers": 2, "session": 3}[boundary]
                result = self._run(
                    setup
                    + "begin_provision_root_transaction\n"
                    + "".join(mutations[:count])
                    + f"die 'injected provisioning failure after {boundary}'\n"
                )
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(paths["existing"].read_text(), "before\n")
                self.assertTrue(paths["link"].is_symlink())
                self.assertEqual(os.readlink(paths["link"]), "old-target")
                self.assertFalse(paths["new"].exists())
                self.assertFalse(paths["created"].exists())
                self.assertEqual(
                    list(paths["state"].glob("provision-rollback.*")), []
                )

    def test_commit_keeps_new_state_and_removes_recovery_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            setup, paths = self._layout(Path(td))
            q = self._quoted
            result = self._run(
                setup
                + "begin_provision_root_transaction\n"
                + f"printf 'committed\\n' > {q(paths['existing'])}\n"
                + f"mkdir -p {q(paths['created'])}\n"
                + f"printf 'kept\\n' > {q(paths['new'])}\n"
                + "commit_provision_root_transaction\n"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(paths["existing"].read_text(), "committed\n")
            self.assertEqual(paths["new"].read_text(), "kept\n")
            self.assertEqual(list(paths["state"].glob("provision-rollback.*")), [])
            self.assertIn("committed the root filesystem transaction", result.stdout)

    def test_uncommitted_clean_exit_is_rolled_back_and_cannot_report_success(self):
        with tempfile.TemporaryDirectory() as td:
            setup, paths = self._layout(Path(td))
            q = self._quoted
            result = self._run(
                setup
                + "begin_provision_root_transaction\n"
                + f"printf 'not-committed\\n' > {q(paths['existing'])}\n"
                + "exit 0\n"
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(paths["existing"].read_text(), "before\n")
            self.assertEqual(list(paths["state"].glob("provision-rollback.*")), [])

    def test_unsafe_automatic_restore_retains_recovery_and_returns_70(self):
        with tempfile.TemporaryDirectory() as td:
            setup, paths = self._layout(Path(td))
            q = self._quoted
            result = self._run(
                setup
                + "begin_provision_root_transaction\n"
                + f"rm -f {q(paths['existing'])}\n"
                + f"mkdir {q(paths['existing'])}\n"
                + "exit 55\n"
            )
            self.assertEqual(result.returncode, 70, result.stderr)
            recovery = list(paths["state"].glob("provision-rollback.*"))
            self.assertEqual(len(recovery), 1)
            self.assertTrue((recovery[0] / "items" / "0").is_file())
            self.assertIn("rollback was incomplete", result.stderr)

    def test_production_inventory_covers_every_root_file_mutation_family(self):
        body = (
            "printf '%s\\n' \"${PROVISION_ROOT_TRANSACTION_PATHS[@]}\"\n"
            "printf '%s\\n' --DIRS--\n"
            "printf '%s\\n' \"${PROVISION_ROOT_TRANSACTION_MANAGED_DIRS[@]}\"\n"
        )
        result = self._run(body)
        self.assertEqual(result.returncode, 0, result.stderr)
        paths_text, dirs_text = result.stdout.split("--DIRS--\n", 1)
        paths = set(paths_text.splitlines())
        dirs = set(dirs_text.splitlines())
        required_paths = {
            "/etc/modprobe.d/plebian-os-no-beep.conf",
            "/etc/systemd/system.conf.d/50-plebian-os-quiet-console.conf",
            "/usr/local/share/plebian-os/wallpapers/plebian-os.png",
            "/usr/local/share/plebian-os/VERSION",
            "/etc/lightdm/lightdm-gtk-greeter.conf.d/50-plebian-os.conf",
            "/usr/local/share/doc/plebian-os/COPYING.GPL-2",
            "/usr/local/share/doc/plebian-os/installer/ATTRIBUTION.md",
            "/usr/local/sbin/plebian-os-passwd",
            "/usr/lib/plebian-os/waydroid/plebian-os-waydroid-setup",
            "/usr/lib/plebian-os/waydroid/waydroid-closure.env",
            "/usr/lib/plebian-os/waydroid/waydroid-closure.sha256",
            "/etc/sudoers.d/plebian-os-passwd",
            "/usr/local/bin/pleb-session",
            "/usr/share/xsessions/pleb.desktop",
            "/usr/local/bin/kilix",
            "/usr/local/bin/pleb",
            "/etc/lightdm/lightdm.conf.d/50-plebian-os.conf",
            "/etc/lightdm/lightdm.conf.d/50-pleb-autologin.conf",
            "/etc/pleb/session.env",
            "/etc/sudoers.d/plebian-os-nopasswd",
            "/var/lib/plebian-os/packages.list",
            "/var/lib/plebian-os/versions.env",
            "/var/lib/plebian-os/apt-sources.list",
        }
        self.assertTrue(required_paths <= paths, required_paths - paths)
        self.assertNotIn("/etc/sudoers.d/plebian-os-provision", paths)
        self.assertIn("/usr/local/share/doc/plebian-os/installer", dirs)
        self.assertIn("/usr/lib/plebian-os/waydroid", dirs)
        self.assertIn("/etc/pleb", dirs)

        account = self._run(
            "TARGET_USER=pleb\n"
            "prepare_provision_root_transaction_paths\n"
            "printf '%s\\n' \"${PROVISION_ROOT_TRANSACTION_PATHS[-1]}\"\n"
        )
        self.assertEqual(account.returncode, 0, account.stderr)
        self.assertEqual(
            account.stdout.strip(), "/var/lib/AccountsService/users/pleb"
        )

    def test_main_transaction_window_starts_before_files_and_commits_last(self):
        source = PROVISION.read_text()
        dependencies = source.rindex(
            'bash "$DEPS_SCRIPT" || die "dependency install failed'
        )
        begun = source.rindex("\nbegin_provision_root_transaction\n")
        first_file = source.rindex("\ninstall_no_beep_defaults\n")
        pleb_install = source.rindex('"$PLEB_DIR/bin/pleb" install')
        provenance = source.rindex("\nwrite_source_tool_manifest\n")
        committed = source.rindex("\ncommit_provision_root_transaction\n")
        cleaned = source.rindex("\ncleanup\ntrap - EXIT INT TERM HUP\n")
        self.assertLess(dependencies, begun)
        self.assertLess(begun, first_file)
        self.assertLess(first_file, pleb_install)
        self.assertLess(pleb_install, provenance)
        self.assertLess(provenance, committed)
        self.assertLess(committed, cleaned)


if __name__ == "__main__":
    unittest.main()
