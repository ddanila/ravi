"""ROM asset limits and compression format consumed by the Z80 decoder."""

import importlib.util
import unittest
from pathlib import Path

BUILDER = Path(__file__).resolve().parents[1] / "tools/build_robotron1715_crt.py"
spec = importlib.util.spec_from_file_location("crt_builder", BUILDER)
crt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crt)


def unpack(data):
    output = bytearray()
    it = iter(data)
    for token in it:
        if not token:
            return bytes(output)
        if token < 128:
            output.extend(next(it) for _ in range(token))
        else:
            distance = next(it) + 256 * next(it)
            if not 0 < distance <= len(output):
                raise ValueError("invalid match")
            for _ in range((token & 127) + 3):
                output.append(output[-distance])
    raise ValueError("missing terminator")


class CRTAssets(unittest.TestCase):
    def test_overlapping_matches_and_binary_literals(self):
        for source in (b"", b"A" * 1024, bytes(range(256)) * 3, bytes(range(127))):
            self.assertEqual(unpack(crt.compress(source)), source)

    def test_streams_fit_rom_and_per_row_fifo(self):
        glyphs, streams, tiles = crt.assets()
        self.assertEqual(len(glyphs), 4096)
        self.assertLessEqual(tiles, 160)
        for stream in streams:
            self.assertLessEqual(len(stream), 2048)
            self.assertEqual(unpack(crt.compress(stream)), stream)
            data = iter(stream)
            for row in range(24):
                attributes = 0
                for col in range(80):
                    char = next(data)
                    if char & 128:
                        self.assertEqual(char & 0xC0, 0x80)
                        attributes += 1
                        char = next(data)
                    self.assertLess(char, 128)
                self.assertLessEqual(attributes, 16)
            self.assertEqual(list(data), [])


if __name__ == "__main__":
    unittest.main()
