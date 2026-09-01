import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(*parts):
    return (ROOT.joinpath(*parts)).read_text()


class ReleaseVersioningTests(unittest.TestCase):
    @property
    def version(self):
        return (ROOT / "VERSION").read_text().strip()

    @property
    def manifest(self):
        path = ROOT / "releases" / f"{self.version}.env"
        if not path.exists():
            self.skipTest(
                f"coordinated {self.version} pin manifest is finalized only "
                "after all component release commits exist"
            )
        return path.read_text()

    def test_version_file_is_semver(self):
        self.assertRegex((ROOT / "VERSION").read_text().strip(), r"^\d+\.\d+\.\d+$")
        self.assertIn(f"## [{self.version}]", _read("CHANGELOG.md"))

    def test_0_1_9_release_notes_document_the_upgrade_path(self):
        notes_path = ROOT / "releases" / "0.1.9-notes.md"
        self.assertTrue(notes_path.is_file())
        notes = notes_path.read_text()
        self.assertIn("Supported upgrade source: **0.1.8**", notes)
        self.assertIn("No direct skip from an earlier release is supported", notes)
        self.assertIn(
            "fetch --force origin 'refs/tags/v0.1.9:refs/tags/v0.1.9'",
            notes,
        )
        self.assertIn(
            'show v0.1.9:provision/plebian-os-select-closure.sh >"$SEL"',
            notes,
        )
        self.assertIn('bash "$SEL" 0.1.9 --source "$SRC" --dry-run', notes)
        self.assertIn('bash "$SEL" 0.1.9 --source "$SRC"', notes)
        self.assertNotIn(
            '"$SRC/provision/plebian-os-select-closure.sh" 0.1.9', notes)
        self.assertIn("plebian-os-update --restart", notes)
        self.assertIn("### Upgrade acceptance result", notes)
        self.assertIn("kilix.speech.models/v1", notes)
        self.assertIn("PLEBIAN_OS_INSTALL_VOICE_MODEL=1", notes)
        releasing = _read("RELEASING.md")
        # These two facts move every release. Pinning them to a literal version
        # inside a 0.1.9 test made RELEASING.md unupdatable: the document stayed
        # on "0.1.9 / next is 0.2.0" through the whole of 0.2.0 and 0.2.1
        # because correcting it broke this test. Derive them from VERSION so the
        # check stays strong and the document stays true.
        self.assertIn(
            f"last published coordinated release is **{self.version}**",
            releasing)
        self.assertRegex(
            releasing, r"next planned release is\s+\*\*\d+\.\d+\.\d+\*\*")

    def test_0_2_0_release_notes_define_the_candidate_contract(self):
        notes = _read("releases", "0.2.0-notes.md")
        self.assertIn("Supported upgrade source: **0.1.9**", notes)
        self.assertIn("No direct skip from an earlier release is supported", notes)
        for heading in (
            "## User-visible changes", "## Compatibility and migration",
            "## Third-party closure", "## Support limits",
            "## Known deferrals", "## Upgrade acceptance result",
        ):
            self.assertIn(heading, notes)
        self.assertIn(
            "4a331173caf36b3235679715e153e4154b85651f", notes
        )
        self.assertIn(
            "f61337589bb130e796ead18fd9fca4a8850fae25", notes
        )
        self.assertIn(
            "4ad7a4d44eef6ce4e90173491d0c6c8da02b3764d0d20d1df67ca7eeaa7e4175",
            notes,
        )
        self.assertIn(
            "fetch --force origin 'refs/tags/v0.2.0:refs/tags/v0.2.0'",
            notes,
        )
        self.assertIn('bash "$SEL" 0.2.0 --source "$SRC" --dry-run', notes)
        self.assertIn('bash "$SEL" 0.2.0 --source "$SRC"', notes)

    def test_release_manifest_pins_refs(self):
        m = self.manifest
        self.assertIn("PLEBIAN_OS_RELEASE_MODE=1", m)
        self.assertIn(f"PLEBIAN_OS_REF=v{self.version}", m)
        for key in ("PLEB_REF", "KILIX_REF", "KILIX95_REF"):
            self.assertRegex(m, rf"(?m)^{key}=[0-9a-f]{{40}}$")

    def test_release_manifest_pins_kilix_95_as_first_page(self):
        m = self.manifest
        for key, value in (
            ("PLEBIAN_OS_DESKTOP", "1"),
            ("PLEBIAN_OS_KIOSK", "0"),
            ("KILIX_DESKTOP_PROVIDER", "external"),
            ("KILIX_DESKTOP_FLAVOR", "95"),
            ("KILIX_RUN_ALIASES", "1"),
        ):
            self.assertRegex(m, rf"(?m)^{key}={value}$")

    def test_release_manifest_checksums_are_filled(self):
        m = self.manifest
        # no pin VALUE is still a placeholder (comments may mention REPLACE_ME)
        self.assertFalse(re.search(r"^\w+=REPLACE_ME$", m, re.M))
        self.assertTrue(re.search(r"^KILIX_PREBUILT_VERSION=\d+\.\d+", m, re.M))
        for key in (
            "KILIX_PREBUILT_SHA256", "PLEBIAN_OS_NETINST_SHA256",
            "PLEBIAN_OS_KILIX_GO_SHA256_AMD64",
            "PLEBIAN_OS_KILIX_GO_SHA256_ARM64",
        ):
            self.assertTrue(re.search(rf"^{key}=[0-9a-f]{{64}}$", m, re.M),
                            f"{key} should be a real sha256")
        self.assertRegex(m, r"(?m)^PLEBIAN_OS_NETINST_URL=https://")
        self.assertRegex(m, r"(?m)^PLEBIAN_OS_APT_SNAPSHOT=\d{8}T\d{6}Z$")
        self.assertRegex(m, r"(?m)^PLEBIAN_OS_KILIX_GO_VERSION=go\d+\.\d+\.\d+$")

    def test_remaster_loads_release_manifest(self):
        r = _read("build", "remaster-iso.sh")
        self.assertIn("load_release_manifest", r)
        self.assertIn("PLEBIAN_OS_RELEASE", r)
        self.assertIn("REPLACE_ME", r)

    def test_release_iso_defaults_include_version_and_architecture(self):
        r = _read("build", "remaster-iso.sh")
        self.assertIn(
            'default_iso_name="plebian-os-$PLEBIAN_OS_VERSION-amd64.iso"', r)
        make_usb = _read("build", "make-usb.sh")
        self.assertIn(
            'default_iso_name="plebian-os-$release_iso_version-amd64.iso"',
            make_usb,
        )
        import sys
        from unittest import mock
        sys.path.insert(0, str(ROOT / "build"))
        import build_vm_image as vm

        with mock.patch.dict(os.environ, {
            "PLEBIAN_OS_RELEASE_MODE": "1",
            "PLEBIAN_OS_VERSION": "9.8.7",
        }, clear=False):
            os.environ.pop("PLEBIAN_OS_RELEASE", None)
            self.assertEqual(
                vm.default_iso_filename("custom"),
                "plebian-os-9.8.7-amd64.iso",
            )
        with mock.patch.dict(os.environ, {
            "PLEBIAN_OS_RELEASE_MODE": "0",
        }, clear=False):
            self.assertEqual(
                vm.default_iso_filename("custom"),
                "plebian-os-custom.iso",
            )

    def test_shell_release_manifest_overrides_ambient_bypass_values(self):
        source = _read("build", "remaster-iso.sh")
        start = source.index("load_release_manifest() {")
        end = source.index('[ -n "${PLEBIAN_OS_RELEASE:-}" ]', start)
        loader = source[start:end]
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "releases").mkdir()
            (repo / "VERSION").write_text("9.8.7\n")
            (repo / "releases" / "9.8.7.env").write_text(
                "PLEBIAN_OS_VERSION=9.8.7\n"
                "PLEBIAN_OS_RELEASE_MODE=1\n"
                "PLEB_REF=" + "a" * 40 + "\n"
            )
            harness = (
                "set -euo pipefail\n"
                f"HERE={repo!s}\n"
                f"{loader}\n"
                "PLEBIAN_OS_RELEASE_MODE=0\n"
                "PLEB_REF=ambient-bypass\n"
                "load_release_manifest 9.8.7\n"
                "printf '%s\\n%s\\n' \"$PLEBIAN_OS_RELEASE_MODE\" \"$PLEB_REF\"\n"
            )
            result = subprocess.run(
                ["bash", "-c", harness], text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.splitlines()[-2:], ["1", "a" * 40])

    def test_python_release_manifest_overrides_ambient_bypass_values(self):
        import sys
        from unittest import mock
        sys.path.insert(0, str(ROOT / "build"))
        import build_vm_image as vm

        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "releases").mkdir()
            (repo / "VERSION").write_text("9.8.7\n")
            (repo / "releases" / "9.8.7.env").write_text(
                "PLEBIAN_OS_VERSION=9.8.7\n"
                "PLEBIAN_OS_RELEASE_MODE=1\n"
                "PLEB_REF=" + "b" * 40 + "\n"
            )
            with mock.patch.object(vm, "REPO", repo), mock.patch.dict(
                    os.environ,
                    {"PLEBIAN_OS_RELEASE_MODE": "0", "PLEB_REF": "ambient-bypass"},
                    clear=False):
                vm.apply_release_manifest("9.8.7")
                self.assertEqual(os.environ["PLEBIAN_OS_RELEASE_MODE"], "1")
                self.assertEqual(os.environ["PLEB_REF"], "b" * 40)

    def test_python_0_2_1_loader_requires_complete_f120_roots(self):
        import sys
        from unittest import mock
        sys.path.insert(0, str(ROOT / "build"))
        import build_vm_image as vm

        requirements = {
            "PLEBIAN_OS_INSTALL_UV": "1",
            "PLEBIAN_OS_UV_VERSION": "0.12.5",
            "PLEBIAN_OS_UV_INSTALLER_SHA256":
                "504511fbbbd811aeaba6738abc79408956b6c7da0ca35437b3dcc24a41efc111",
            "PLEBIAN_OS_UV_INSTALLER_MAX_BYTES": "71225",
        }
        values = {
            "PLEBIAN_OS_VERSION": "0.2.1",
            "PLEBIAN_OS_RELEASE_MODE": "1",
            **requirements,
        }
        for index, (root, repo_url) in enumerate(
                vm.F120_ROOT_REPOS.items(), start=1):
            values[f"{root}_REF"] = str(index) * 40
            values[f"{root}_REPO"] = repo_url
            values[f"{root}_BRANCH"] = ""

        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            releases = repo / "releases"
            releases.mkdir()
            (repo / "VERSION").write_text("0.2.1\n")
            manifest = releases / "0.2.1.env"
            manifest.write_text("".join(
                f"{key}={value}\n" for key, value in values.items()))
            (releases / "0.2.1.requirements").write_text("".join(
                f"{key}={value}\n" for key, value in requirements.items()))

            with mock.patch.object(vm, "REPO", repo), mock.patch.dict(
                    os.environ, {}, clear=False):
                vm.apply_release_manifest("0.2.1")
                for key in vm.F120_ROOT_KEYS:
                    self.assertEqual(os.environ[key], values[key])

                del values["KILIX_MEDIA_SDK_REF"]
                manifest.write_text("".join(
                    f"{key}={value}\n" for key, value in values.items()))
                with self.assertRaises(SystemExit):
                    vm.apply_release_manifest("0.2.1")

    def test_remaster_records_version_and_runtime_config(self):
        # build-info + firstboot env must carry the version and the previously
        # missing security-relevant runtime knobs (provenance completeness).
        r = _read("build", "remaster-iso.sh")
        for key in ("PLEBIAN_OS_VERSION", "PLEBIAN_OS_KIOSK", "PLEBIAN_OS_USER",
                    "PLEBIAN_OS_NOPASSWD_SUDO", "PLEBIAN_OS_INSTALL_UV",
                    "PLEBIAN_OS_APT_SNAPSHOT", "PLEBIAN_OS_REPO", "PLEBIAN_OS_REF"):
            self.assertIn(key, r)

    def test_release_installs_and_reasserts_public_version_marker(self):
        remaster = _read("build", "remaster-iso.sh")
        preseed = _read("preseed", "preseed.cfg")
        provision = _read("provision", "plebian-os-provision.sh")
        self.assertIn(
            'install -m 0644 "$HERE/VERSION" "$EXTRACT/plebian-os/VERSION"',
            remaster,
        )
        marker = "/target/usr/local/share/plebian-os/VERSION"
        self.assertIn(f"cp /cdrom/plebian-os/VERSION {marker}", preseed)
        self.assertIn(f"chown root:root {marker}", preseed)
        self.assertIn(f"chmod 0644 {marker}", preseed)
        self.assertIn("install_version_marker", provision)
        self.assertIn("/etc/plebian-os/build-info.env", provision)
        self.assertIn("VERSION_MARKER_DST=/usr/local/share/plebian-os/VERSION", provision)

    def test_unpinned_remaster_defaults_match_release_session_contract(self):
        r = _read("build", "remaster-iso.sh")
        self.assertEqual(r.count('${PLEBIAN_OS_DESKTOP:-1}'), 2)
        self.assertEqual(r.count('${KILIX_DESKTOP_FLAVOR:-95}'), 2)
        self.assertEqual(r.count('${KILIX_RUN_ALIASES:-1}'), 2)

    def test_gui_routing_defaults_inside_kilix_and_preserves_opt_out(self):
        provision = _read("provision", "plebian-os-provision.sh")
        updater = _read("provision", "plebian-os-update.sh")
        acceptance = _read("build", "build_vm_image.py")
        self.assertIn(
            'KILIX_RUN_ALIASES="${KILIX_RUN_ALIASES:-1}"', provision)
        self.assertIn(
            'KILIX_RUN_ALIASES="${KILIX_RUN_ALIASES:-1}"', updater)
        self.assertRegex(
            updater,
            r'if \[\[ ! "\$config_text" =~ .*KILIX_RUN_ALIASES.*\]\]; then\n'
            r'\s+names\+=\(KILIX_RUN_ALIASES\)\n\s+values\+=\(1\)',
        )
        self.assertIn('"GUI routes in Kilix"', acceptance)
        self.assertIn("alias chromium | grep -Fq ' run chromium'", acceptance)
        for path in (
            '$KILIX_DIR/tests/test_kilix_bashrc.py',
            '$KILIX_DIR/desktop/tests/test_shell_xpane.py',
            '$KILIX95_DIR/tests/run.py',
        ):
            self.assertIn(path, acceptance)
        self.assertIn('"Kilix-95 GUI routing tests"', acceptance)
        self.assertIn('shell_xpane', acceptance)
        self.assertIn('timeout=check_timeouts.get(name, 15)', acceptance)

    def test_release_mode_warns_on_unpinned_apt(self):
        r = _read("build", "remaster-iso.sh")
        self.assertIn("PLEBIAN_OS_APT_SNAPSHOT", r)
        self.assertIn("snapshot.debian.org", r)

    def test_provisioner_persists_self_update_knobs(self):
        p = _read("provision", "plebian-os-provision.sh")
        for key in ("PLEBIAN_OS_VERSION", "PLEBIAN_OS_REPO",
                    "PLEBIAN_OS_REF", "PLEBIAN_OS_APT_SNAPSHOT"):
            self.assertIn(f"write_session_default {key}", p)

    def test_provisioner_has_apt_snapshot_and_manifest(self):
        p = _read("provision", "plebian-os-provision.sh")
        self.assertIn("configure_apt_snapshot", p)
        self.assertIn("write_package_manifest", p)
        self.assertIn("snapshot.debian.org", p)
        self.assertIn("/var/lib/plebian-os/packages.list", p)

    def test_update_helper_self_updates_os_layer(self):
        u = _read("provision", "plebian-os-update.sh")
        self.assertIn("self_update_os_layer", u)
        self.assertIn("update_os_checkout", u)
        self.assertIn("PLEBIAN_OS_SELF_UPDATE", u)
        self.assertIn("install -m 0755", u)
        self.assertIn("/usr/local/sbin/plebian-os-provision", u)
        # the password-nag helper is an OS-layer script too — it must redeploy
        self.assertIn("/usr/local/sbin/plebian-os-passwd", u)
        # the target-closure selector is the twelfth transactional payload
        self.assertIn("/usr/local/bin/plebian-os-select-closure", u)
        # Exact pins are resolved from the object returned by origin rather
        # than a potentially poisoned local tag, then deployed transactionally.
        self.assertIn(
            'checkout_pinned_ref "$PLEBIAN_OS_DIR" "$PLEBIAN_OS_REF" "plebian-os"',
            u,
        )
        self.assertIn("FETCH_HEAD^{commit}", u)
        self.assertIn("deploy_staged_os_layer", u)
        self.assertIn("systemctl daemon-reload", u)

    def test_python_builders_forward_version_and_release(self):
        vm = _read("build", "build_vm_image.py")
        self.assertIn("apply_release_manifest", vm)
        self.assertIn("PLEBIAN_OS_VERSION", vm)
        # apply_release_manifest populates every coordinated pin (including
        # PLEBIAN_OS_REPO); inheriting os.environ into remaster forwards them
        # without maintaining a second, drift-prone key list here.
        self.assertIn("{**os.environ", vm)
        usb = _read("build", "build_usb_image.py")
        self.assertIn("vm.apply_release_manifest()", usb)

    def test_release_docs_present(self):
        self.assertTrue((ROOT / "RELEASING.md").exists())
        self.assertTrue((ROOT / "CHANGELOG.md").exists())
        self.assertTrue((ROOT / "UPGRADING.md").exists())
        self.assertTrue(
            (ROOT / "releases" / f"{self.version}-notes.md").exists()
        )

    def test_current_release_notes_track_the_exact_source_closure(self):
        notes = _read("releases", f"{self.version}-notes.md")
        manifest = self.manifest
        for key in ("PLEB_REF", "KILIX_REF", "KILIX95_REF"):
            match = re.search(rf"(?m)^{key}=([0-9a-f]{{40}})$", manifest)
            self.assertIsNotNone(match, key)
            self.assertIn(match.group(1), notes)
        self.assertIn(f"`v{self.version}`", notes)
        self.assertIn("fresh-install baseline", notes)
        self.assertIn("attached provenance record is the final artifact\nacceptance record", notes)
        self.assertIn("earlier local candidate ISO", notes)

        changelog = _read("CHANGELOG.md")
        heading = re.search(
            rf"(?m)^## \[{re.escape(self.version)}\](?: — ([0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}))?$",
            changelog,
        )
        self.assertIsNotNone(heading)
        self.assertIsNotNone(heading.group(1))
        section_end = changelog.find("\n## ", heading.end())
        current_section = changelog[
            heading.start():section_end if section_end != -1 else None
        ]
        self.assertNotRegex(current_section, r"(?i)\bunreleased\b")

    def test_upgrade_policy_starts_with_0_1_7_and_requires_preservation(self):
        policy = json.loads(
            _read("releases", "upgrade-policy.json")
        )
        self.assertEqual(policy["schema_version"], 1)
        self.assertEqual(policy["upgrade_baseline"], "0.1.7")
        self.assertEqual(
            policy["pre_baseline_action"], "fresh_install_required"
        )
        self.assertEqual(
            policy["default_supported_hop"],
            "immediately_previous_published_release",
        )
        self.assertEqual(
            policy["published_release_skip"],
            "explicit_path_and_acceptance_required",
        )
        self.assertEqual(
            policy["upgrade_entrypoint"],
            "installed_updater_with_target_release_closure",
        )
        self.assertEqual(
            policy["release_controlled_keys_move_as"],
            "one_coordinated_closure",
        )
        for required in (
            "user_files",
            "gpu_terminal_application_state",
            "game_saves",
            "operator_session_choices",
            "shared_settings",
        ):
            self.assertIn(required, policy["preserve"])
        self.assertEqual(
            policy["failure_result"],
            "previous_coherent_stack_and_configuration_restored",
        )
        self.assertTrue(all(policy["release_gate"].values()))

    def test_upgrade_docs_retire_the_pre_baseline_bridge(self):
        readme = _read("README.md")
        releasing = _read("RELEASING.md")
        upgrading = _read("UPGRADING.md")
        self.assertNotIn("Upgrading from v0.1.1", readme)
        self.assertNotIn("documented v0.1.1 migration", releasing)
        self.assertIn("0.1.2 to 0.1.7 is not a supported", upgrading)
        self.assertIn("immediately previous published release", upgrading)
        self.assertIn("induced mid-transaction failure", upgrading)

    def test_0_1_2_historical_manifest_tracks_the_published_artifacts(self):
        manifest = _read("releases", "0.1.2.env")
        expected = {
            "PLEBIAN_OS_REF":
                "96016f0eee8b652f13c377fa84c842bed98b0f8c",
            "PLEB_REF":
                "20c5cff3655cf95efb96dc7a7e855257dc6ccc2e",
            "KILIX_REF":
                "0cf52e81e481a45b103548373f52ee5c73e0e8eb",
            "KILIX95_REF":
                "8ac7aa65e3df4d08cc31e020ee0517b9087c6d4c",
        }
        for key, commit in expected.items():
            self.assertRegex(manifest, rf"(?m)^{key}={commit}$")
        self.assertNotRegex(manifest, r"(?m)^PLEBIAN_OS_REF=v0\.1\.2$")

        provenance_path = ROOT / "releases" / "0.1.2-provenance.md"
        provenance = provenance_path.read_bytes()
        provenance_hash = hashlib.sha256(provenance).hexdigest()
        self.assertEqual(
            provenance_hash,
            "959797398d3f4031dae067322407ac4f959467956f586f46dce039ac3f946b5d",
        )
        provenance_text = provenance.decode("utf-8")
        notes = _read("releases", "0.1.2-notes.md")
        for commit in expected.values():
            self.assertIn(commit, provenance_text)
            self.assertIn(commit, notes)
        for artifact_hash in (
            "cedd3f933171f4ce5166f88a8cc35a08e2c12a207101b3f72a92be743844e1a4",
            "7788ba540745f028976ba22a04620a2a5d6b71d35ca3f0182048e7d7dd38dd73",
            "59ed4e44e0a96ccd0dec143bfe6cdc1a3941ee3d5f6655f1f763ab7775b290c4",
        ):
            self.assertIn(artifact_hash, provenance_text)
            self.assertIn(artifact_hash, notes)
        self.assertIn(provenance_hash, notes)
        self.assertIn("The published tags are not moved", provenance_text)

    def test_release_manifest_omits_the_retired_shared_login(self):
        manifest = self.manifest
        self.assertNotRegex(manifest, r"(?m)^IMAGE_PASSWORD=")
        self.assertNotRegex(manifest, r"(?m)^RANDOM_PASSWORD=")

    def test_acceptance_binds_instrumented_image_to_clean_candidate(self):
        source = (ROOT / "build" / "acceptance-vm.sh").read_text()
        self.assertIn('PLEBIAN_OS_ACCEPTANCE_RAM:-4096', source)
        self.assertIn('releases/$PLEBIAN_OS_ACCEPTANCE_RELEASE.env', source)
        self.assertIn("rev-parse --verify 'HEAD^{commit}'", source)
        self.assertIn('rev-parse --verify "${manifest_os_ref}^{commit}"', source)
        self.assertIn('cat-file -t "refs/tags/$manifest_os_ref"', source)
        self.assertIn('[ "$candidate_commit" = "$manifest_commit" ]', source)
        self.assertIn('status --porcelain --untracked-files=normal', source)
        self.assertIn('PLEBIAN_OS_REF="$candidate_commit"', source)
        self.assertIn('PLEBIAN_OS_RELEASE_MODE=0', source)
        self.assertIn('PLEBIAN_OS_RELEASE=', source)
        self.assertIn('unset IMAGE_PASSWORD RANDOM_PASSWORD', source)
        self.assertIn('--generate-one-time-password', source)
        self.assertIn('--sudo-nopasswd', source)
        self.assertIn('--username "$ACCEPTANCE_USER"', source)
        self.assertIn('--hostname "$ACCEPTANCE_HOSTNAME"', source)
        self.assertIn('PLEBIAN_OS_VERIFY_CATALOG_BUILDS=1', source)
        self.assertIn('PLEBIAN_OS_VERIFY_UPDATE_ROLLBACK=1', source)
        self.assertIn('PLEBIAN_OS_VERIFY_SUCCESSFUL_UPDATE=1', source)
        self.assertIn('plebian-acceptance-${PLEBIAN_OS_ACCEPTANCE_RELEASE}-${candidate_short}', source)
        self.assertIn('plebian-os-${PLEBIAN_OS_ACCEPTANCE_RELEASE}-${candidate_short}-acceptance.json', source)
        self.assertIn('--report "$REPORT"', source)
        self.assertNotIn('--replace', source)

    def test_exact_release_iso_lane_validates_and_covers_bios_and_efi(self):
        path = ROOT / "build" / "acceptance-release-iso.sh"
        source = path.read_text()
        self.assertTrue(path.stat().st_mode & 0o111)
        for key in (
            "PLEBIAN_OS_VERSION",
            "PLEBIAN_OS_RELEASE",
            "PLEBIAN_OS_RELEASE_MODE",
            "PLEBIAN_OS_DIRTY",
            "PLEBIAN_OS_COMMIT",
            "PLEBIAN_OS_SSH_ENABLED",
            "PLEBIAN_OS_AUTOBOOT",
            "PLEBIAN_OS_UNATTENDED_DISK",
        ):
            self.assertIn(key, source)
        self.assertIn("El Torito boot img.*BIOS", source)
        self.assertIn("El Torito boot img.*UEFI", source)
        self.assertIn('PLEBIAN-OS $RELEASE AMD64', source)
        self.assertIn('cat-file -t "refs/tags/v$RELEASE"', source)
        self.assertIn('read_kv_file "$stage/build-info.env"', source)
        self.assertIn('read_kv_file "$manifest"', source)
        self.assertIn('for key in "${!release_manifest[@]}"', source)
        self.assertNotIn('. "$1"', source)
        self.assertIn("firmwares=(bios efi)", source)
        self.assertIn('--firmware "$firmware"', source)
        self.assertIn("--interactive-installer", source)
        self.assertIn("--no-wait --no-verify", source)
        self.assertIn('--report "$report"', source)
        self.assertNotIn("--password plebian", source)
        self.assertIn("manifest must omit retired key", source)


if __name__ == "__main__":
    unittest.main()
