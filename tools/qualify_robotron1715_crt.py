#!/usr/bin/env python3
"""Execute the CRT ROM kit on DAC; produce checked rasters and JSON evidence."""

import argparse
import hashlib
import json
import struct
import subprocess
import zlib
from pathlib import Path

from build_robotron1715_crt import NAMES, assets, build


def png(path, width, height, rgb):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    scan = b"".join(
        b"\0" + rgb[y * width * 3 : (y + 1) * width * 3] for y in range(height)
    )
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(scan))
        + chunk(b"IEND", b"")
    )


def ppm(path):
    data = path.read_bytes()
    header = b"P6\n640 288\n255\n"
    assert data.startswith(header) and len(data) == len(header) + 640 * 288 * 3
    return data[len(header) :]


def reference(stream, glyphs):
    """Independent whole-frame reference for this kit's restricted stream grammar.

    Each attribute immediately precedes its visible FIFO character. No timing,
    CPU, pending row buffers or emulator renderer are used here.
    """
    image = bytearray(640 * 288 * 3)
    pos = 0
    attr = 0
    for row in range(24):
        count = 0
        for col in range(80):
            char = stream[pos]
            pos += 1
            if char & 128:
                assert char & 0xC0 == 0x80
                attr = char & 63
                count += 1
                char = stream[pos]
                pos += 1
            assert char < 128
            for y in range(12):
                bits = glyphs[(2048 if attr & 4 else 0) + 128 * y + char]
                for x in range(8):
                    value = (255 if attr & 1 else 170) if bits & (128 >> x) else 0
                    i = ((row * 12 + y) * 640 + col * 8 + x) * 3
                    image[i : i + 3] = bytes([value]) * 3
        assert count <= 16
    assert pos == len(stream) <= 2048
    return bytes(image)


def expected(glyphs, streams, index, screen=0xF800, work=0xF700):
    stream = bytearray(streams[index])
    if index == 0:
        line = "RAM SCREEN: 0000  WORK: 0000"
        start = (80 - len(line)) // 2
        for offset, address in (
            (line.index("0000"), screen),
            (line.rindex("0000"), work),
        ):
            at = 9 * 81 + 1 + start + offset
            stream[at : at + 4] = f"{address:04X}".encode()
    return reference(stream, glyphs)


def run(runner, kit, out, seconds, fault="clean"):
    out.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            str(runner),
            str(kit / "boot.bin"),
            str(kit / "glyphs.bin"),
            str(out),
            str(seconds),
            fault,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    (out / "run.json").write_text(json.dumps(data, indent=2) + "\n")
    assert data["rom_enabled"] == 1
    for key in ("underruns", "overflows", "unexpected_io", "unclaimed_reads"):
        assert data[key] == 0, (fault, key, data[key])
    return data


