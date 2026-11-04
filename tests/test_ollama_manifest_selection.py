"""Execute source paths with tiny carrier fixtures; no guest or model runs."""
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest

import test_ollama_reprovision as fixtures
import test_lid_update as snapshots

extract_shell_function = fixtures.extract_shell_function

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "provision/plebian-os-install-kilix-ollama-runtime"
VERSIONS = ("0.2.2", "0.2.2.1", "0.2.3")


def run_shell(source, **variables):
    prelude = "set -euo pipefail\n"
    prelude += 'die() { printf "%s\\n" "$*" >&2; exit 1; }\n'
    prelude += "\n".join(f"{name}={shlex.quote(str(value))}" for name, value in variables.items())
    return subprocess.run(["bash", "-c", prelude + "\n" + source],
                          text=True, capture_output=True, timeout=15)


class OllamaManifestSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.OllamaCarrierPreflightTests.setUpClass()
        cls.probes = fixtures.OllamaCarrierPreflightTests()
        cls.remaster = (ROOT / "build/remaster-iso.sh").read_text()
        start = cls.remaster.index("ollama_carrier_required() {")
        end = cls.remaster.index('if [ -z "$SRC_ISO" ]; then', start)
        cls.verify_media = cls.remaster[start:end]
        start = cls.remaster.index('if ollama_carrier_required "$PLEBIAN_OS_VERSION"; then', end)
        end = cls.remaster.index("\nfi", start) + len("\nfi")
        cls.stage_media = cls.remaster[start:end]
        preseed = (ROOT / "preseed/preseed.cfg").read_text()
        start = preseed.index('    ollama_version="$(cat /cdrom/plebian-os/VERSION)"')
        end = preseed.index('    if [ -f /cdrom/plebian-os/ollama-runtime-carrier.tar.xz ]', start)
        cls.copy_media = preseed[start:end].replace("\\\n", "\n")
        cls.updater = (ROOT / "provision/plebian-os-update.sh").read_text()
        start = cls.updater.index('    install -m 0644 "$PLEBIAN_OS_DIR/VERSION" "$stage/VERSION"')
        end = cls.updater.index('    install -m 0644 "$PLEBIAN_OS_DIR/assets/desktop/', start)
        cls.stage_update = "stage_manifest() {\n" + cls.updater[start:end] + "\n}\nstage_manifest\n"
        start = cls.updater.index("manifest_index=$((${#new_paths[@]} - 1))")
        end = cls.updater.index("\nPY_MANIFEST", start) + len("\nPY_MANIFEST")
        cls.root_validate = cls.updater[start:end]

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def fixture(self, version):
        root = self.root / version
        fixture = self.probes.make_fixture(root, carrier_payload=f"carrier for {version}\n".encode(),
                                          version=version)
        (fixture["checkout"] / "VERSION").write_text(version + "\n")
        return fixture

    def media(self, fixture):
        media = fixture["root"] / "media"
        media.mkdir(exist_ok=True)
        shutil.copyfile(INSTALLER, fixture["source_installer"])
        return run_shell(self.verify_media + "\n" + self.stage_media,
                         HERE=fixture["checkout"], EXTRACT=media,
                         OLLAMA_CARRIER=fixture["carrier"],
                         PLEBIAN_OS_VERSION=fixture["version"],
                         PLEBIAN_OS_REF="v0.2.3-rc1"), media / "plebian-os"

    def test_numeric_versions_and_explicit_rc_source_tag_select_exact_media_manifest(self):
        for version in VERSIONS:
            with self.subTest(version=version):
                fixture = self.fixture(version)
                (fixture["root"] / "media/plebian-os").mkdir(parents=True)
                result, media = self.media(fixture)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((media / "ollama-release.env").read_bytes(), fixture["manifest"].read_bytes())
                self.assertEqual((media / "ollama-runtime-carrier.tar.xz").read_bytes(), fixture["payload"])

    def test_remaster_never_falls_back_to_another_manifest(self):
        fixture = self.fixture("0.2.3")
        other = fixture["manifest"].with_name("0.2.2.env")
        other.write_text(fixture["manifest"].read_text().replace("0.2.3", "0.2.2"))
        original = fixture["manifest"].read_text()
        cases = (None, original.replace("0.2.3", "0.2.2"),
                 original + "PLEBIAN_OS_VERSION=0.2.3\n",
                 original.replace("PLEBIAN_OS_VERSION=0.2.3\n", ""))
        for value in cases:
            with self.subTest(value=value):
                fixture["manifest"].unlink(missing_ok=True)
                if value is not None:
                    fixture["manifest"].write_text(value)
                result, media = self.media(fixture)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((media / "ollama-release.env").exists())

    def test_remaster_retains_byte_and_hash_checks(self):
        fixture = self.fixture("0.2.2.1")
        for payload in (fixture["payload"] + b"extra", b"x" * len(fixture["payload"])):
            fixture["carrier"].write_bytes(payload)
            result, _ = self.media(fixture)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("release pin", result.stderr)

    def test_preseed_copies_only_a_version_matching_manifest_and_refuses_missing_payload(self):
        for version in VERSIONS:
            with self.subTest(version=version):
                fixture = self.fixture(version)
                media = fixture["root"] / "media"
                target = fixture["root"] / "target"
                media.mkdir()
                target.mkdir()
                (media / "VERSION").write_text(version + "\n")
                manifest = media / "ollama-release.env"
                source = self.copy_media.replace("/cdrom/plebian-os", str(media)).replace(
                    "/target/usr/local/share/plebian-os", str(target))
                # Ownership is covered separately; this source test runs unprivileged.
                source = source.replace("chown root:root ", "true ")
                for value in (None, fixture["manifest"].read_text().replace(version, "9.9.9"),
                              fixture["manifest"].read_text()):
                    manifest.unlink(missing_ok=True)
                    if value is not None:
                        manifest.write_text(value)
                    result = run_shell(source)
                    if value == fixture["manifest"].read_text():
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual((target / manifest.name).read_bytes(), manifest.read_bytes())
                    else:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertFalse((target / manifest.name).exists())

    def test_firstboot_and_bootstrap_preflight_select_version_without_python(self):
        for version in VERSIONS:
            with self.subTest(version=version):
                fixture = self.fixture(version)
                path = self.probes.make_no_python_path(fixture)
                result = self.probes.run_real_entry_prefix(fixture, option=str(fixture["carrier"]), path=path)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((fixture["stage_root"] / "ollama-release.env").read_bytes(),
                                 fixture["manifest"].read_bytes())
                # Exercise bootstrap's real exec boundary with the same bounded
                # provision prefix, stopping before logging/package mutation.
                bootstrap = fixture["checkout"] / "bootstrap.sh"
                shutil.copyfile(ROOT / "bootstrap.sh", bootstrap)
                prefix = self.probes.entry_prefix.replace("/usr/local/share/plebian-os", str(fixture["stage_root"]))
                provisioner = fixture["checkout"] / "provision/plebian-os-provision.sh"
                provisioner.write_text(prefix + '\nprintf "bootstrap-prefix-complete\\n"\n')
                provisioner.chmod(0o755)
                env = {**fixture["env"], "PLEBIAN_OS_VERSION": version,
                       "PLEBIAN_OS_REF": "v0.2.3-rc1", "PATH": str(path)}
                # The executable shebang uses env bash; provide the interpreter
                # while deliberately leaving python3 unavailable.
                (path / "bash").symlink_to("/bin/bash")
                result = subprocess.run(["/bin/bash", str(bootstrap), "--ollama-carrier", str(fixture["carrier"])],
                                        env=env, text=True, capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("bootstrap-prefix-complete", result.stdout)

    def test_firstboot_wrong_missing_duplicate_and_old_only_manifests_refuse_before_mutation(self):
        fixture = self.fixture("0.2.3")
        original = fixture["manifest"].read_text()
        fixture["manifest"].with_name("0.2.2.env").write_text(original.replace("0.2.3", "0.2.2"))
        for value in (None, original.replace("0.2.3", "0.2.2"),
                      original + "PLEBIAN_OS_VERSION=0.2.3\n", original.replace("PLEBIAN_OS_VERSION=0.2.3\n", "")):
            fixture["manifest"].unlink(missing_ok=True)
            if value is not None:
                fixture["manifest"].write_text(value)
            result = self.probes.run_real_entry_prefix(fixture, option=str(fixture["carrier"]))
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(fixture["stage_root"].exists())
            self.assertNotIn("entry-prefix-complete", result.stdout)

    def test_legacy_manifest_only_applies_to_exact_022_and_does_not_override_new_staged_version(self):
        fixture = self.fixture("0.2.2")
        fixture["stage_root"].mkdir(mode=0o755)
        fixture["stage_root"].chmod(0o755)
        old = fixture["stage_root"] / "0.2.2.env"
        old.write_bytes(fixture["manifest"].read_bytes())
        old.chmod(0o644)
        result = self.probes.run_real_entry_prefix(fixture, option=str(fixture["carrier"]))
        self.assertEqual(result.returncode, 0, result.stderr)
        selected = fixture["stage_root"] / "ollama-release.env"
        selected.write_text(old.read_text().replace("0.2.2", "0.2.3"))
        selected.chmod(0o644)
        result = self.probes.run_real_entry_prefix(fixture, option=str(fixture["carrier"]))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("entry-prefix-complete", result.stdout)

    def test_updater_stages_exact_manifest_and_root_rechecks_version_and_pins(self):
        for version in VERSIONS:
            with self.subTest(version=version):
                fixture = self.fixture(version)
                stage = fixture["root"] / "stage"
                stage.mkdir()
                shutil.copyfile(INSTALLER, stage / INSTALLER.name)
                result = run_shell(self.stage_update, PLEBIAN_OS_DIR=fixture["checkout"],
                                   PLEBIAN_OS_VERSION=version, stage=stage)
                self.assertEqual(result.returncode, 0, result.stderr)
                selected = stage / "ollama-release.env"
                original = selected.read_text()
                prelude = 'new_paths=(a b c d e f "$version_file" "$manifest")\n'
                cases = (original, original.replace(version, "9.9.9"),
                         original + "PLEBIAN_OS_VERSION=" + version + "\n",
                         re.sub(r"CARRIER_SHA256=.*", "CARRIER_SHA256=wrong", original),
                         re.sub(r"CARRIER_BYTES=.*", "CARRIER_BYTES=0", original))
                for payload in cases:
                    selected.write_text(payload)
                    result = run_shell(prelude + self.root_validate, manifest=selected,
                                       version_file=stage / "VERSION")
                    self.assertEqual(result.returncode == 0, payload == original, result.stderr)

    def test_updater_missing_selected_manifest_refuses_in_user_stage(self):
        fixture = self.fixture("0.2.3")
        fixture["manifest"].rename(fixture["manifest"].with_name("0.2.2.env"))
        stage = fixture["root"] / "stage"
        stage.mkdir()
        shutil.copyfile(INSTALLER, stage / INSTALLER.name)
        result = run_shell(self.stage_update, PLEBIAN_OS_DIR=fixture["checkout"],
                           PLEBIAN_OS_VERSION=fixture["version"], stage=stage)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((stage / "ollama-release.env").exists())

    def test_manifest_joins_both_snapshot_and_rollback_sets(self):
        for marker in ("<<'ROOT_SNAPSHOT'", "<<'ROOT_RESTORE'"):
            start = self.updater.index(marker)
            end = self.updater.index("\n)", self.updater.index("paths=(", start))
            self.assertIn("/usr/local/share/plebian-os/ollama-release.env", self.updater[start:end])

    def test_real_snapshot_and_rollback_restore_version_and_manifest_together(self):
        for present in (False, True):
            with self.subTest(previous_manifest=present):
                fixture = snapshots.Fixture(self)
                directory = fixture.root / "usr/local/share/plebian-os"
                directory.mkdir()
                directory.chmod(0o755)
                version = directory / "VERSION"
                manifest = directory / "ollama-release.env"
                version.write_text("0.2.2\n")
                version.chmod(0o644)
                if present:
                    manifest.write_text("PLEBIAN_OS_VERSION=0.2.2\n")
                    manifest.chmod(0o644)
                before = (version.read_bytes(), manifest.read_bytes() if present else None)
                snap, restore = snapshots.scripts()
                snap = snapshots.as_user(snapshots.under(snap, fixture.root))
                restore = snapshots.as_user(snapshots.under(restore, fixture.root))
                env = {"PATH": f"{fixture.safe_bin()}:/usr/bin:/bin", "HOME": str(fixture.tmp)}
                result = subprocess.run(["bash", "-c", "set -euo pipefail\n" + snap],
                                        env=env, text=True, capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                transaction = result.stdout.strip().splitlines()[-1]
                version.write_text("0.2.3\n")
                manifest.write_text("PLEBIAN_OS_VERSION=0.2.3\n")
                result = subprocess.run(["bash", "-s", "--", transaction],
                                        input="set -euo pipefail\nsystemctl() { :; }\n" + restore,
                                        env=env, text=True, capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(version.read_bytes(), before[0])
                self.assertEqual(manifest.read_bytes() if manifest.exists() else None, before[1])

    def test_required_carrier_policy_matches_and_invalid_versions_never_skip_preflight(self):
        provision = (ROOT / "provision/plebian-os-provision.sh").read_text()
        helper = extract_shell_function(provision, "ollama_carrier_required")
        self.assertEqual(helper, extract_shell_function(self.remaster, "ollama_carrier_required"))
        for version in (*VERSIONS, "0.3.0", "1.0.0", "0.2.1", "", "../0.2.2", "0.2.3-rc1"):
            result = run_shell(helper + '\nif ollama_carrier_required "$selected"; then echo REQUIRED; else echo LEGACY; fi',
                               selected=version)
            if version in ("", "../0.2.2", "0.2.3-rc1"):
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("LEGACY", result.stdout)
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "LEGACY" if version == "0.2.1" else "REQUIRED")


if __name__ == "__main__":
    unittest.main()
