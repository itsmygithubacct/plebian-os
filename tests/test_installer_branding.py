import binascii
import hashlib
import importlib.util
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "build" / "brand-installer.py"
ASSET_ROOT = ROOT / "assets" / "installer"

SPEC = importlib.util.spec_from_file_location("brand_installer", HELPER)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import machinery guard
    raise RuntimeError(f"cannot load {HELPER}")
brand_installer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = brand_installer
SPEC.loader.exec_module(brand_installer)


def png_chunk(chunk_type, payload, *, corrupt_crc=False):
    crc = binascii.crc32(chunk_type + payload) & 0xFFFFFFFF
    if corrupt_crc:
        crc ^= 0xFFFFFFFF
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", crc)
    )


def png_ihdr(
    width,
    height,
    *,
    bit_depth=8,
    color_type=2,
    compression=0,
    filter_method=0,
    interlace=0,
):
    payload = struct.pack(
        ">IIBBBBB",
        width,
        height,
        bit_depth,
        color_type,
        compression,
        filter_method,
        interlace,
    )
    return png_chunk(b"IHDR", payload)


def rgb8_scanlines(width, height, filters=None):
    if filters is None:
        filters = [0] * height
    if len(filters) != height:
        raise ValueError("one filter byte is required per row")
    pixels = bytes(width * 3)
    return b"".join(bytes([filter_type]) + pixels for filter_type in filters)


def png_image(
    width,
    height,
    *,
    raw=None,
    compressed=None,
    before_idat=(),
    after_idat=(),
    include_idat=True,
    include_iend=True,
    trailing=b"",
    **ihdr_fields,
):
    if raw is None:
        raw = rgb8_scanlines(width, height)
    if compressed is None:
        compressed = zlib.compress(raw)
    chunks = [png_ihdr(width, height, **ihdr_fields), *before_idat]
    if include_idat:
        chunks.append(png_chunk(b"IDAT", compressed))
    chunks.extend(after_idat)
    if include_iend:
        chunks.append(png_chunk(b"IEND", b""))
    return brand_installer.PNG_SIGNATURE + b"".join(chunks) + trailing


def png_from_chunks(*chunks, trailing=b""):
    return brand_installer.PNG_SIGNATURE + b"".join(chunks) + trailing


def write_text_fixture(root):
    menu = root / "isolinux" / "menu.cfg"
    menu.parent.mkdir(parents=True)
    menu.write_bytes(
        b"include stdmenu.cfg\n"
        + brand_installer.BIOS_TITLE
        + b"\nlabel install\n"
    )

    theme_root = root / "boot" / "grub" / "theme"
    theme_root.mkdir(parents=True)
    for name in brand_installer.THEME_NAMES:
        (theme_root / name).write_bytes(
            b'# Debian attribution remains valid\n'
            + brand_installer.UEFI_TITLE
            + b"\n"
            + brand_installer.UEFI_HEADING
            + b"\n"
        )
    (theme_root / "hl_c.png").write_bytes(b"highlight fixture")

    (root / "README.txt").write_bytes(
        b"\r\n".join(
            marker
            for marker, expected in brand_installer.README_TEXT_REQUIRED
            for _ in range(expected)
        )
        + b"\r\n"
    )
    (root / "README.html").write_bytes(
        b"\n".join(
            marker
            for marker, expected in brand_installer.README_HTML_REQUIRED
            for _ in range(expected)
        )
        + b"\n"
    )
    (root / "isolinux" / "f1.txt").write_bytes(
        b"\n".join(
            (
                brand_installer.F1_WELCOME,
                brand_installer.F1_MEDIA,
                brand_installer.F1_BUILD,
                brand_installer.F1_PREREQUISITES,
            )
        )
        + b"\n"
    )
    (root / "isolinux" / "f2.txt").write_bytes(
        b"\n".join(
            (
                brand_installer.F2_HEADING,
                brand_installer.F2_DEBIAN_REQUIREMENTS,
                b"Thank you for choosing Debian!",
            )
        )
        + b"\n"
    )
    (root / "isolinux" / "f9.txt").write_bytes(
        brand_installer.F9_DEBIAN_SUPPORT + b"\n"
    )

    timestamp_ns = 1_650_000_000_123_456_789
    for path in root.rglob("*"):
        if path.is_file():
            os.utime(path, ns=(timestamp_ns, timestamp_ns))
    return menu, theme_root