def contact_sheet(path, images, glyphs):
    """Full horizontal resolution avoids aliasing away fine CRT test patterns."""
    width, height = 1920, 2016
    sheet = bytearray(width * height * 3)
    for n, raster in enumerate(images):
        left, top = (n % 3) * 640, (n // 3) * 504
        label = f"{n + 1:02d} {NAMES[n].upper()}"
        for col, char in enumerate(label):
            for y in range(12):
                bits = glyphs[y * 128 + ord(char)]
                for x in range(8):
                    if bits & (128 >> x):
                        for dy in range(2):
                            for dx in range(2):
                                at = (
                                    (top + 2 * y + dy) * width
                                    + left
                                    + col * 16
                                    + x * 2
                                    + dx
                                ) * 3
                                sheet[at : at + 3] = b"\xff" * 3
        for y in range(480):
            source = (y * 288 // 480) * 640 * 3
            dest = ((top + 24 + y) * width + left) * 3
            sheet[dest : dest + 1920] = raster[source : source + 1920]
    png(path, width, height, bytes(sheet))


def qualify(dac, out):
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["make", "-C", str(dac), "build/pc1715-crt-capture", "test-pc1715-video"],
        check=True,
    )
    runner = dac / "build/pc1715-crt-capture"
    kit = out / "cycle"
    manifest = build(kit)
    glyphs, streams, _ = assets()
    report = {"manifest": manifest, "qualification": "emulator-only", "runs": {}}
    cycle = run(runner, kit, out / "cycle-run", 242)
    transitions = cycle["transitions"]
    assert [t["pattern"] for t in transitions] == list(range(12)) * 2 + [0]
    dwell = [
        (b["cycle"] - a["cycle"]) / cycle["clock_hz"]
        for a, b in zip(transitions, transitions[1:])
    ]
    assert all(9.5 <= d <= 10.5 for d in dwell)
    report["dwell_seconds"] = dwell
    report["runs"]["cycle"] = cycle
    images = []
    for n, t in enumerate(transitions):
        raster = ppm(out / "cycle-run" / f"frame-{n:02d}.ppm")
        assert raster == expected(
            glyphs, streams, t["pattern"], t["screen"], t["work"]
        ), (n, t)
        if n < 12:
            images.append(raster)
            png(out / f"{NAMES[n]}-raw.png", 640, 288, raster)
            corrected = b"".join(
                raster[(y * 288 // 480) * 640 * 3 : (y * 288 // 480 + 1) * 640 * 3]
                for y in range(480)
            )
            png(out / f"{NAMES[n]}-4x3.png", 640, 480, corrected)
    # Independent simple-pattern invariants catch inverted bits/phase/intensity.
    assert not any(images[7])
    assert set(images[8]) == {170}
    assert images[3][:24] == bytes([170, 170, 170, 0, 0, 0]) * 4
    assert images[4][: 640 * 3] == bytes([170]) * (640 * 3)
    assert not any(images[4][640 * 3 : 1280 * 3])
    assert sum(v != 0 for v in images[5][::3]) == 80 * 24
    contact_sheet(out / "contact-sheet.png", images, glyphs)
    for fault, screen, work in (
        ("screen", 0xF000, 0xEF00),
        ("work", 0xF800, 0xF600),
        ("alias", 0xF800, 0xF600),
    ):
        result = run(runner, kit, out / fault, 3, fault)
        t = result["transitions"][0]
        assert (t["screen"], t["work"]) == (screen, work), t
        assert ppm(out / fault / "frame-00.ppm") == expected(
            glyphs, streams, 0, screen, work
        )
        report["runs"][fault] = result
    dead = run(runner, kit, out / "dead", 3, "dead")
    assert not dead["transitions"] and dead["fetches"] == 0 and dead["sp"] == 65535
    assert dead["pc"] < 2048
    report["runs"]["dead"] = dead
    reset = run(runner, kit, out / "reset", 3, "reset")
    assert [t["pattern"] for t in reset["transitions"]] == [0, 0]
    for frame in (0, 1):
        assert ppm(out / "reset" / f"frame-{frame:02d}.ppm") == expected(
            glyphs, streams, 0
        )
    report["runs"]["reset"] = reset
    for index, name in enumerate(NAMES):
        print(f"Qualifying fixed {name}", flush=True)
        fixed = out / ("fixed-" + name)
        build(fixed, name)
        result = run(runner, fixed, fixed / "run", 21)
        assert (
            len(result["transitions"]) == 1
            and result["transitions"][0]["pattern"] == index
        )
        for frame in (0, 110, 120):
            assert ppm(fixed / "run" / f"frame-{frame:02d}.ppm") == expected(
                glyphs, streams, index
            ), (name, frame)
        report["runs"][name] = result
    report["raster_sha256"] = {
        name: hashlib.sha256(im).hexdigest() for name, im in zip(NAMES, images)
    }
    report["dac_revision"] = subprocess.check_output(
        ["git", "-C", str(dac), "rev-parse", "HEAD"], text=True
    ).strip()
    report["dac_dirty"] = bool(
        subprocess.check_output(
            ["git", "-C", str(dac), "status", "--porcelain"], text=True
        )
    )
    (out / "qualification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS: two cycles, twelve fixed holds, RAM faults; evidence in {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dac", type=Path, default=Path("../dac-emulation"))
    parser.add_argument(
        "--out", type=Path, default=Path("build/robotron1715-crt-qualified")
    )
    args = parser.parse_args()
    qualify(args.dac.resolve(), args.out.resolve())
