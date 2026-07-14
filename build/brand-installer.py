#!/usr/bin/env python3
"""Fail-closed helpers for branding the pinned Debian installer tree.

The text mutation deliberately matches Debian 13.5's exact bytes.  A future
base-image change must update these constants and their fixtures together.
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import os
import re
import stat
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence


class BrandingError(RuntimeError):
    """The input does not satisfy the audited installer branding contract."""


THEME_NAMES = frozenset(
    {
        "1",
        "1-1",
        "1-1-1",
        "1-2",
        "1-2-1",
        "dark-1",
        "dark-1-1",
        "dark-1-1-1",
        "dark-1-2",
        "dark-1-2-1",
    }
)

BIOS_TITLE = b"menu title \x07Debian GNU/Linux installer menu (BIOS mode)"
UEFI_TITLE = b'title-text: "Debian GNU/Linux 13.5.0"'
UEFI_HEADING = b'text = "Debian GNU/Linux UEFI Installer menu"'

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_IHDR = struct.Struct(">IIBBBBB")
_VERSION_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+~-]*\Z")
_MANIFEST_LINE_RE = re.compile(
    rb"(?P<digest>[0-9a-f]{32})  \./(?P<path>[^\r\n]+)\Z"
)


@dataclass(frozen=True)
class PngIhdr:
    width: int
    height: int
    bit_depth: int
    color_type: int
    compression: int
    filter_method: int
    interlace: int


@dataclass(frozen=True)
class _Mutation:
    path: Path
    original: bytes
    updated: bytes
    atime_ns: int
    mtime_ns: int


def _fail(path: Path, detail: str) -> BrandingError:
    return BrandingError(f"{path}: {detail}")


def _version_bytes(version: str) -> bytes:
    if _VERSION_RE.fullmatch(version) is None:
        raise BrandingError(f"unsafe PLEBIAN_OS_VERSION: {version!r}")
    return version.encode("ascii")


def _prepare_replacements(
    path: Path, replacements: Iterable[tuple[bytes, bytes, int]]
) -> _Mutation:
    try:
        path_stat = path.stat()
    except OSError as exc:
        raise _fail(path, f"cannot stat required file: {exc}") from exc
    if path.is_symlink() or not stat.S_ISREG(path_stat.st_mode):
        raise _fail(path, "required path is not a regular file")

    try:
        original = path.read_bytes()
    except OSError as exc:
        raise _fail(path, f"cannot read required file: {exc}") from exc

    updated = original
    for old, new, expected in replacements:
        count = updated.count(old)
        if count != expected:
            raise _fail(
                path,
                f"expected {expected} copies of {old!r}, found {count}",
            )
        updated = updated.replace(old, new)

    return _Mutation(
        path=path,
        original=original,
        updated=updated,
        atime_ns=path_stat.st_atime_ns,
        mtime_ns=path_stat.st_mtime_ns,
    )


def _write_mutations(mutations: Sequence[_Mutation]) -> None:
    written: list[_Mutation] = []
    try:
        for mutation in mutations:
            # Include the current path in rollback even if write_bytes() only
            # partially succeeds or restoring its timestamp fails.
            written.append(mutation)
            mutation.path.write_bytes(mutation.updated)
            os.utime(
                mutation.path,
                ns=(mutation.atime_ns, mutation.mtime_ns),
            )
    except OSError as exc:
        # Validation happens before the first write.  If the filesystem itself
        # fails mid-commit, make a best-effort rollback of files already written.
        for mutation in reversed(written):
            try:
                mutation.path.write_bytes(mutation.original)
                os.utime(
                    mutation.path,
                    ns=(mutation.atime_ns, mutation.mtime_ns),
                )
            except OSError:
                pass
        raise BrandingError(f"could not write installer branding: {exc}") from exc


def brand_boot_text(root: Path | str, version: str) -> None:
    """Patch the exact BIOS and UEFI strings in an extracted Debian 13.5 ISO.

    Every input and replacement count is checked before any file is modified.
    The literal BIOS BEL byte and each file's access/modify timestamps are
    preserved.
    """

    root = Path(root)
    version_b = _version_bytes(version)
    theme_root = root / "boot/grub/theme"

    try:
        entries = list(theme_root.iterdir())
    except OSError as exc:
        raise _fail(theme_root, f"cannot inspect required theme directory: {exc}") from exc

    actual = {entry.name for entry in entries if entry.name != "hl_c.png"}
    if actual != THEME_NAMES:
        raise _fail(theme_root, f"unexpected GRUB theme set: {sorted(actual)}")

    for name in THEME_NAMES:
        theme = theme_root / name
        try:
            theme_stat = theme.stat()
        except OSError as exc:
            raise _fail(theme, f"cannot stat required theme: {exc}") from exc
        if theme.is_symlink() or not stat.S_ISREG(theme_stat.st_mode):
            raise _fail(theme, "required theme is not a regular file")

    mutations = [
        _prepare_replacements(
            root / "isolinux/menu.cfg",
            [
                (
                    BIOS_TITLE,
                    b"menu title \x07Plebian-OS "
                    + version_b
                    + b" installer menu (BIOS mode)",
                    1,
                )
            ],
        )
    ]

    for name in sorted(THEME_NAMES):
        mutations.append(
            _prepare_replacements(
                theme_root / name,
                [
                    (
                        UEFI_TITLE,
                        b'title-text: "Plebian-OS ' + version_b + b'"',
                        1,
                    ),
                    (
                        UEFI_HEADING,
                        b'text = "Plebian-OS UEFI Installer menu"',
                        1,
                    ),
                ],
            )
        )

    _write_mutations(mutations)


def _png_chunk_name(chunk_type: bytes) -> str:
    return chunk_type.decode("ascii", errors="backslashreplace")


def _validate_png_chunk_type(path: Path, chunk_type: bytes) -> None:
    if len(chunk_type) != 4 or any(
        not (ord("A") <= byte <= ord("Z") or ord("a") <= byte <= ord("z"))
        for byte in chunk_type
    ):
        raise _fail(path, f"invalid PNG chunk type {chunk_type!r}")
    # PNG reserves the case bit of the third type byte; it must be uppercase.
    if chunk_type[2] & 0x20:
        raise _fail(path, f"invalid reserved bit in PNG chunk {chunk_type!r}")


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left


def _decode_rgb8_scanlines(
    path: Path, ihdr: PngIhdr, compressed: bytes
) -> None:
    row_size = ihdr.width * 3
    scanline_size = row_size + 1
    expected_size = scanline_size * ihdr.height
    if expected_size >= sys.maxsize:
        raise _fail(path, "decoded PNG is too large to validate safely")

    decoder = zlib.decompressobj()
    try:
        decoded = decoder.decompress(compressed, expected_size + 1)
    except zlib.error as exc:
        raise _fail(path, f"invalid PNG zlib stream: {exc}") from exc

    if len(decoded) > expected_size or decoder.unconsumed_tail:
        raise _fail(
            path,
            f"invalid PNG scanline length: expected {expected_size} bytes",
        )
    if not decoder.eof:
        raise _fail(path, "truncated PNG zlib stream")
    if decoder.unused_data:
        raise _fail(path, "trailing data after PNG zlib stream")
    try:
        decoded += decoder.flush()
    except zlib.error as exc:
        raise _fail(path, f"invalid PNG zlib stream: {exc}") from exc
    if len(decoded) != expected_size:
        raise _fail(
            path,
            "invalid PNG scanline length: "
            f"expected {expected_size} bytes, got {len(decoded)}",
        )

    previous = bytearray(row_size)
    offset = 0
    for row_number in range(ihdr.height):
        filter_type = decoded[offset]
        if filter_type > 4:
            raise _fail(
                path,
                f"invalid PNG filter {filter_type} on row {row_number}",
            )
        row = bytearray(decoded[offset + 1 : offset + scanline_size])
        if filter_type == 1:  # Sub
            for index in range(3, row_size):
                row[index] = (row[index] + row[index - 3]) & 0xFF
        elif filter_type == 2:  # Up
            for index in range(row_size):
                row[index] = (row[index] + previous[index]) & 0xFF
        elif filter_type == 3:  # Average
            for index in range(row_size):
                left = row[index - 3] if index >= 3 else 0
                row[index] = (row[index] + ((left + previous[index]) // 2)) & 0xFF
        elif filter_type == 4:  # Paeth
            for index in range(row_size):
                left = row[index - 3] if index >= 3 else 0
                upper_left = previous[index - 3] if index >= 3 else 0
                row[index] = (
                    row[index] + _paeth(left, previous[index], upper_left)
                ) & 0xFF
        previous = row
        offset += scanline_size


def _validate_complete_png(
    path: Path, expected: PngIhdr | None = None
) -> PngIhdr:
    try:
        contents = path.read_bytes()
    except OSError as exc:
        raise _fail(path, f"cannot read PNG: {exc}") from exc
    if not contents.startswith(PNG_SIGNATURE):
        raise _fail(path, "invalid PNG signature")

    offset = len(PNG_SIGNATURE)
    ihdr: PngIhdr | None = None
    compressed_parts: list[bytes] = []
    seen_plte = False
    seen_idat = False
    idat_closed = False
    seen_iend = False

    while offset < len(contents):
        if len(contents) - offset < 8:
            raise _fail(path, "truncated PNG chunk header")
        length = struct.unpack(">I", contents[offset : offset + 4])[0]
        chunk_type = contents[offset + 4 : offset + 8]
        _validate_png_chunk_type(path, chunk_type)
        if length > 0x7FFFFFFF:
            raise _fail(path, "PNG chunk length exceeds the format limit")

        data_start = offset + 8
        data_end = data_start + length
        crc_end = data_end + 4
        chunk_name = _png_chunk_name(chunk_type)
        if crc_end > len(contents):
            raise _fail(path, f"truncated PNG {chunk_name} chunk")
        payload = contents[data_start:data_end]
        stored_crc = struct.unpack(">I", contents[data_end:crc_end])[0]
        calculated_crc = binascii.crc32(chunk_type + payload) & 0xFFFFFFFF
        if stored_crc != calculated_crc:
            raise _fail(path, f"invalid PNG {chunk_name} CRC")
        offset = crc_end

        if ihdr is None:
            if chunk_type != b"IHDR" or length != _IHDR.size:
                raise _fail(path, "IHDR is not the first PNG chunk")
            ihdr = PngIhdr(*_IHDR.unpack(payload))
            if not (1 <= ihdr.width <= 0x7FFFFFFF) or not (
                1 <= ihdr.height <= 0x7FFFFFFF
            ):
                raise _fail(path, "invalid PNG dimensions")
            required = PngIhdr(
                width=ihdr.width,
                height=ihdr.height,
                bit_depth=8,
                color_type=2,
                compression=0,
                filter_method=0,
                interlace=0,
            )
            contract = expected if expected is not None else required
            if ihdr != contract:
                raise _fail(
                    path,
                    "expected "
                    f"{contract.width}x{contract.height} RGB8 non-interlaced PNG "
                    f"(IHDR {contract}), got IHDR {ihdr}",
                )
            continue

        if chunk_type == b"IHDR":
            raise _fail(path, "duplicate PNG IHDR chunk")
        if chunk_type == b"PLTE":
            if seen_plte:
                raise _fail(path, "duplicate PNG PLTE chunk")
            if seen_idat:
                raise _fail(path, "PNG PLTE chunk appears after IDAT")
            if length == 0 or length % 3 or length > 256 * 3:
                raise _fail(path, "invalid PNG PLTE length")
            seen_plte = True
            continue
        if chunk_type == b"IDAT":
            if idat_closed:
                raise _fail(path, "non-consecutive PNG IDAT chunks")
            seen_idat = True
            compressed_parts.append(payload)
            continue
        if chunk_type == b"IEND":
            if length != 0:
                raise _fail(path, "invalid PNG IEND length")
            if not seen_idat:
                raise _fail(path, "PNG has no IDAT chunk")
            seen_iend = True
            if offset != len(contents):
                raise _fail(path, "trailing bytes after PNG IEND chunk")
            break
        if not (chunk_type[0] & 0x20):
            raise _fail(path, f"unknown critical PNG chunk {chunk_name}")
        if chunk_type == b"tRNS":
            raise _fail(path, "PNG transparency is not allowed")
        if seen_idat:
            idat_closed = True

    if ihdr is None:
        raise _fail(path, "PNG has no IHDR chunk")
    if not seen_iend:
        raise _fail(path, "PNG has no IEND chunk")
    _decode_rgb8_scanlines(path, ihdr, b"".join(compressed_parts))
    return ihdr


def read_png_ihdr(path: Path | str) -> PngIhdr:
    """Validate a complete RGB8 PNG and return its authenticated IHDR."""

    return _validate_complete_png(Path(path))


def validate_png_asset(
    path: Path | str, expected_width: int, expected_height: int
) -> PngIhdr:
    """Require an RGB8, non-interlaced PNG with the requested dimensions."""

    path = Path(path)
    if expected_width < 1 or expected_height < 1:
        raise BrandingError("expected PNG dimensions must be positive")
    expected = PngIhdr(
        width=expected_width,
        height=expected_height,
        bit_depth=8,
        color_type=2,
        compression=0,
        filter_method=0,
        interlace=0,
    )
    return _validate_complete_png(path, expected)


def validate_installer_assets(asset_root: Path | str) -> None:
    """Validate all three PNGs embedded in the Debian installer."""

    asset_root = Path(asset_root)
    validate_png_asset(asset_root / "splash.png", 640, 480)
    validate_png_asset(asset_root / "banner.png", 800, 75)
    validate_png_asset(asset_root / "banner-dark.png", 800, 75)


def _new_md5():
    # Python exposes usedforsecurity on current supported Debian, while the
    # fallback keeps the helper usable with older Python 3 implementations.
    try:
        return hashlib.md5(usedforsecurity=False)
    except TypeError:
        return hashlib.md5()


def _md5_file(path: Path) -> str:
    digest = _new_md5()
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise _fail(path, f"cannot hash manifest entry: {exc}") from exc
    return digest.hexdigest()


def _manifest_target(root: Path, raw_path: bytes, line_number: int) -> Path:
    relative_text = os.fsdecode(raw_path)
    relative = PurePosixPath(relative_text)
    raw_parts = raw_path.split(b"/")
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {b"", b".", b".."} for part in raw_parts)
    ):
        raise BrandingError(
            f"md5sum.txt:{line_number}: unsafe relative path {relative_text!r}"
        )

    target = root.joinpath(*relative.parts)
    try:
        resolved = target.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise BrandingError(
            f"md5sum.txt:{line_number}: missing path {relative_text!r}: {exc}"
        ) from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise BrandingError(
            f"md5sum.txt:{line_number}: path escapes ISO root: {relative_text!r}"
        ) from exc
    if not resolved.is_file():
        raise BrandingError(
            f"md5sum.txt:{line_number}: path is not a file: {relative_text!r}"
        )
    return target


def refresh_md5_manifest(root: Path | str) -> None:
    """Refresh existing md5sum.txt entries without changing path order/spelling."""

    root = Path(root)
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        raise BrandingError(f"cannot resolve ISO root {root}: {exc}") from exc
    if not root.is_dir():
        raise BrandingError(f"ISO root is not a directory: {root}")

    manifest = root / "md5sum.txt"
    try:
        manifest_stat = manifest.stat()
    except OSError as exc:
        raise _fail(manifest, f"cannot stat required manifest: {exc}") from exc
    if manifest.is_symlink() or not stat.S_ISREG(manifest_stat.st_mode):
        raise _fail(manifest, "required manifest is not a regular file")
    try:
        original = manifest.read_bytes()
    except OSError as exc:
        raise _fail(manifest, f"cannot read required manifest: {exc}") from exc
    if not original:
        raise _fail(manifest, "manifest is empty")

    has_terminal_newline = original.endswith(b"\n")
    raw_lines = original[:-1].split(b"\n") if has_terminal_newline else original.split(b"\n")
    refreshed: list[bytes] = []
    digest_cache: dict[Path, str] = {}

    for line_number, line in enumerate(raw_lines, start=1):
        match = _MANIFEST_LINE_RE.fullmatch(line)
        if match is None:
            raise BrandingError(f"md5sum.txt:{line_number}: malformed manifest line")
        target = _manifest_target(root, match.group("path"), line_number)
        resolved = target.resolve(strict=True)
        if resolved == manifest:
            raise BrandingError(
                f"md5sum.txt:{line_number}: manifest cannot list itself"
            )
        if resolved not in digest_cache:
            digest_cache[resolved] = _md5_file(target)
        refreshed.append(
            digest_cache[resolved].encode("ascii") + line[32:]
        )

    updated = b"\n".join(refreshed)
    if has_terminal_newline:
        updated += b"\n"

    try:
        manifest.write_bytes(updated)
        os.utime(
            manifest,
            ns=(manifest_stat.st_atime_ns, manifest_stat.st_mtime_ns),
        )
    except OSError as exc:
        try:
            manifest.write_bytes(original)
            os.utime(
                manifest,
                ns=(manifest_stat.st_atime_ns, manifest_stat.st_mtime_ns),
            )
        except OSError:
            pass
        raise _fail(manifest, f"cannot refresh manifest: {exc}") from exc


def _positive_dimension(value: str) -> int:
    try:
        dimension = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if dimension < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return dimension


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    patch = subparsers.add_parser("patch-text", help="brand BIOS and UEFI text")
    patch.add_argument("root", type=Path, help="extracted ISO root")
    patch.add_argument("version", help="resolved PLEBIAN_OS_VERSION")

    png = subparsers.add_parser("validate-png", help="validate one embedded PNG")
    png.add_argument("path", type=Path)
    png.add_argument("width", type=_positive_dimension)
    png.add_argument("height", type=_positive_dimension)

    assets = subparsers.add_parser(
        "validate-assets", help="validate splash.png and both banner PNGs"
    )
    assets.add_argument("asset_root", type=Path)

    refresh = subparsers.add_parser(
        "refresh-md5", help="refresh existing md5sum.txt entries"
    )
    refresh.add_argument("root", type=Path, help="extracted ISO root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "patch-text":
            brand_boot_text(args.root, args.version)
        elif args.command == "validate-png":
            validate_png_asset(args.path, args.width, args.height)
        elif args.command == "validate-assets":
            validate_installer_assets(args.asset_root)
        elif args.command == "refresh-md5":
            refresh_md5_manifest(args.root)
        else:  # pragma: no cover - argparse constrains this value.
            raise AssertionError(f"unhandled command: {args.command}")
    except BrandingError as exc:
        print(f"brand-installer.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
