#!/usr/bin/env python3
"""Build the original 80x24 PC1715 CRT ROM kit (requires z80asm)."""

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    "identity",
    "grid",
    "circle",
    "vertical",
    "horizontal",
    "dots",
    "checker",
    "black",
    "white",
    "window",
    "glyphs",
    "intensity",
)
# Original compact 5x7 alphabet. Each hex digit pair is a five-bit row.
FONT = {
    "A": "0E11111F111111",
    "B": "1E11111E11111E",
    "C": "0F10101010100F",
    "D": "1E11111111111E",
    "E": "1F10101E10101F",
    "F": "1F10101E101010",
    "G": "0F10101711110F",
    "H": "1111111F111111",
    "I": "0E04040404040E",
    "J": "0702020212120C",
    "K": "11121418141211",
    "L": "1010101010101F",
    "M": "111B1515111111",
    "N": "11191915131311",
    "O": "0E11111111110E",
    "P": "1E11111E101010",
    "Q": "0E11111115120D",
    "R": "1E11111E141211",
    "S": "0F10100E01011E",
    "T": "1F040404040404",
    "U": "1111111111110E",
    "V": "11111111110A04",
    "W": "11111115151B11",
    "X": "11110A040A1111",
    "Y": "11110A04040404",
    "Z": "1F01020408101F",
    "0": "0E11131519110E",
    "1": "040C040404040E",
    "2": "0E11010204081F",
    "3": "1E01010601011E",
    "4": "02060A121F0202",
    "5": "1F10101E01011E",
    "6": "0E10101E11110E",
    "7": "1F010204080808",
    "8": "0E11110E11110E",
    "9": "0E11110F01010E",
    ":": "00040400040400",
    "-": "0000001F000000",
    ".": "00000000000C0C",
    "/": "01010204081010",
    "+": "0004041F040400",
    "=": "00001F001F0000",
}


def compress(data):
    """Small greedy LZ: literals 1..127, match 128..255 = 3..130 + LE distance."""
    out = bytearray()
    literal = bytearray()

    def flush():
        while literal:
            n = min(127, len(literal))
            out.append(n)
            out.extend(literal[:n])
            del literal[:n]

    i = 0
    while i < len(data):
        best, distance = 0, 0
        for j in range(i):
            if data[j : j + 3] != data[i : i + 3]:
                continue
            n = 3
            while n < min(130, len(data) - i) and data[j + n] == data[i + n]:
                n += 1
            if n > best:
                best, distance = n, i - j
        if best >= 4:
            flush()
            out.extend((128 + best - 3, distance & 255, distance >> 8))
            i += best
        else:
            literal.append(data[i])
            i += 1
    flush()
    out.append(0)
    return bytes(out)


def assets():
    banks = [[bytes(16) for _ in range(128)] for _ in range(2)]
    for c, rows in FONT.items():
        banks[0][ord(c)] = bytes(
            [0, 0] + [v << 2 for v in bytes.fromhex(rows)] + [0] * 7
        )
    tiles = [
        bytes(12),
        bytes([255] * 12),
        bytes([0xAA] * 12),
        bytes(255 if y % 2 == 0 else 0 for y in range(12)),
        bytes(0x80 if y == 0 else 0 for y in range(12)),
        bytes(0xAA if y % 2 == 0 else 0x55 for y in range(12)),
    ]

    # Grid/circle tiles share bank 1; all geometry is generated, not a copied font.
    def tile(value):
        b = bytes(value)
        if b not in tiles:
            tiles.append(b)
        return tiles.index(b)

    def geometry(circle=False):
        result = []
        for row in range(24):
            cells = []
            for col in range(80):
                pixels = []
                for dy in range(12):
                    y = row * 12 + dy
                    b = 0
                    for dx in range(8):
                        x = col * 8 + dx
                        on = x in (0, 639, 319, 320) or y in (0, 287, 143, 144)
                        on |= x % 80 == 0 or y % 48 == 0
                        # 640x288 active raster stretched to 4:3. Radius in units
                        # of vertical pixels: x scale=0.6, so this is a circle.
                        if circle:
                            r = math.hypot((x - 319.5) * 0.6, y - 143.5)
                            on |= abs(r - 126) < 0.65
                        b = (b << 1) | on
                    pixels.append(b)
                cells.append(tile(pixels))
            result.append(cells)
        return result

    grid = geometry()
    circle = geometry(True)
    if len(tiles) > 160:
        raise ValueError(f"{len(tiles)} geometry tiles exceed banks")
    for i, t in enumerate(tiles):
        banks[1 if i < 128 else 0][i % 128] = t + bytes(4)

    def blank(code=0):
        return [[code] * 80 for _ in range(24)]

    def text(rows, y, s):
        start = (80 - len(s)) // 2
        rows[y][start : start + len(s)] = s.encode("ascii")

    ident = blank(32)
    for y, s in (
        (3, "RAVI PC1715 CRT 1.3"),
        (6, "80 X 24  -  640 X 288"),
        (9, "RAM SCREEN: 0000  WORK: 0000"),
        (12, "12 PATTERNS  -  10 SECONDS"),
        (15, "NO KEYBOARD OR DISK REQUIRED"),
        (18, "RESET TO RESTART"),
    ):
        text(ident, y, s)

    # Every row begins with an invisible field attribute plus its FIFO glyph.
    def stream(rows, bank=1, attributes=None):
        out = bytearray()
        for y, row in enumerate(rows):
            current = 0 if bank and row[0] >= 128 else bank
            out.append(0x80 | current * 4)
            for x, c in enumerate(row):
                if bank:
                    wanted = 0 if c >= 128 else 1
                    if wanted != current:
                        out.append(0x80 | wanted * 4)
                    current = wanted
                    c %= 128
                if attributes and x in attributes.get(y, {}):
                    out.append(attributes[y][x])
                out.append(c)
        if len(out) > 2048:
            raise ValueError("Display stream exceeds 2 KiB")
        return bytes(out)

    window = blank()
    for y in range(9, 15):
        window[y][30:50] = [1] * 20
    chart = blank(32)
    text(chart, 1, "STANDARD GLYPHS")
    text(chart, 12, "ALTERNATE TILES")
    for y in range(4):
        chart[4 + y][8:40] = list(range(y * 32, y * 32 + 32))
    for y in range(4):
        chart[15 + y][8:40] = list(range(y * 32, y * 32 + 32))
    chartdata = bytearray()
    for y, row in enumerate(chart):
        chartdata.extend(bytes([0x84 if 15 <= y < 19 else 0x80]) + bytes(row))
    intensity = blank(32)
    for y, s in (
        (1, "INTENSITY AND DITHER"),
        (5, "NORMAL"),
        (10, "HIGH"),
        (15, "DITHER 50 PERCENT"),
        (20, "DITHER IS NOT ANALOG GREY"),
    ):
        text(intensity, y, s)
    attrs = {}
    for y in (7, 8, 12, 13, 17, 18):
        intensity[y][16:64] = [5 if y >= 17 else 1] * 48
        attrs[y] = {16: 0x85 if y in (12, 13) else 0x84, 64: 0x80}
    streams = [
        stream(ident, 0),
        stream(grid),
        stream(circle),
        stream(blank(2)),
        stream(blank(3)),
        stream(blank(4)),
        stream(blank(5)),
        stream(blank()),
        stream(blank(1)),
        stream(window),
        bytes(chartdata),
        stream(intensity, 0, attrs),
    ]
    glyphs = bytes(
        banks[b][c][y] for b in range(2) for y in range(16) for c in range(128)
    )
    return glyphs, streams, len(tiles)


