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


def title_reference(glyphs, index):
    # Independently construct visible cells; no firmware name-table decoding.
    rows = bytearray(b" " * 1920)
    name = NAMES[index].upper().encode("ascii")
    offset = 11 * 80 + (80 - len(name)) // 2
    rows[offset : offset + len(name)] = name
    return reference(b"\x80" + rows, glyphs)


def phase_reference(glyphs, streams, transition):
    if transition["phase"] == "title":
        return title_reference(glyphs, transition["pattern"])
    return expected(
        glyphs, streams, transition["pattern"], transition["screen"], transition["work"]
    )


def assemble(folder, source):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "boot.asm").write_text(source)
    binary = folder / "boot.bin"
    subprocess.run(["z80asm", "-o", str(binary), str(folder / "boot.asm")], check=True)
    raw = binary.read_bytes()
    assert len(raw) <= 2048
    binary.write_bytes(raw + b"\xff" * (2048 - len(raw)))
    return binary


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
    assert data["io_reads"] == 0, (fault, "unexpected CPU input", data)
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
    # Negative controls reproduce each hardware-assumption error separately.
    # Assemble real changed firmware, not a renderer that recognizes patterns.
    source = (kit / "boot.asm").read_text()
    mutations = {
        "floppy-port": source.replace("out (034h),a", "out (022h),a"),
        "wrong-address-bits": source.replace(
            "rrca\n rrca\n and 03eh", "rrca\n rrca\n rrca\n and 31"
        ),
    }
    report["rejected_mutations"] = {}
    for name, asm in mutations.items():
        assert asm != source
        folder = out / name
        folder.mkdir(exist_ok=True)
        (folder / "boot.asm").write_text(asm)
        binary = folder / "boot.bin"
        subprocess.run(
            ["z80asm", "-o", str(binary), str(folder / "boot.asm")], check=True
        )
        raw = binary.read_bytes()
        assert len(raw) <= 2048
        binary.write_bytes(raw + b"\xff" * (2048 - len(raw)))
        result = subprocess.run(
            [
                str(runner),
                str(binary),
                str(kit / "glyphs.bin"),
                str(folder),
                "3",
                "clean",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        data = json.loads(result.stdout)
        assert ppm(folder / "frame-00.ppm") != title_reference(glyphs, 0), name
        assert data["unexpected_io"] == (1 if name == "floppy-port" else 0)
        report["rejected_mutations"][name] = data
    # A23.1 prevents status reads. Reintroduce the 1.1 polling loop and
    # hold the otherwise floating CPU input low: first screen must get stuck.
    # This is the hardware symptom, not an assumption about open-bus voltage.
    # The old bounded wait itself is sufficient to reproduce repeated resets;
    # the 513-successful-frame counter is irrelevant when no flag ever arrives.
    old_wait = """delay:
 ld de,0
wait_frame:
 in a,(019h)
 and 020h
 ret nz
 dec de
 ld a,d
 or e
 jr nz,wait_frame
 jp initialise
"""
    begin = source.index("delay:\n")
    end = source.index("; LZ decoder:", begin)
    folder = out / "status-polling-regression"
    folder.mkdir(exist_ok=True)
    (folder / "boot.asm").write_text(source[:begin] + old_wait + source[end:])
    binary = folder / "boot.bin"
    subprocess.run(["z80asm", "-o", str(binary), str(folder / "boot.asm")], check=True)
    raw = binary.read_bytes()
    assert len(raw) <= 2048
    binary.write_bytes(raw + b"\xff" * (2048 - len(raw)))
    result = subprocess.run(
        [
            str(runner),
            str(binary),
            str(kit / "glyphs.bin"),
            str(folder),
            "6",
            "status-low",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    broken = json.loads(result.stdout)
    assert [t["pattern"] for t in broken["transitions"]] == [0]
    assert broken["display_starts"] >= 4 and broken["status_reads"] > 100000
    report["rejected_mutations"]["status-polling"] = broken
    # New firmware advances at the same speed even with low floating inputs.
    low = run(runner, kit, out / "status-low", 25, "status-low")
    assert [(t["pattern"], t["phase"]) for t in low["transitions"]] == [
        (i, phase) for i in range(3) for phase in ("title", "pattern")
    ]
    assert low["display_starts"] == 6 and low["status_reads"] == 0
    report["runs"]["status-low"] = low
    cycle = run(runner, kit, out / "cycle-run", 268)
    transitions = cycle["transitions"]
    assert [(t["pattern"], t["phase"]) for t in transitions] == [
        (i, phase) for i in list(range(12)) * 2 + [0] for phase in ("title", "pattern")
    ]
    assert cycle["display_starts"] == len(transitions)
    dwell = [
        (b["cycle"] - a["cycle"]) / cycle["clock_hz"]
        for a, b in zip(transitions, transitions[1:])
    ]
    assert all(
        0.9 <= d <= 1.1 if transitions[n]["phase"] == "title" else 9.9 <= d <= 10.2
        for n, d in enumerate(dwell)
    )
    report["title_seconds"] = dwell[::2]
    report["dwell_seconds"] = dwell[1::2]
    report["runs"]["cycle"] = cycle
    images = []
    for n, t in enumerate(transitions):
        raster = ppm(out / "cycle-run" / f"frame-{n:02d}.ppm")
        assert raster == phase_reference(glyphs, streams, t), (n, t)
        if n == 0:
            png(out / "title-example.png", 640, 288, raster)
        if n < 24 and t["phase"] == "pattern":
            images.append(raster)
            name = NAMES[t["pattern"]]
            png(out / f"{name}-raw.png", 640, 288, raster)
            corrected = b"".join(
                raster[(y * 288 // 480) * 640 * 3 : (y * 288 // 480 + 1) * 640 * 3]
                for y in range(480)
            )
            png(out / f"{name}-4x3.png", 640, 480, corrected)
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
        for n, t in enumerate(result["transitions"]):
            assert ppm(out / fault / f"frame-{n:02d}.ppm") == phase_reference(
                glyphs, streams, t
            )
        report["runs"][fault] = result
    dead = run(runner, kit, out / "dead", 3, "dead")
    assert not dead["transitions"] and dead["fetches"] == 0 and dead["sp"] == 65535
    assert dead["pc"] < 2048
    report["runs"]["dead"] = dead
    for fault, phases in (
        ("reset", ["title", "title", "pattern"]),
        ("reset-pattern", ["title", "pattern", "title", "pattern"]),
    ):
        reset = run(runner, kit, out / fault, 4, fault)
        assert [t["pattern"] for t in reset["transitions"]] == [0] * len(phases)
        assert [t["phase"] for t in reset["transitions"]] == phases
        for n, t in enumerate(reset["transitions"]):
            assert ppm(out / fault / f"frame-{n:02d}.ppm") == phase_reference(
                glyphs, streams, t
            )
        report["runs"][fault] = reset
    for index, name in enumerate(NAMES):
        print(f"Qualifying fixed {name}", flush=True)
        fixed = out / ("fixed-" + name)
        build(fixed, name)
        result = run(runner, fixed, fixed / "run", 21)
        assert result["display_starts"] == 2 and [
            (t["pattern"], t["phase"]) for t in result["transitions"]
        ] == [(index, "title"), (index, "pattern")]
        assert ppm(fixed / "run" / "frame-00.ppm") == title_reference(glyphs, index)
        for frame in (1, 110, 120):
            assert ppm(fixed / "run" / f"frame-{frame:02d}.ppm") == expected(
                glyphs, streams, index
            ), (name, frame)
        report["runs"][name] = result
    # Reintroduce the photographed failure on the corrected controller model.
    for name in ("grid", "circle", "white", "window"):
        fixed = out / ("fixed-" + name)
        folder = out / ("blanking-" + name)
        asm = (fixed / "boot.asm").read_text().replace("057h,06bh", "057h,0bbh")
        assemble(folder, asm)
        (folder / "glyphs.bin").write_bytes(glyphs)
        data = run(runner, folder, folder / "run", 3)
        actual = ppm(folder / "run" / "frame-01.ppm")
        clean = images[NAMES.index(name)]
        masked = bytearray(clean)
        for y in range(288):
            if y % 12 in (0, 11):
                masked[y * 1920 : (y + 1) * 1920] = bytes(1920)
        assert actual == masked and actual != clean, name
        report["rejected_mutations"]["boundary-blanking-" + name] = data
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
