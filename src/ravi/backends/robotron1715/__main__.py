"""python -m ravi.backends.robotron1715 --help"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from contextlib import ExitStack
from importlib.resources import files
from pathlib import Path

from ravi.transport import LoggedTransport, SerialTransport

from .boot import BootError, StockBoot, load_record, positive, run_record

READY = b"R1715 RAM OK\r\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Experimental plain PC1715 stock-ROM serial bootstrap"
    )
    parser.add_argument("--port", required=True, help="RS-232 serial device")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--stop-bits", type=int, choices=(1, 2), default=2)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--byte-delay", type=float, default=0.002)
    parser.add_argument(
        "--log-dir",
        type=Path,
        required=True,
        help="new directory for raw TX/RX and result",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("probe", help="ROM handshake only; reset afterwards")
    sub.add_parser(
        "smoke", help="upload RAM test and verify all 256 byte values by echo"
    )
    upload = sub.add_parser("upload", help="send a raw binary, optionally jump into it")
    upload.add_argument("image", type=Path)
    upload.add_argument("--address", type=lambda s: int(s, 0), default=0x4000)
    upload.add_argument("--entry", type=lambda s: int(s, 0))
    args = parser.parse_args(argv)
    # Validate everything before opening a serial port or sending a handshake.
    try:
        positive(args.timeout, "timeout")
        StockBoot(None, byte_delay=args.byte_delay)  # type: ignore[arg-type]
        image = None
        address, entry = 0x4000, None
        if args.command == "smoke":
            image = files(__package__).joinpath("smoke.bin").read_bytes()
            entry = address
        elif args.command == "upload":
            image = args.image.read_bytes()
            address, entry = args.address, args.entry
        if image is not None:
            load_record(address, image)
            if entry is not None:
                run_record(entry)
                if not address <= entry < address + len(image):
                    raise ValueError("entry must lie inside the uploaded payload")
        args.log_dir.mkdir(parents=True, exist_ok=False)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    result = {
        "target": "plain-pc1715-stock-rom",
        "command": args.command,
        "port": args.port,
        "baud": args.baud,
        "host_format": f"8O{args.stop_bits}",
        "byte_delay": args.byte_delay,
        "started_unix": time.time(),
        "success": False,
        "hardware_qualification": "experimental; inspect this session's evidence",
    }
    try:
        with ExitStack() as stack:
            tx = stack.enter_context((args.log_dir / "tx.bin").open("wb"))
            rx = stack.enter_context((args.log_dir / "rx.bin").open("wb"))
            serial = stack.enter_context(
                SerialTransport(
                    args.port, args.baud, parity="O", stop_bits=args.stop_bits
                )
            )
            transport = LoggedTransport(serial, rx, tx)
            boot = StockBoot(transport, byte_delay=args.byte_delay)
            print("Waiting for stock ROM; press RESET on the board.", flush=True)
            boot.handshake(args.timeout)
            print("ROM handshake received: 12 12.", flush=True)
            if image is not None:
                boot.upload(address, image)
                result.update(
                    address=address,
                    size=len(image),
                    entry=entry,
                    image_sha256=hashlib.sha256(image).hexdigest(),
                )
                print(f"Sent {len(image)} bytes; stock ROM provides no readback/ACK.")
                if entry is not None:
                    boot.execute(entry)
                    print(f"Jump command sent for {entry:04X}h.")
            if args.command == "smoke":
                boot.expect(READY)
                for value in range(256):
                    transport.write(bytes((value,)))
                    boot.expect(bytes((value,)))
                print(
                    "PASS: payload ran, 8000h..80FFh RAM test and 256-byte echo passed."
                )
                result["evidence"] = "RAM OK banner and exact 00..FF echo"
            else:
                result["evidence"] = (
                    "ROM handshake only"
                    if image is None
                    else "ROM handshake; payload/entry sent without execution verification"
                )
            result["success"] = True
        return 0
    except (OSError, ValueError, BootError) as exc:
        result["error"] = str(exc)
        print(
            f"FAIL: {exc}. Reset before retrying; no automatic replay.", file=sys.stderr
        )
        return 1
    except KeyboardInterrupt:
        result["error"] = "interrupted; reset before retrying"
        return 130
    finally:
        result["finished_unix"] = time.time()
        (args.log_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
