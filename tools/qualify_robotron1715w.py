#!/usr/bin/env python3
"""Run actual W1 firmware through a pinned dac-emulation checkout, never serial."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emulator", type=Path, required=True)
    parser.add_argument(
        "--cas",
        type=Path,
        help="reference CAS binary; default is a synthetic equivalent for model tests",
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="new evidence directory"
    )
    args = parser.parse_args()
    args.emulator = args.emulator.resolve()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    pin = json.loads((ROOT / "tools/robotron1715w-emulator.json").read_text())
    head = subprocess.check_output(
        ["git", "-C", str(args.emulator), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != pin["commit"]:
        raise SystemExit(f"emulator must be pinned at {pin['commit']}, found {head}")
    subprocess.run(
        ["make", "-C", str(args.emulator), "build/robotron-rom-monitor"], check=True
    )
    cas = args.cas.resolve() if args.cas else args.output / "synthetic-cas.bin"
    if args.cas is None:
        # Original test data, not a historical PROM dump. Only the upper half
        # is consulted by this model; boot selector 0 has explicit decoding.
        data = bytearray([15] * 256)
        banks = [[1] * 16, [2] * 12 + [1] * 4, [4] * 12 + [1] * 4, [8] * 12 + [1] * 4]
        for bank, values in enumerate(banks, 1):
            for page, value in enumerate(values):
                data[128 + bank * 16 + page] = value ^ 15
        cas.write_bytes(data)
    if len(cas.read_bytes()) != 256:
        raise SystemExit("CAS must be 256 bytes")
    env = dict(
        os.environ,
        PYTHONPATH=str(ROOT / "src"),
        RAVI_W_FIXTURE=str(args.emulator / "build/robotron-rom-monitor"),
        RAVI_W_CAS=str(cas),
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            str(ROOT / "tests"),
            "-p",
            "test_robotron1715w.py",
            "-v",
        ],
        env=env,
        text=True,
        capture_output=True,
    )
    (args.output / "tests.txt").write_text(proc.stdout + proc.stderr)
    sources = [
        "machines/robotron1715m/robotron.c",
        "machines/robotron1715m/sio.c",
        "tests/integration/robotron_rom_monitor.c",
        "common/cpu/z80.c",
        "third_party/cpu/chips/z80.h",
    ]
    report = {
        "passed": proc.returncode == 0,
        "emulator_commit": head,
        "emulator_sources": {
            f: hashlib.sha256((args.emulator / f).read_bytes()).hexdigest()
            for f in sources
        },
        "rom_sha256": hashlib.sha256(
            (ROOT / "src/ravi/backends/robotron1715w/rom.bin").read_bytes()
        ).hexdigest(),
        "cas_sha256": hashlib.sha256(cas.read_bytes()).hexdigest(),
        "cas_kind": "caller-supplied reference"
        if args.cas
        else "synthetic reference-layout test data",
        "physical_qualification": False,
        "limits": [
            "No PC001 ROM/PROM or wiring identity inferred.",
            "No analog DRAM retention/refresh or CPU bus-stall proof.",
            "CTC1/CTC2 both programmed; physical serial clock route unverified.",
            "Uncooperative snippet needs external reset.",
        ],
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
