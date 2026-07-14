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

    def assert_in_order(self, source, *markers):
        cursor = 0
        for marker in markers:
            position = source.find(marker, cursor)
            self.assertNotEqual(
                position,
                -1,
                f"missing or out-of-order remaster marker: {marker!r}",
            )
            cursor = position + len(marker)

    def source_section(self, start_marker, end_marker):
        start = self.source.index(start_marker)
        end = self.source.index(end_marker, start + len(start_marker))
        return self.source[start:end]

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

    def test_tracked_installer_assets_are_validated_before_iso_mutation(self):
        validation = (
            'python3 "$INSTALLER_BRANDER" validate-assets '
            '"$INSTALLER_ASSETS"'
        )
        compact = " ".join(re.sub(r"\\\n\s*", " ", self.source).split())
        splash_call = (
            'replace_installer_asset "$INSTALLER_ASSETS/splash.png" '
            '"$EXTRACT/isolinux/splash.png"'
        )
        self.assertIn(
            'INSTALLER_ASSETS="$HERE/assets/installer"', self.source
        )
        self.assertIn(
            'INSTALLER_BRANDER="$HERE/build/brand-installer.py"', self.source
        )
        self.assertEqual(self.source.count(validation), 1)
        self.assertIn(f"\n{validation}\n", self.source)
        self.assertNotIn("/home/", self.source)
        self.assert_in_order(
            compact,
            validation,
            'xorriso -osirrox on -indev "$SRC_ISO" -extract / "$EXTRACT"',
            splash_call,
        )

    def test_dynamic_boot_branding_replaces_the_shared_splash(self):
        patch_command = (
            'python3 "$INSTALLER_BRANDER" patch-text "$EXTRACT" '
            '"$PLEBIAN_OS_VERSION"'
        )
        compact = " ".join(re.sub(r"\\\n\s*", " ", self.source).split())
        splash_call = (
            'replace_installer_asset "$INSTALLER_ASSETS/splash.png" '
            '"$EXTRACT/isolinux/splash.png"'
        )
        self.assertEqual(self.source.count(patch_command), 1)
        self.assertIn(f"\n{patch_command}\n", self.source)
        self.assertIn(splash_call, compact)

        replace = self.source_section(
            "replace_installer_asset() {", "\nbrand_graphical_installer() {"
        )
        for marker in (
            '[ -f "$src" ]',
            '[ -f "$dest" ] && [ ! -L "$dest" ]',
            'mode="$(stat -c \'%a\' "$dest")"',
        ):
            self.assertIn(marker, replace)
        self.assert_in_order(
            replace,
            'touch --reference="$dest" "$metadata_ref"',
            'mode="$(stat -c \'%a\' "$dest")"',
            'install -m "$mode" "$src" "$dest"',
            'touch --reference="$metadata_ref" "$dest"',
        )

        self.assert_in_order(
            self.source,
            'chmod -R u+w "$EXTRACT"',
            '"$INSTALLER_ASSETS/splash.png"',
            patch_command,
            "\nbrand_graphical_installer\n",
            'cp "$PRESEED" "$EXTRACT/preseed.cfg"',
            "add_bootarg() {",
        )

    def test_graphical_installer_overlay_is_deterministic_and_exactly_two_files(self):
        graphical = self.source_section(
            "brand_graphical_installer() {",
            '\nBUILD_PRESEED="$WORK/preseed.cfg"',
        )
        compact = " ".join(re.sub(r"\\\n\s*", " ", graphical).split())

        self.assertIn(
            'install -m 0644 "$INSTALLER_ASSETS/banner.png" '
            '"$overlay/usr/share/graphics/logo_debian.png"',
            compact,
        )
        self.assertIn(
            'install -m 0644 "$INSTALLER_ASSETS/banner-dark.png" '
            '"$overlay/usr/share/graphics/logo_debian_dark.png"',
            compact,
        )
        self.assertEqual(graphical.count("install -m 0644"), 2)
        self.assertIn(
            'touch -d @0 "$overlay/usr/share/graphics/logo_debian.png" '
            '"$overlay/usr/share/graphics/logo_debian_dark.png"',
            compact,
        )

        archive_start = graphical.index("printf '%s\\0'")
        archive_end = graphical.index("| LC_ALL=C cpio", archive_start)
        command_end = graphical.index(') > "$overlay_cpio"', archive_end)
        archive_command = graphical[archive_end:command_end]
        archived_paths = re.findall(
            r"usr/share/graphics/logo_[a-z_]+\.png",
            graphical[archive_start:archive_end],
        )
        self.assertEqual(
            archived_paths,
            [
                "usr/share/graphics/logo_debian.png",
                "usr/share/graphics/logo_debian_dark.png",
            ],
        )
        for flag in (
            "--null",
            "--create",
            "--format=newc",
            "--owner=0:0",
            "--reproducible",
            "--quiet",
        ):
            self.assertIn(flag, archive_command)
        self.assertIn('gzip -n -9 -c "$overlay_cpio" >> "$combined"', graphical)
        self.assertIn(
            "LC_ALL=C cpio --help 2>&1 | grep -q -- '--reproducible'",
            self.source,
        )

    def test_graphical_overlay_validates_source_prefix_and_both_payloads(self):
        graphical = self.source_section(
            "brand_graphical_installer() {",
            '\nBUILD_PRESEED="$WORK/preseed.cfg"',
        )
        inventory_start = graphical.index("for path in", graphical.index("cpio -it"))
        inventory_end = graphical.index("; do", inventory_start)
        inventory_paths = re.findall(
            r"usr/share/graphics/logo_[a-z_]+\.png",
            graphical[inventory_start:inventory_end],
        )
        self.assertEqual(
            inventory_paths,
            [
                "usr/share/graphics/logo_debian.png",
                "usr/share/graphics/logo_debian_dark.png",
                "usr/share/graphics/logo_installer.png",
                "usr/share/graphics/logo_installer_dark.png",
            ],
        )
        self.assertIn('grep -Fxq "$path" "$inventory"', graphical)

        self.assert_in_order(
            graphical,
            'original_size="$(stat -c \'%s\' "$initrd")"',
            'cp --preserve=mode,timestamps "$initrd" "$combined"',
            'chmod u+w "$combined"',
            'gzip -n -9 -c "$overlay_cpio" >> "$combined"',
            'gzip -t "$combined"',
            'cmp -n "$original_size" "$initrd" "$combined"',
            "for path in logo_debian.png logo_debian_dark.png; do",
            'tail -c "+$((original_size + 1))" "$combined"',
            "| gzip -dc",
            '| cpio -i --quiet --to-stdout "usr/share/graphics/$path"',
            '| cmp - "$asset"',
            'touch --reference="$initrd" "$combined"',
            'chmod "$mode" "$combined"',
            'mv -f "$combined" "$initrd"',
        )
        self.assertIn(
            'logo_debian.png) asset="$INSTALLER_ASSETS/banner.png"',
            graphical,
        )
        self.assertIn(
            'logo_debian_dark.png) asset="$INSTALLER_ASSETS/banner-dark.png"',
            graphical,
        )

    def test_build_info_records_all_installer_asset_hashes(self):
        build_info = self.source_section(
            "write_build_info() {", "\nwrite_firstboot_env() {"
        )
        contracts = (
            (
                "splash_sha",
                "splash.png",
                "PLEBIAN_OS_INSTALLER_SPLASH_SHA256",
            ),
            (
                "banner_sha",
                "banner.png",
                "PLEBIAN_OS_INSTALLER_BANNER_SHA256",
            ),
            (
                "banner_dark_sha",
                "banner-dark.png",
                "PLEBIAN_OS_INSTALLER_BANNER_DARK_SHA256",
            ),
        )
        for variable, filename, key in contracts:
            hash_assignment = (
                f'{variable}="$(sha256sum "$INSTALLER_ASSETS/{filename}" '
                f"| awk '{{print $1}}')\""
            )
            manifest_entry = f'manifest_kv {key} "${variable}"'
            self.assertIn(hash_assignment, build_info)
            self.assertEqual(build_info.count(manifest_entry), 1)
            self.assertLess(
                build_info.index(hash_assignment),
                build_info.index(manifest_entry),
            )

        wallpaper_hash = (
            'desktop_wallpaper_sha="$(sha256sum "$DESKTOP_WALLPAPER" '
            "| awk '{print $1}')\""
        )
        wallpaper_entry = (
            'manifest_kv PLEBIAN_OS_DESKTOP_WALLPAPER_SHA256 '
            '"$desktop_wallpaper_sha"'
        )
        self.assertIn(wallpaper_hash, build_info)
        self.assertEqual(build_info.count(wallpaper_entry), 1)
        self.assertLess(
            build_info.index(wallpaper_hash),
            build_info.index(wallpaper_entry),
        )

        for variable, source, key in (
            (
                "installer_attribution_sha",
                "$INSTALLER_ATTRIBUTION",
                "PLEBIAN_OS_INSTALLER_ATTRIBUTION_SHA256",
            ),
            (
                "gpl2_license_sha",
                "$GPL2_LICENSE",
                "PLEBIAN_OS_GPL2_LICENSE_SHA256",
            ),
        ):
            assignment = (
                f'{variable}="$(sha256sum "{source}" | awk \'{{print $1}}\')"'
            )
            entry = f'manifest_kv {key} "${variable}"'
            self.assertIn(assignment, build_info)
            self.assertEqual(build_info.count(entry), 1)
            self.assertLess(build_info.index(assignment), build_info.index(entry))

    def test_distribution_notices_are_staged_at_fixed_media_paths(self):
        contracts = (
            (
                'install -m 0644 "$INSTALLER_ATTRIBUTION" '
                '"$EXTRACT/plebian-os/doc/installer/ATTRIBUTION.md"',
                "/cdrom/plebian-os/doc/installer/ATTRIBUTION.md",
                "/usr/local/share/doc/plebian-os/installer/ATTRIBUTION.md",
            ),
            (
                'install -m 0644 "$GPL2_LICENSE" '
                '"$EXTRACT/plebian-os/doc/COPYING.GPL-2"',
                "/cdrom/plebian-os/doc/COPYING.GPL-2",
                "/usr/local/share/doc/plebian-os/COPYING.GPL-2",
            ),
        )
        preseed = (ROOT / "preseed" / "preseed.cfg").read_text()
        for stage, media, installed in contracts:
            self.assertIn(stage, self.source)
            self.assertIn(media, preseed)
            self.assertIn(installed, preseed)
            self.assertIn(f"chmod 0644 /target{installed}", preseed)

    def test_media_checksum_refresh_follows_all_mutations_and_precedes_repack(self):
        refresh = 'python3 "$INSTALLER_BRANDER" refresh-md5 "$EXTRACT"'
        repack = 'xorriso -as mkisofs "${mkisofs_argv[@]}" -o "$OUT_TMP" "$EXTRACT"'
        self.assertEqual(self.source.count(refresh), 1)
        self.assertEqual(self.source.count(repack), 1)
        self.assertIn(f"\n{refresh}\n", self.source)
        refresh_position = self.source.index(refresh)

        mutation_markers = (
            '"$INSTALLER_ASSETS/splash.png"',
            'python3 "$INSTALLER_BRANDER" patch-text "$EXTRACT"',
            "\nbrand_graphical_installer\n",
            'cp "$PRESEED" "$EXTRACT/preseed.cfg"',
            'write_build_info "$EXTRACT/plebian-os/build-info.env"',
            'write_firstboot_env "$EXTRACT/plebian-os/firstboot.env"',
            'for cfg in "$EXTRACT"/isolinux/*.cfg',
            'sed -i "/vmlinuz/ s#\\(vmlinuz\\)#\\1 $BOOTARGS#"',
            "printf 'timeout 50\\nontimeout install\\n' >> "
            '"$EXTRACT/isolinux/isolinux.cfg"',
            "sed -i 's/^set timeout=.*/set timeout=5/'",
        )
        for marker in mutation_markers:
            self.assertIn(marker, self.source)
            self.assertLess(
                self.source.rindex(marker),
                refresh_position,
                f"mutation occurs after media-check refresh: {marker!r}",
            )

        repack_position = self.source.index(repack, refresh_position)
        self.assertLess(refresh_position, repack_position)
        between = self.source[
            refresh_position + len(refresh):repack_position
        ]
        self.assertNotIn(
            "$EXTRACT",
            between,
            "ISO tree is touched after checksum refresh and before repack",
        )

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