def tree_bytes(root):
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


class PngContractTests(unittest.TestCase):
    def test_tracked_installer_assets_match_embedding_contract(self):
        brand_installer.validate_installer_assets(ASSET_ROOT)

    def test_accepts_exact_rgb8_noninterlaced_contract(self):
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / "splash.png"
            png.write_bytes(png_image(640, 480))
            ihdr = brand_installer.validate_png_asset(png, 640, 480)
            self.assertEqual((ihdr.width, ihdr.height), (640, 480))
            self.assertEqual(ihdr.bit_depth, 8)
            self.assertEqual(ihdr.color_type, 2)
            self.assertEqual(ihdr.interlace, 0)

    def test_rejects_every_incompatible_ihdr_field(self):
        cases = {
            "width": dict(width=639, height=480),
            "height": dict(width=640, height=479),
            "bit depth": dict(width=640, height=480, bit_depth=16),
            "alpha": dict(width=640, height=480, color_type=6),
            "grayscale": dict(width=640, height=480, color_type=0),
            "compression": dict(width=640, height=480, compression=1),
            "filter": dict(width=640, height=480, filter_method=1),
            "interlace": dict(width=640, height=480, interlace=1),
        }
        for label, fields in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                png = Path(td) / "bad.png"
                fields = fields.copy()
                width = fields.pop("width")
                height = fields.pop("height")
                png.write_bytes(png_image(width, height, **fields))
                with self.assertRaises(brand_installer.BrandingError):
                    brand_installer.validate_png_asset(png, 640, 480)

    def test_rejects_invalid_signature_truncation_chunk_order_and_crc(self):
        valid = png_image(640, 480)
        cases = {
            "signature": b"not-png!" + valid[8:],
            "truncated": valid[:24],
            "chunk order": valid[:12] + b"IDAT" + valid[16:],
            "crc": valid[:29] + bytes([valid[29] ^ 0xFF]) + valid[30:],
        }
        for label, contents in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                png = Path(td) / "bad.png"
                png.write_bytes(contents)
                with self.assertRaises(brand_installer.BrandingError):
                    brand_installer.validate_png_asset(png, 640, 480)

    def test_rejects_truncated_chunks_crc_errors_and_post_iend_data(self):
        width, height = 4, 3
        raw = rgb8_scanlines(width, height)
        compressed = zlib.compress(raw)
        ihdr = png_ihdr(width, height)
        idat = png_chunk(b"IDAT", compressed)
        iend = png_chunk(b"IEND", b"")
        valid = png_from_chunks(ihdr, idat, iend)
        cases = {
            "truncated chunk header": png_from_chunks(ihdr) + b"\x00\x00\x00",
            "truncated chunk data": png_from_chunks(
                ihdr,
                struct.pack(">I", len(compressed) + 4) + b"IDAT" + compressed,
            ),
            "truncated chunk CRC": png_from_chunks(ihdr) + idat[:-2],
            "IDAT CRC": png_from_chunks(
                ihdr,
                png_chunk(b"IDAT", compressed, corrupt_crc=True),
                iend,
            ),
            "IEND CRC": png_from_chunks(
                ihdr,
                idat,
                png_chunk(b"IEND", b"", corrupt_crc=True),
            ),
            "invalid chunk type": png_from_chunks(
                ihdr, png_chunk(b"1DAT", compressed), iend
            ),
            "reserved chunk bit": png_from_chunks(
                ihdr, png_chunk(b"abca", b""), idat, iend
            ),
            "nonempty IEND": png_from_chunks(
                ihdr, idat, png_chunk(b"IEND", b"x")
            ),
            "post-IEND bytes": valid + b"\x00",
        }
        for label, contents in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                png = Path(td) / "bad.png"
                png.write_bytes(contents)
                with self.assertRaises(brand_installer.BrandingError):
                    brand_installer.validate_png_asset(png, width, height)

    def test_rejects_missing_duplicate_and_misordered_critical_chunks(self):
        width, height = 4, 3
        compressed = zlib.compress(rgb8_scanlines(width, height))
        midpoint = len(compressed) // 2
        ihdr = png_ihdr(width, height)
        idat = png_chunk(b"IDAT", compressed)
        iend = png_chunk(b"IEND", b"")
        palette = png_chunk(b"PLTE", b"\x00\x00\x00")
        cases = {
            "missing IHDR": png_from_chunks(idat, iend),
            "missing IDAT": png_from_chunks(ihdr, iend),
            "missing IEND": png_from_chunks(ihdr, idat),
            "duplicate IHDR": png_from_chunks(ihdr, ihdr, idat, iend),
            "duplicate PLTE": png_from_chunks(
                ihdr, palette, palette, idat, iend
            ),
            "PLTE after IDAT": png_from_chunks(ihdr, idat, palette, iend),
            "non-consecutive IDAT": png_from_chunks(
                ihdr,
                png_chunk(b"IDAT", compressed[:midpoint]),
                png_chunk(b"tEXt", b"key\x00value"),
                png_chunk(b"IDAT", compressed[midpoint:]),
                iend,
            ),
            "unknown critical chunk": png_from_chunks(
                ihdr, png_chunk(b"ABCD", b""), idat, iend
            ),
            "duplicate IEND": png_from_chunks(ihdr, idat, iend, iend),
        }
        for label, contents in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                png = Path(td) / "bad.png"
                png.write_bytes(contents)
                with self.assertRaises(brand_installer.BrandingError):
                    brand_installer.validate_png_asset(png, width, height)

    def test_rejects_bad_truncated_and_concatenated_zlib_streams(self):
        width, height = 4, 3
        raw = rgb8_scanlines(width, height)
        compressed = zlib.compress(raw)
        cases = {
            "not zlib": b"not a zlib stream",
            "truncated zlib": compressed[:-2],
            "bad Adler checksum": compressed[:-1]
            + bytes([compressed[-1] ^ 0xFF]),
            "concatenated stream": compressed + zlib.compress(b""),
        }
        for label, bad_stream in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                png = Path(td) / "bad.png"
                png.write_bytes(
                    png_image(width, height, compressed=bad_stream)
                )
                with self.assertRaises(brand_installer.BrandingError):
                    brand_installer.validate_png_asset(png, width, height)

    def test_rejects_invalid_scanline_lengths_and_filter_bytes(self):
        width, height = 4, 3
        scanline_size = 1 + width * 3
        valid = rgb8_scanlines(width, height)
        second_filter = bytearray(valid)
        second_filter[scanline_size] = 5
        cases = {
            "short scanlines": valid[:-1],
            "long scanlines": valid + b"\x00",
            "first bad filter": b"\x05" + valid[1:],
            "later bad filter": bytes(second_filter),
        }
        for label, raw in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                png = Path(td) / "bad.png"
                png.write_bytes(png_image(width, height, raw=raw))
                with self.assertRaises(brand_installer.BrandingError):
                    brand_installer.validate_png_asset(png, width, height)

    def test_fully_decodes_all_standard_scanline_filters(self):
        width, height = 4, 5
        rows = []
        for filter_type in range(5):
            encoded = bytes(
                (index * 17 + filter_type * 13) & 0xFF
                for index in range(width * 3)
            )
            rows.append(bytes([filter_type]) + encoded)
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / "filters.png"
            png.write_bytes(png_image(width, height, raw=b"".join(rows)))
            brand_installer.validate_png_asset(png, width, height)

    def test_rejects_transparency_chunk_for_rgb_image(self):
        width, height = 4, 3
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / "transparent.png"
            png.write_bytes(
                png_image(
                    width,
                    height,
                    before_idat=(png_chunk(b"tRNS", b"\x00" * 6),),
                )
            )
            with self.assertRaises(brand_installer.BrandingError):
                brand_installer.validate_png_asset(png, width, height)


