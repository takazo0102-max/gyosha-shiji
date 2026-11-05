"""スモークの「プレビューが真っ白か」の判定（PIL 無しで PNG を読む）."""

import struct
import sys
import unittest
import zlib
from pathlib import Path

from _path import SRC  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def _png(width, height, dark_cols=()):
    rows = b""
    for _y in range(height):
        line = bytearray(b"\xff" * (width * 3))
        for x in dark_cols:
            line[x * 3:x * 3 + 3] = b"\x00\x00\x00"
        rows += b"\x00" + bytes(line)

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


class TestBlank(unittest.TestCase):
    def test_white_is_blank_and_a_line_is_not(self):
        from bisect_gdl import _dark_pixels, is_blank

        self.assertTrue(is_blank(_png(200, 100)))
        drawn = _png(200, 100, dark_cols=(50,))
        self.assertEqual(_dark_pixels(drawn), (100, 20000))
        self.assertFalse(is_blank(drawn))


if __name__ == "__main__":
    unittest.main()
