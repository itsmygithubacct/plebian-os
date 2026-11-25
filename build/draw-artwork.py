#!/usr/bin/env python3
"""Draw the Plebian-OS boot splash, installer banner and desktop wallpaper.

    draw-artwork.py --neuronte DIR [--out DIR] [--check]

Everything in the three pictures is drawn here, from two things only:

* the angular-P mark, read from assets/installer/logo.svg (its paths, stroke
  widths and colours; nothing about the mark is repeated in this file), and
* the lettering "Plebian-OS", drawn by the Neuronte large desktop face
  (weights/neuronte-ui-large-latin1-v2.nrt of a Neuronte release, through
  build/libneuronte.so of the same release). DIR is that release's directory.
  The weight file must have the SHA-256 recorded below.

The background is a vertical gradient with the outline of the same mark,
enlarged and cropped, laid over it faintly. No other artwork is read.

The files written are assets/installer/splash.png, banner.png and
banner-dark.png (the same bytes) and assets/desktop/plebian-os.png; --out
writes them into another directory instead and --check compares what would
be written with the tracked files and writes nothing.

The same inputs give the same bytes: the drawing is integer and float64
arithmetic with no random numbers, and the PNG encoder is the one in this
file. The encoder's output depends on zlib; the tracked files were written
with zlib 1.3.1, Pillow 11.1.0 (polygon filling only) and NumPy 2.2.4.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / 'assets' / 'installer' / 'logo.svg'
LETTERING = 'Plebian-OS'
FACE = 'weights/neuronte-ui-large-latin1-v2.nrt'
FACE_SHA256 = 'f50ffdae9770686accf3e0fd79109487885977e06c4d1282102c5d9701dd3fc4'
LIBRARY = 'build/libneuronte.so'
SUPERSAMPLE = 8

BACKGROUND_TOP = (0x10, 0x18, 0x24)
BACKGROUND_BOTTOM = (0x1a, 0x28, 0x3a)
WATERMARK = (0xaa, 0xc5, 0xda)  # the mark's own colour, laid on faintly
WATERMARK_LINE = 0.075
WATERMARK_FILL = 0.030


# The mark ------------------------------------------------------------------

def parse_path(d: str) -> tuple[list[tuple[float, float]], bool]:
    """The points of one absolute M/L/H/V/Z path, and whether it is closed."""
    if re.sub(r'[MLHVZ0-9. \-]', '', d):
        raise ValueError(f'unsupported path data: {d!r}')
    points: list[tuple[float, float]] = []
    closed = False
    command = ''
    tokens = re.findall(r'[MLHVZ]|-?[0-9]+(?:\.[0-9]+)?', d)
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in 'MLHVZ':
            command = token
            i += 1
            if command == 'Z':
                closed = True
            continue
        if command in 'ML':
            if i + 1 >= len(tokens) or tokens[i + 1] in 'MLHVZ':
                raise ValueError(f'a point needs two numbers: {d!r}')
            points.append((float(token), float(tokens[i + 1])))
            i += 2
            command = 'L'
        elif command == 'H':
            points.append((float(token), points[-1][1]))
            i += 1
        elif command == 'V':
            points.append((points[-1][0], float(token)))
            i += 1
        else:
            raise ValueError(f'unsupported path data: {d!r}')
    if closed and points[0] == points[-1]:
        points.pop()
    return points, closed


class Mark:
    """The angular-P mark as logo.svg defines it."""

    def __init__(self, svg: Path = LOGO) -> None:
        ns = {'s': 'http://www.w3.org/2000/svg'}
        root = ET.parse(svg).getroot()
        box = [float(v) for v in root.attrib['viewBox'].split()]
        if box[:2] != [0.0, 0.0] or box[2] != box[3]:
            raise ValueError('logo.svg must have a square viewBox at the origin')
        self.size = box[2]
        self.strokes = []  # (points, closed, width, colour, round)
        for group in root.findall('s:g', ns):
            colour = hex_colour(group.attrib['stroke'])
            width = float(group.attrib['stroke-width'])
            is_round = group.attrib['stroke-linejoin'] == 'round'
            for path in group.findall('s:path', ns):
                points, closed = parse_path(path.attrib['d'])
                self.strokes.append((points, closed, width, colour, is_round))
        self.dots = [((float(c.attrib['cx']), float(c.attrib['cy'])), float(c.attrib['r']),
                      hex_colour(c.attrib['fill'])) for c in root.findall('s:circle', ns)]
        if len(self.strokes) != 5 or len(self.dots) != 1:
            raise ValueError('logo.svg is not the mark this program knows how to draw')
        self.outline = self.strokes[0]


def hex_colour(text: str) -> tuple[int, int, int]:
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', text):
        raise ValueError(f'not a colour: {text!r}')
    return int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16)


def _offset(p: tuple[float, float], q: tuple[float, float], d: float) -> tuple[float, float]:
    length = ((q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2) ** 0.5
    return -(q[1] - p[1]) / length * d, (q[0] - p[0]) / length * d


def _meet(a, b, c, d):
    """Where the line through a and b meets the line through c and d."""
    den = (a[0] - b[0]) * (c[1] - d[1]) - (a[1] - b[1]) * (c[0] - d[0])
    t = ((a[0] - c[0]) * (c[1] - d[1]) - (a[1] - c[1]) * (c[0] - d[0])) / den
    return a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])


def stroke_shapes(points, closed, width, is_round):
    """Polygons and discs that together cover a stroked line."""
    half = width / 2
    polygons, discs = [], []
    pairs = list(zip(points, points[1:] + ([points[0]] if closed else [])))
    if not closed:
        pairs = pairs[:len(points) - 1]
    if is_round:  # round joins and caps: a box per segment, a disc per point
        for p, q in pairs:
            ox, oy = _offset(p, q, half)
            polygons.append([(p[0] + ox, p[1] + oy), (q[0] + ox, q[1] + oy),
                             (q[0] - ox, q[1] - oy), (p[0] - ox, p[1] - oy)])
        discs = [(p, half) for p in points]
        return polygons, discs
    # Square caps and mitred joins (the prompt): one outline polygon.
    ends = list(points)
    for index, (p, q) in ((0, pairs[0]), (-1, pairs[-1])):
        length = ((q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2) ** 0.5
        ux, uy = (q[0] - p[0]) / length * half, (q[1] - p[1]) / length * half
        ends[index] = (p[0] - ux, p[1] - uy) if index == 0 else (q[0] + ux, q[1] + uy)
    sides = []
    for sign in (1, -1):
        lines = []
        for p, q in zip(ends, ends[1:]):
            ox, oy = _offset(p, q, half * sign)
            lines.append(((p[0] + ox, p[1] + oy), (q[0] + ox, q[1] + oy)))
        side = [lines[0][0]]
        for one, two in zip(lines, lines[1:]):
            side.append(_meet(one[0], one[1], two[0], two[1]))
        side.append(lines[-1][1])
        sides.append(side)
    polygons.append(sides[0] + sides[1][::-1])
    return polygons, discs


class Canvas:
    """A float RGB picture that shapes are laid over with exact coverage."""

    def __init__(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        t = np.linspace(0.0, 1.0, height)[:, None, None]
        top, bottom = np.array(BACKGROUND_TOP, float), np.array(BACKGROUND_BOTTOM, float)
        self.rgb = np.broadcast_to(top + (bottom - top) * t, (height, width, 3)).copy()

    def coverage(self, polygons, discs, scale, dx, dy) -> np.ndarray:
        """How much of each pixel the shapes cover, 0..1 (drawn 8x and averaged)."""
        s = SUPERSAMPLE
        mask = Image.new('L', (self.width * s, self.height * s), 0)
        draw = ImageDraw.Draw(mask)
        for polygon in polygons:
            draw.polygon([((x * scale + dx) * s, (y * scale + dy) * s) for x, y in polygon], fill=255)
        for (x, y), r in discs:
            cx, cy, cr = (x * scale + dx) * s, (y * scale + dy) * s, r * scale * s
            draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=255)
        small = np.asarray(mask, dtype=np.float64).reshape(self.height, s, self.width, s)
        return small.mean(axis=(1, 3)) / 255.0

    def lay(self, alpha: np.ndarray, colour: tuple[int, int, int], strength: float = 1.0) -> None:
        a = (alpha * strength)[:, :, None]
        self.rgb = self.rgb * (1.0 - a) + np.array(colour, float) * a

    def watermark(self, mark: Mark, scale: float, dx: float, dy: float) -> None:
        points, closed, width, _colour, is_round = mark.outline
        line = self.coverage(*stroke_shapes(points, closed, width, is_round), scale, dx, dy)
        fill = self.coverage([points], [], scale, dx, dy)
        self.lay(np.maximum(fill - line, 0.0), WATERMARK, WATERMARK_FILL)
        self.lay(line, WATERMARK, WATERMARK_LINE)

    def mark(self, mark: Mark, height: float, left: float, top: float) -> None:
        scale = height / mark.size
        for points, closed, width, colour, is_round in mark.strokes:
            self.lay(self.coverage(*stroke_shapes(points, closed, width, is_round), scale, left, top), colour)
        for centre, radius, colour in mark.dots:
            self.lay(self.coverage([], [(centre, radius)], scale, left, top), colour)

    def text(self, ink: np.ndarray, colour, left: int, top: int) -> None:
        alpha = np.zeros((self.height, self.width))
        alpha[top:top + ink.shape[0], left:left + ink.shape[1]] = ink
        self.lay(alpha, colour)

    def pixels(self) -> np.ndarray:
        """8-bit RGB, with an ordered dither so the gradient shows no bands."""
        bayer = np.array([[0, 2], [3, 1]], float)
        for _ in range(2):
            bayer = np.block([[4 * bayer, 4 * bayer + 2], [4 * bayer + 3, 4 * bayer + 1]])
        threshold = (bayer + 0.5) / 64.0
        tiled = np.tile(threshold, (self.height // 8 + 1, self.width // 8 + 1))[:self.height, :self.width]
        return np.clip(np.floor(self.rgb + tiled[:, :, None]), 0, 255).astype(np.uint8)


# The lettering -------------------------------------------------------------

class Lettering:
    """The Neuronte large desktop face, drawing one line of text."""

    def __init__(self, release: Path) -> None:
        face = release / FACE
        digest = hashlib.sha256(face.read_bytes()).hexdigest()
        if digest != FACE_SHA256:
            raise SystemExit(f'{face}: SHA-256 {digest}, expected {FACE_SHA256}')
        self.lib = ctypes.CDLL(str(release / LIBRARY))
        self.lib.neuronte_open_file.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
        self.lib.neuronte_text_width.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int]
        self.lib.neuronte_draw_text.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_size_t,
            ctypes.c_uint32]
        self.lib.neuronte_close.argtypes = [ctypes.c_void_p]
        self.handle = ctypes.c_void_p()
        if self.lib.neuronte_open_file(str(face).encode(), ctypes.byref(self.handle)) != 0:
            raise SystemExit(f'cannot open {face}')

    def ink(self, text: str, em: int) -> np.ndarray:
        """Coverage 0..1 of the text at this size, cropped to its ink."""
        if em < 33:
            raise ValueError('the large face draws from 33 px up')
        raw = text.encode()
        width = self.lib.neuronte_text_width(self.handle, raw, len(raw), 0, em)
        if width <= 0:
            raise SystemExit('the face could not measure the lettering')
        w, h = width + 2 * em, 2 * em
        buffer = (ctypes.c_uint32 * (w * h))()
        moved = self.lib.neuronte_draw_text(self.handle, buffer, w, w, h, em // 2, 0, em, 0, raw, len(raw),
                                            0xFFFFFFFF)
        if moved != width:
            raise SystemExit('the face could not draw the lettering')
        alpha = (np.frombuffer(buffer, dtype=np.uint32).reshape(h, w) & 0xFF).astype(np.float64) / 255.0
        rows, cols = np.flatnonzero(alpha.any(axis=1)), np.flatnonzero(alpha.any(axis=0))
        return alpha[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]

    def close(self) -> None:
        self.lib.neuronte_close(self.handle)


# The three pictures ----------------------------------------------------------

def splash(mark: Mark, lettering: Lettering) -> np.ndarray:
    """640x480, behind the boot menu: the mark and name stay bottom right."""
    c = Canvas(640, 480)
    c.watermark(mark, 1.30, -120.0, -150.0)
    ink = lettering.ink(LETTERING, 34)
    axis = 616 - ink.shape[1] / 2
    c.mark(mark, 96, axis - 48, 316)
    c.text(ink, mark.outline[3], 616 - ink.shape[1], 452 - ink.shape[0])
    return c.pixels()


def banner(mark: Mark, lettering: Lettering) -> np.ndarray:
    """800x75, the strip above the graphical installer: mark, then name."""
    c = Canvas(800, 75)
    c.watermark(mark, 0.62, 560.0, -118.0)
    c.watermark(mark, 0.62, -30.0, -150.0)
    ink = lettering.ink(LETTERING, 40)
    gap, size = 22, 60
    left = (800 - (size + gap + ink.shape[1])) // 2
    c.mark(mark, size, left, 8)
    c.text(ink, mark.outline[3], left + size + gap, (75 - ink.shape[0]) // 2 + 1)
    return c.pixels()


def wallpaper(mark: Mark, lettering: Lettering) -> np.ndarray:
    """1920x1080 desktop: the mark and name bottom right, clear of the bars."""
    c = Canvas(1920, 1080)
    c.watermark(mark, 3.10, -330.0, -360.0)
    ink = lettering.ink(LETTERING, 76)
    c.text(ink, mark.outline[3], 1836 - ink.shape[1], 1016 - ink.shape[0])
    c.mark(mark, 168, 1836 - ink.shape[1] - 36 - 168, 1036 - 168)
    return c.pixels()


# PNG -------------------------------------------------------------------------

def png(pixels: np.ndarray) -> bytes:
    """An 8-bit RGB, non-interlaced PNG with only IHDR, IDAT and IEND."""
    height, width, _ = pixels.shape
    rows = pixels.reshape(height, width * 3).astype(np.int16)
    left = np.zeros_like(rows)
    left[:, 3:] = rows[:, :-3]
    above = np.zeros_like(rows)
    above[1:] = rows[:-1]
    candidates = [rows, rows - left, rows - above]  # filters 0, 1 and 2
    as_bytes = [(c & 0xFF).astype(np.uint8) for c in candidates]
    # Each row takes the filter whose bytes, read as signed, are smallest.
    cost = np.stack([np.minimum(b, 256 - b.astype(np.int32)).sum(axis=1) for b in as_bytes])
    choice = cost.argmin(axis=0)
    raw = bytearray()
    for y in range(height):
        raw.append(int(choice[y]))
        raw += as_bytes[choice[y]][y].tobytes()

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + chunk(b'IEND', b''))


def draw_all(release: Path) -> dict[str, bytes]:
    mark, lettering = Mark(), Lettering(release)
    try:
        strip = png(banner(mark, lettering))
        return {
            'assets/installer/splash.png': png(splash(mark, lettering)),
            'assets/installer/banner.png': strip,
            'assets/installer/banner-dark.png': strip,
            'assets/desktop/plebian-os.png': png(wallpaper(mark, lettering)),
        }
    finally:
        lettering.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--neuronte', required=True, type=Path, help='directory of a Neuronte release')
    parser.add_argument('--out', type=Path, default=ROOT, help='write under this directory (default: the repository)')
    parser.add_argument('--check', action='store_true', help='compare with the tracked files; write nothing')
    args = parser.parse_args()
    status = 0
    for name, data in draw_all(args.neuronte).items():
        digest = hashlib.sha256(data).hexdigest()
        if args.check:
            same = (ROOT / name).read_bytes() == data
            print(f"{'same' if same else 'DIFFERENT'}  {digest}  {name}")
            status |= 0 if same else 1
        else:
            target = args.out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            print(f'{digest}  {name}  {len(data)} bytes')
    return status


if __name__ == '__main__':
    sys.exit(main())