class TextBrandingTests(unittest.TestCase):
    def test_literal_bel_and_all_ten_themes_receive_dynamic_version(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            menu, theme_root = write_text_fixture(root)
            mtimes = {
                path: path.stat().st_mtime_ns
                for path in root.rglob("*")
                if path.is_file()
            }

            brand_installer.brand_boot_text(root, "9.8.7")

            menu_bytes = menu.read_bytes()
            self.assertIn(
                b"menu title \x07Plebian-OS 9.8.7 installer menu (BIOS mode)",
                menu_bytes,
            )
            self.assertNotIn(brand_installer.BIOS_TITLE, menu_bytes)
            self.assertEqual(menu_bytes.count(b"\x07"), 1)

            readme_text = (root / "README.txt").read_bytes()
            readme_html = (root / "README.html").read_bytes()
            for rendered in (readme_text, readme_html):
                normalized = b" ".join(rendered.split())
                self.assertIn(b"Plebian-OS 9.8.7", normalized)
                self.assertIn(b"Debian 13", normalized)
                self.assertIn(b"not an official Debian image", normalized)
                self.assertIn(b"not endorsed by the Debian Project", normalized)
                self.assertIn(b"itsmygithubacct/plebian-os/issues", normalized)
                self.assertNotIn(b"Official amd64 NETINST", normalized)
                self.assertNotIn(b"official release of the Debian", normalized)
            self.assertIn(b"/install.amd/", readme_text)
            self.assertIn(b"<title>Plebian-OS 9.8.7 installer</title>", readme_html)
            self.assertNotIn(b"openlogo-nd-50.png", readme_html)

            f1 = (root / "isolinux" / "f1.txt").read_bytes()
            f2 = (root / "isolinux" / "f2.txt").read_bytes()
            f9 = (root / "isolinux" / "f9.txt").read_bytes()
            self.assertIn(b"Welcome to Plebian-OS 9.8.7!", f1)
            self.assertIn(b"based on Debian 13 (trixie)", f1)
            self.assertIn(b"INSTALLING PLEBIAN-OS", f2)
            self.assertIn(b"at least 4 GiB of RAM and 20 GiB", f2)
            self.assertIn(b"network connection is required on first boot", f2)
            self.assertNotIn(b"350 megabytes", f2)
            self.assertNotIn(b"1160 megabytes", f2)
            self.assertIn(b"Thank you for choosing Plebian-OS!", f2)
            self.assertIn(b"itsmygithubacct/plebian-os/issues", f9)
            self.assertIn(b"/cdrom/plebian-os/build-info.env", f9)
            self.assertIn(b"/etc/plebian-os/build-info.env", f9)
            self.assertIn(b"underlying Debian Installer", f9)
            self.assertNotIn(b"Debian team is ready", f9)
            for help_page in (f1, f2, f9):
                self.assertLessEqual(
                    max(len(line) for line in help_page.splitlines()),
                    80,
                )

            self.assertEqual(len(brand_installer.THEME_NAMES), 10)
            for name in brand_installer.THEME_NAMES:
                themed = (theme_root / name).read_bytes()
                self.assertIn(b'title-text: "Plebian-OS 9.8.7"', themed)
                self.assertIn(
                    b'text = "Plebian-OS UEFI Installer menu"', themed
                )
                self.assertNotIn(brand_installer.UEFI_TITLE, themed)
                self.assertNotIn(brand_installer.UEFI_HEADING, themed)
                # Branding is targeted; Debian attribution elsewhere is retained.
                self.assertIn(b"Debian attribution remains valid", themed)

            for path, expected_mtime in mtimes.items():
                self.assertEqual(path.stat().st_mtime_ns, expected_mtime)

    def test_accepts_release_safe_version_alphabet(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            menu, _ = write_text_fixture(root)
            brand_installer.brand_boot_text(root, "v1.2+git~rc-1")
            self.assertIn(b"Plebian-OS v1.2+git~rc-1", menu.read_bytes())

    def test_rejects_unsafe_versions_without_modifying_tree(self):
        for version in ("", ".1", "-1", "1 2", "1/2", "1\n2", "é"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                write_text_fixture(root)
                before = tree_bytes(root)
                with self.assertRaises(brand_installer.BrandingError):
                    brand_installer.brand_boot_text(root, version)
                self.assertEqual(tree_bytes(root), before)

    def test_source_string_and_theme_drift_fail_before_any_write(self):
        def missing_bios(root, menu, theme_root):
            menu.write_bytes(menu.read_bytes().replace(brand_installer.BIOS_TITLE, b""))

        def duplicate_bios(root, menu, theme_root):
            menu.write_bytes(menu.read_bytes() + brand_installer.BIOS_TITLE)

        def missing_theme_title(root, menu, theme_root):
            path = theme_root / "dark-1-2"
            path.write_bytes(path.read_bytes().replace(brand_installer.UEFI_TITLE, b""))

        def duplicate_theme_heading(root, menu, theme_root):
            path = theme_root / "1-1-1"
            path.write_bytes(path.read_bytes() + brand_installer.UEFI_HEADING)

        def missing_theme(root, menu, theme_root):
            (theme_root / "1-2-1").unlink()

        def extra_theme(root, menu, theme_root):
            (theme_root / "future-theme").write_bytes(b"upstream drift")

        def missing_readme_marker(root, menu, theme_root):
            path = root / "README.txt"
            path.write_bytes(
                path.read_bytes().replace(
                    brand_installer.README_TEXT_REQUIRED[0][0], b"upstream drift"
                )
            )

        cases = {
            "missing BIOS title": missing_bios,
            "duplicate BIOS title": duplicate_bios,
            "missing UEFI title": missing_theme_title,
            "duplicate UEFI heading": duplicate_theme_heading,
            "missing theme": missing_theme,
            "extra theme": extra_theme,
            "missing README marker": missing_readme_marker,
        }
        for label, mutate in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                menu, theme_root = write_text_fixture(root)
                mutate(root, menu, theme_root)
                before = tree_bytes(root)
                with self.assertRaises(brand_installer.BrandingError):
                    brand_installer.brand_boot_text(root, "9.8.7")
                self.assertEqual(tree_bytes(root), before)

    def test_main_menu_template_receives_dynamic_product_title(self):
        with tempfile.TemporaryDirectory() as td:
            template = Path(td) / "main-menu.templates"
            template.write_bytes(
                brand_installer.MAIN_MENU_TITLE
                + b"Description-de.UTF-8: Debian-Installer --- Hauptmenu\n"
            )
            timestamp_ns = 1_650_000_000_123_456_789
            os.utime(template, ns=(timestamp_ns, timestamp_ns))
            brand_installer.brand_main_menu_template(template, "9.8.7")
            rendered = template.read_bytes()
            self.assertIn(
                b"Description: Plebian-OS 9.8.7 installer main menu "
                b"(Debian Installer)\n",
                rendered,
            )
            self.assertNotIn(brand_installer.MAIN_MENU_TITLE, rendered)
            self.assertIn(b"Description-de.UTF-8: Debian-Installer", rendered)
            self.assertEqual(template.stat().st_mtime_ns, timestamp_ns)

    def test_main_menu_drift_and_unsafe_version_leave_file_unchanged(self):
        cases = (
            (b"Description: future installer title\n", "9.8.7"),
            (brand_installer.MAIN_MENU_TITLE, "9 8 7"),
            (brand_installer.MAIN_MENU_TITLE * 2, "9.8.7"),
        )
        for contents, version in cases:
            with self.subTest(contents=contents, version=version), tempfile.TemporaryDirectory() as td:
                template = Path(td) / "main-menu.templates"
                template.write_bytes(contents)
                before = template.read_bytes()
                with self.assertRaises(brand_installer.BrandingError):
                    brand_installer.brand_main_menu_template(template, version)
                self.assertEqual(template.read_bytes(), before)


class Md5ManifestTests(unittest.TestCase):
    def make_manifest_tree(self, base, *, terminal_newline=True):
        root = base / "iso"
        (root / "nested").mkdir(parents=True)
        (root / "plebian-os" / "nested").mkdir(parents=True)
        entries = [
            ("z-last.bin", b"last"),
            ("a file.txt", b"space"),
            ("nested/middle", b"middle"),
        ]
        for relative, contents in entries:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        custom_entries = [
            ("preseed.cfg", b"preseed"),
            ("plebian-os/a file.txt", b"payload space"),
            ("plebian-os/nested/z-last.bin", b"payload nested"),
        ]
        for relative, contents in custom_entries:
            (root / relative).write_bytes(contents)
        lines = [f"{'0' * 32}  ./{relative}" for relative, _ in entries]
        manifest = root / "md5sum.txt"
        ending = "\n" if terminal_newline else ""
        manifest.write_text("\n".join(lines) + ending)
        os.utime(manifest, ns=(1_650_000_000_000_000_000,) * 2)
        return root, manifest, entries, custom_entries

    def test_refreshes_existing_entries_and_appends_all_custom_files(self):
        for terminal_newline in (True, False):
            with (
                self.subTest(terminal_newline=terminal_newline),
                tempfile.TemporaryDirectory() as td,
            ):
                root, manifest, entries, custom_entries = self.make_manifest_tree(
                    Path(td), terminal_newline=terminal_newline
                )
                original_mtime = manifest.stat().st_mtime_ns

                brand_installer.refresh_md5_manifest(root)

                expected_lines = [
                    f"{hashlib.md5(contents).hexdigest()}  ./{relative}"
                    for relative, contents in entries + custom_entries
                ]
                ending = "\n" if terminal_newline else ""
                self.assertEqual(
                    manifest.read_text(), "\n".join(expected_lines) + ending
                )
                self.assertEqual(manifest.stat().st_mtime_ns, original_mtime)

    def test_does_not_duplicate_custom_file_already_in_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root, manifest, _, _ = self.make_manifest_tree(Path(td))
            manifest.write_text(
                manifest.read_text()
                + f"{'0' * 32}  ./preseed.cfg\n"
            )

            brand_installer.refresh_md5_manifest(root)

            lines = manifest.read_text().splitlines()
            preseed_lines = [line for line in lines if line.endswith("  ./preseed.cfg")]
            self.assertEqual(len(preseed_lines), 1)
            self.assertEqual(
                preseed_lines[0],
                f"{hashlib.md5(b'preseed').hexdigest()}  ./preseed.cfg",
            )

    def test_invalid_custom_payload_leaves_manifest_unchanged(self):
        def missing_preseed(root):
            (root / "preseed.cfg").unlink()

        def payload_symlink(root):
            (root / "plebian-os" / "link").symlink_to(root / "z-last.bin")

        for label, mutate in (
            ("missing preseed", missing_preseed),
            ("payload symlink", payload_symlink),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                root, manifest, _, _ = self.make_manifest_tree(Path(td))
                mutate(root)
                before = manifest.read_bytes()
                with self.assertRaises(brand_installer.BrandingError):
                    brand_installer.refresh_md5_manifest(root)
                self.assertEqual(manifest.read_bytes(), before)

    def test_malformed_missing_and_unsafe_entries_leave_manifest_unchanged(self):
        def uppercase(root, manifest):
            manifest.write_text(f"{'A' * 32}  ./z-last.bin\n")

        def one_space(root, manifest):
            manifest.write_text(f"{'0' * 32} ./z-last.bin\n")

        def no_dot_slash(root, manifest):
            manifest.write_text(f"{'0' * 32}  z-last.bin\n")

        def traversal(root, manifest):
            manifest.write_text(f"{'0' * 32}  ./../outside\n")

        def absolute(root, manifest):
            manifest.write_text(f"{'0' * 32}  .//etc/passwd\n")

        def missing(root, manifest):
            manifest.write_text(f"{'0' * 32}  ./not-present\n")

        def self_reference(root, manifest):
            manifest.write_text(f"{'0' * 32}  ./md5sum.txt\n")

        cases = {
            "uppercase digest": uppercase,
            "one separator space": one_space,
            "missing dot slash": no_dot_slash,
            "parent traversal": traversal,
            "absolute path": absolute,
            "missing file": missing,
            "self reference": self_reference,
        }
        for label, mutate in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                root, manifest, _, _ = self.make_manifest_tree(Path(td))
                mutate(root, manifest)
                before = manifest.read_bytes()
                with self.assertRaises(brand_installer.BrandingError):
                    brand_installer.refresh_md5_manifest(root)
                self.assertEqual(manifest.read_bytes(), before)

    def test_rejects_symlink_that_escapes_iso_root(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root, manifest, _, _ = self.make_manifest_tree(base)
            outside = base / "outside"
            outside.write_bytes(b"not part of ISO")
            (root / "escape").symlink_to(outside)
            manifest.write_text(f"{'0' * 32}  ./escape\n")
            before = manifest.read_bytes()
            with self.assertRaises(brand_installer.BrandingError):
                brand_installer.refresh_md5_manifest(root)
            self.assertEqual(manifest.read_bytes(), before)

    def test_commit_failure_rolls_manifest_back(self):
        with tempfile.TemporaryDirectory() as td:
            root, manifest, _, _ = self.make_manifest_tree(Path(td))
            before = manifest.read_bytes()
            with mock.patch.object(
                brand_installer.os,
                "utime",
                side_effect=OSError("injected timestamp failure"),
            ):
                with self.assertRaises(brand_installer.BrandingError):
                    brand_installer.refresh_md5_manifest(root)
            self.assertEqual(manifest.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
