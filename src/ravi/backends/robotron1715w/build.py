"""Reproducible z80asm firmware build; only explicit output paths are written."""

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def assemble(source: str):
    with tempfile.TemporaryDirectory(prefix="ravi-w1-") as directory:
        base = Path(directory)
        asm = base / "image.asm"
        asm.write_text(source)
        proc = subprocess.run(
            ["z80asm", "-L", "-o", str(base / "image.bin"), str(asm)],
            capture_output=True,
            text=True,
            check=True,
        )
        labels = {
            name: int(value, 16)
            for name, value in re.findall(
                r"^(\w+):\s+equ \$([0-9a-fA-F]+)", proc.stderr, re.M
            )
        }
        return (base / "image.bin").read_bytes(), labels


def build_helper(address):
    if not 0x4000 <= address <= 0xFF00:
        raise ValueError("helper must start in directly accessible RAM")
    image, labels = assemble(f" org {address}\n" + (ROOT / "helper.asm").read_text())
    if address + len(image) > 65536:
        raise ValueError("helper wraps address space")
    return image, labels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    image, labels = assemble((ROOT / "rom.asm").read_text())
    if len(image) != 2048:
        raise ValueError("ROM must fit a 2716 exactly")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(image)
    report = {
        "size": len(image),
        "used": labels["image_end"],
        "sha256": hashlib.sha256(image).hexdigest(),
        "labels": labels,
    }
    args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "labels"}))


if __name__ == "__main__":
    main()
