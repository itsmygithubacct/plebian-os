import hashlib
import importlib.util
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "build" / "draw-artwork.py"
DRAWN = (
    "assets/installer/splash.png",
    "assets/installer/banner.png",
    "assets/installer/banner-dark.png",
    "assets/desktop/plebian-os.png",
)

try:
    import numpy as np
    import PIL  # noqa: F401
except ImportError:  # the drawing program is an authoring tool, not a build input
    np = None
    draw_artwork = None
else:
    SPEC = importlib.util.spec_from_file_location("draw_artwork", PROGRAM)
    if SPEC is None or SPEC.loader is None:  # pragma: no cover - import machinery guard
        raise RuntimeError(f"cannot load {PROGRAM}")
    draw_artwork = importlib.util.module_from_spec(SPEC)
    sys.modules[SPEC.name] = draw_artwork
    SPEC.loader.exec_module(draw_artwork)


def decode_png(data):
    """Pixels of an 8-bit RGB PNG that uses filters 0, 1 and 2 only."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    chunks, at = [], 8
    while at < len(data):
        (length,), kind = struct.unpack(">I", data[at:at + 4]), data[at + 4:at + 8]
        body = data[at + 8:at + 8 + length]
        assert struct.unpack(">I", data[at + 8 + length:at + 12 + length])[0] == zlib.crc32(kind + body)
        chunks.append((kind, body))
        at += 12 + length
    width, height, depth, colour, _, _, interlace = struct.unpack(">IIBBBBB", chunks[0][1])
    assert (depth, colour, interlace) == (8, 2, 0)
    raw = zlib.decompress(b"".join(body for kind, body in chunks if kind == b"IDAT"))
    stride = width * 3
    rows, previous = [], bytes(stride)
    for y in range(height):
        kind, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if kind == 1:
            for x in range(3, stride):
                line[x] = (line[x] + line[x - 3]) & 0xFF
        elif kind == 2:
            for x in range(stride):
                line[x] = (line[x] + previous[x]) & 0xFF
        else:
            assert kind == 0, kind
        rows.append(bytes(line))
        previous = rows[-1]
    return [kind for kind, _ in chunks], width, height, rows


@unittest.skipIf(draw_artwork is None, "NumPy and Pillow are needed to load the drawing program")
class ArtworkDrawingTests(unittest.TestCase):
    def test_path_reader_reads_the_mark_and_refuses_anything_else(self):
        points, closed = draw_artwork.parse_path("M92 446V104H314L422 212 314 320H211L92 446Z")
        self.assertTrue(closed)
        self.assertEqual(points, [(92, 446), (92, 104), (314, 104), (422, 212), (314, 320), (211, 320)])
        points, closed = draw_artwork.parse_path("M163 164L222 218 163 272")
        self.assertFalse(closed)
        self.assertEqual(points, [(163, 164), (222, 218), (163, 272)])
        self.assertEqual(draw_artwork.parse_path("M253 272H323"), ([(253, 272), (323, 272)], False))
        for unsupported in ("M0 0C1 1 2 2 3 3", "m0 0l5 5", "M0 0A5 5 0 0 0 9 9", "M0 0Q1 1 2 2", "M0 0L5", "M0 0L5 H9"):
            with self.subTest(d=unsupported), self.assertRaises(ValueError):
                draw_artwork.parse_path(unsupported)

    def test_mark_is_read_from_the_tracked_vector(self):
        mark = draw_artwork.Mark()
        self.assertEqual(mark.size, 512)
        self.assertEqual([len(points) for points, *_ in mark.strokes], [6, 2, 2, 3, 2])
        self.assertEqual([closed for _, closed, *_ in mark.strokes], [True, False, False, False, False])
        self.assertEqual([width for _, _, width, _, _ in mark.strokes], [36, 36, 36, 28, 28])
        self.assertEqual({colour for *_, colour, _ in mark.strokes}, {(0xAA, 0xC5, 0xDA), (0xFF, 0x9F, 0x0A)})
        self.assertEqual([is_round for *_, is_round in mark.strokes], [True, True, True, False, False])
        self.assertEqual(mark.dots, [((319, 180), 18, (0xAA, 0xC5, 0xDA))])
        with tempfile.TemporaryDirectory() as td:
            other = Path(td) / "logo.svg"
            other.write_text(draw_artwork.LOGO.read_text().replace('<circle cx="319" cy="180" r="18" fill="#aac5da"/>', ""))
            with self.assertRaises(ValueError):
                draw_artwork.Mark(other)

    def test_strokes_cover_what_the_vector_says(self):
        # A round stroke: a box per segment and a disc per point.
        polygons, discs = draw_artwork.stroke_shapes([(0, 0), (10, 0)], False, 4, True)
        self.assertEqual(polygons, [[(0, 2), (10, 2), (10, -2), (0, -2)]])
        self.assertEqual(discs, [((0, 0), 2), ((10, 0), 2)])
        # A square-capped straight line reaches half its width past each end.
        (polygon,), discs = draw_artwork.stroke_shapes([(0, 0), (10, 0)], False, 4, False)
        self.assertEqual(discs, [])
        self.assertEqual(sorted(polygon), [(-2, -2), (-2, 2), (12, -2), (12, 2)])
        # A right-angle corner is mitred to a point, not cut off or rounded.
        (polygon,), _ = draw_artwork.stroke_shapes([(0, 0), (10, 0), (10, 10)], False, 4, False)
        self.assertEqual(len(polygon), 6)
        self.assertIn((12.0, -2.0), [(round(x, 9), round(y, 9)) for x, y in polygon])
        canvas = draw_artwork.Canvas(16, 8)
        cover = canvas.coverage([[(2, 2), (6, 2), (6, 6), (2, 6)]], [], 1.0, 0.0, 0.0)
        self.assertEqual(float(cover[3, 3]), 1.0)
        self.assertEqual(float(cover[0, 0]), 0.0)
        # Pillow fills the samples on both edges of a polygon, so a shape comes
        # out one sample (an eighth of a pixel) wider and taller than drawn.
        self.assertAlmostEqual(float(cover.sum()), (4 + 1 / 8) ** 2, delta=0.01)
        half = canvas.coverage([[(2, 2), (6, 2), (6, 6), (2, 6)]], [], 1.0, 0.5, 0.0)
        self.assertAlmostEqual(float(half[3, 2]), 0.5, delta=0.07)

    def test_png_writer_round_trips_and_writes_three_chunks(self):
        height, width = 37, 53
        y, x = np.mgrid[0:height, 0:width]
        pixels = np.stack([(x * 7 + y * 3) % 256, (x * x + y) % 256, (x ^ (y * 5)) % 256], axis=2).astype(np.uint8)
        pixels[10:20] = pixels[9]          # rows the "up" filter wins
        pixels[25:30, :, :] = 200          # rows the "left" filter wins
        data = draw_artwork.png(pixels)
        kinds, got_width, got_height, rows = decode_png(data)
        self.assertEqual(kinds, [b"IHDR", b"IDAT", b"IEND"])
        self.assertEqual((got_width, got_height), (width, height))
        self.assertEqual(b"".join(rows), pixels.tobytes())
        self.assertEqual(draw_artwork.png(pixels), data)

    def test_tracked_drawings_are_what_the_program_describes(self):
        strip = (ROOT / "assets/installer/banner.png").read_bytes()
        self.assertEqual((ROOT / "assets/installer/banner-dark.png").read_bytes(), strip)
        orange = bytes((0xFF, 0x9F, 0x0A))
        for name, size in zip(DRAWN, ((640, 480), (800, 75), (800, 75), (1920, 1080))):
            with self.subTest(name=name):
                kinds, width, height, rows = decode_png((ROOT / name).read_bytes())
                self.assertEqual(kinds, [b"IHDR", b"IDAT", b"IEND"])
                self.assertEqual((width, height), size)
                # Where the faint outline does not cross it, the top row is the
                # plain gradient: dark, and dithered by one level at most.
                for channel, base in enumerate(draw_artwork.BACKGROUND_TOP):
                    self.assertIn(min(rows[0][channel::3]) - base, (0, 1))
                    self.assertLess(max(rows[0][channel::3]) - base, 24)
                # The prompt's orange appears, and only inside the small mark.
                columns = {x for row in rows for x in range(0, width * 3, 3) if row[x:x + 3] == orange}
                lines = {y for y, row in enumerate(rows) if orange in row}
                self.assertTrue(columns)
                self.assertLess((max(columns) - min(columns)) // 3, width // 8)
                self.assertLess(max(lines) - min(lines), max(height // 6, 30))

    def test_a_different_weight_file_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "weights").mkdir()
            (Path(td) / draw_artwork.FACE).write_bytes(b"not the face")
            with self.assertRaises(SystemExit) as refused:
                draw_artwork.Lettering(Path(td))
            self.assertIn(draw_artwork.FACE_SHA256, str(refused.exception))

    @unittest.skipUnless(
        os.environ.get("NEURONTE_HOME"),
        "set NEURONTE_HOME to a Neuronte release to redraw the tracked artwork",
    )
    def test_redrawing_gives_the_tracked_bytes(self):
        drawn = draw_artwork.draw_all(Path(os.environ["NEURONTE_HOME"]))
        self.assertEqual(sorted(drawn), sorted(DRAWN))
        for name, data in drawn.items():
            with self.subTest(name=name):
                self.assertEqual(
                    hashlib.sha256(data).hexdigest(),
                    hashlib.sha256((ROOT / name).read_bytes()).hexdigest(),
                )


if __name__ == "__main__":
    unittest.main()