def build(output, pattern="cycle"):
    output.mkdir(parents=True, exist_ok=True)
    glyphs, streams, tiles = assets()
    compressed = [compress(s) for s in streams]
    asm = (ROOT / "firmware/robotron1715-crt/boot.asm").read_text()
    line = "RAM SCREEN: 0000  WORK: 0000"
    start = (80 - len(line)) // 2
    asm = asm.replace("@SCREEN_ADDR@", str(9 * 81 + 1 + start + line.index("0000")))
    asm = asm.replace("@WORK_ADDR@", str(9 * 81 + 1 + start + line.rindex("0000")))
    asm = asm.replace("@FIRST@", str(0 if pattern == "cycle" else NAMES.index(pattern)))
    asm = asm.replace(
        "@ADVANCE@",
        "inc a\n cp 12\n jr c, selected\n xor a"
        if pattern == "cycle"
        else "jp hold",
    )
    asm += "\nnames:\n"
    for name in NAMES:
        data = name.upper().encode("ascii")
        asm += " db " + ",".join(map(str, [len(data), *data])) + "\n"
    asm += "\npatterns:\n dw " + ",".join("p" + str(i) for i in range(12)) + "\n"
    for i, data in enumerate(compressed):
        asm += f"p{i}:\n"
        for j in range(0, len(data), 24):
            asm += " db " + ",".join(str(b) for b in data[j : j + 24]) + "\n"
    source = output / "boot.asm"
    source.write_text(asm)
    binary = output / "boot.bin"
    subprocess.run(["z80asm", "-o", str(binary), str(source)], check=True)
    raw = binary.read_bytes()
    if len(raw) > 2048:
        raise ValueError(
            f"Boot uses {len(raw)} bytes (limit 2048); data {sum(map(len, compressed))}"
        )
    binary.write_bytes(raw + bytes([255]) * (2048 - len(raw)))
    files = {
        "boot.bin": binary.read_bytes(),
        "glyph-standard.bin": glyphs[:2048],
        "glyph-alternate.bin": glyphs[2048:],
        "glyphs.bin": glyphs,
    }
    for name, data in files.items():
        (output / name).write_bytes(data)
    manifest = {
        "source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                Path(__file__).resolve(),
                ROOT / "firmware/robotron1715-crt/boot.asm",
            )
        },
        "version": "1.3",
        "pattern": pattern,
        "presentation": {"title_seconds": 1, "pattern_seconds": 10 if pattern == "cycle" else None,
                         "title_style": "centered-on-black", "phase_work_offset": 1,
                         "phase_values": {"title": 0, "pattern": 1}},
        "boot_used": len(raw),
        "tile_count": tiles,
        "stream_bytes": list(map(len, streams)),
        "compressed_bytes": list(map(len, compressed)),
        "sockets": {
            "A25.3": "boot.bin",
            "A25.2": "glyph-standard.bin",
            "A25.1": "glyph-alternate.bin",
        },
        "files": {
            n: {"bytes": len(d), "sha256": hashlib.sha256(d).hexdigest()}
            for n, d in files.items()
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pattern", choices=("cycle",) + NAMES, default="cycle")
    parser.add_argument("--out", type=Path, default=ROOT / "build/robotron1715-crt")
    args = parser.parse_args()
    print(json.dumps(build(args.out, args.pattern), indent=2))
