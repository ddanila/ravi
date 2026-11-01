"""Deploy or query the serial-only recoverable diagnostic on a plain PC1715."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from contextlib import ExitStack
from importlib.resources import files
from pathlib import Path

from ravi.transport import LoggedTransport, SerialTransport

from .boot import BootError, StockBoot, positive
from .monitor import IDENTITY, Monitor


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--log-dir", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--byte-delay", type=float, default=0.002)
    sub = parser.add_subparsers(dest="command", required=True)
    deploy = sub.add_parser(
        "deploy", help="fresh ROM handshake, upload, verify, test 00/80"
    )
    deploy.add_argument("--reference-rom", type=Path)
    test = sub.add_parser(
        "test", help="already-running monitor; preserve/test/restore pages"
    )
    test.add_argument("pages", nargs="+", type=lambda s: int(s, 16))
    read = sub.add_parser("read")
    read.add_argument("address", type=lambda s: int(s, 16))
    read.add_argument("length", type=int)
    write = sub.add_parser(
        "write", help="write/readback one page chunk outside monitor/boot"
    )
    write.add_argument("address", type=lambda s: int(s, 16))
    write.add_argument("image", type=Path)
    call = sub.add_parser("call", help="call uploaded code; RET returns to monitor")
    call.add_argument("address", type=lambda s: int(s, 16))
    sub.add_parser("identify")
    args = parser.parse_args(argv)
    try:
        positive(args.timeout, "timeout")
        StockBoot(None, byte_delay=args.byte_delay)
        payload = (
            files("ravi.backends.robotron1715").joinpath("monitor.bin").read_bytes()
        )
        if len(payload) > 0xC00:
            raise ValueError("monitor overlaps scratch buffer")
        reference = None
        if args.command == "deploy" and args.reference_rom:
            reference = args.reference_rom.read_bytes()
            if len(reference) != 2048:
                raise ValueError("reference ROM must be 2048 bytes")
        image = args.image.read_bytes() if args.command == "write" else None
        # Validate command parameters before opening the physical port.
        if args.command == "read":
            Monitor._range(args.address, args.length)
        if args.command == "test" and any(
            not 0 <= p <= 255 or 8 <= p <= 15 or 0x40 <= p <= 0x4F for p in args.pages
        ):
            raise ValueError("protected or invalid test page")
        if args.command in ("write", "call"):
            if not 0x1000 <= args.address <= 0xFFFF or 0x4000 <= args.address < 0x5000:
                raise ValueError("protected or invalid address")
        if image is not None:
            Monitor._range(args.address, len(image))
            if (args.address & 255) + len(image) > 256:
                raise ValueError("write must fit one page")
        args.log_dir.mkdir(parents=True, exist_ok=False)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    result = {
        "command": args.command,
        "port": args.port,
        "format": "9600 8O2",
        "started_unix": time.time(),
        "success": False,
    }
    try:
        with ExitStack() as stack:
            tx = stack.enter_context((args.log_dir / "tx.bin").open("wb"))
            rx = stack.enter_context((args.log_dir / "rx.bin").open("wb"))
            port = stack.enter_context(
                SerialTransport(args.port, 9600, parity="O", stop_bits=2)
            )
            transport = LoggedTransport(port, rx, tx)
            monitor = Monitor(transport, args.byte_delay)
            if args.command == "deploy":
                boot = StockBoot(transport, byte_delay=args.byte_delay)
                print(
                    "Waiting for fresh stock loader; power on when ready.", flush=True
                )
                boot.handshake(args.timeout)
                boot.upload(0x4000, payload)
                boot.execute(0x4000)
                if monitor.response() != [IDENTITY]:
                    raise BootError("monitor startup identity mismatch")
                print(
                    "Monitor executing; verifying uploaded code by readback.",
                    flush=True,
                )
                readback = b"".join(
                    monitor.read_memory(0x4000 + i, min(256, len(payload) - i))
                    for i in range(0, len(payload), 256)
                )
                (args.log_dir / "payload.bin").write_bytes(payload)
                (args.log_dir / "readback.bin").write_bytes(readback)
                if readback != payload:
                    raise BootError("monitor image readback differs; tests not started")
                result["payload_verified_sha256"] = hashlib.sha256(readback).hexdigest()
                low = monitor.read_memory(0, 256)
                (args.log_dir / "low-page-before.bin").write_bytes(low)
                if reference is not None:
                    result["low_page_matches_reference"] = low == reference[:256]
                result["tests"] = []
                for page in (0, 0x80):
                    record = monitor.test_page(page)
                    result["tests"].append(record)
                    print(json.dumps(record), flush=True)
                    if page == 0:
                        restored = monitor.read_memory(0, 256)
                        (args.log_dir / "low-page-after.bin").write_bytes(restored)
                        result["low_page_restored"] = restored == low
                        if restored != low:
                            raise BootError(
                                "low control page did not restore; stopping tests"
                            )
                monitor.identify()
                result["monitor_responsive_after_tests"] = True
                result["all_tested_pages_passed"] = all(
                    t["passed"] for t in result["tests"]
                )
            else:
                monitor.identify()
                if args.command == "test":
                    result["tests"] = [monitor.test_page(p) for p in args.pages]
                elif args.command == "read":
                    data = monitor.read_memory(args.address, args.length)
                    (args.log_dir / "memory.bin").write_bytes(data)
                    result["data_hex"] = data.hex()
                elif args.command == "write":
                    monitor.write_memory(args.address, image)
                    result["write_readback_verified"] = True
                elif args.command == "call":
                    result["reply"] = [
                        x.decode("ascii", "replace") for x in monitor.call(args.address)
                    ]
            result["success"] = True  # Command succeeded; RAM outcome is separate.
            print(json.dumps(result, indent=2), flush=True)
        return 0
    except (OSError, ValueError, BootError) as exc:
        result["error"] = str(exc)
        print(f"FAIL: {exc}; no automatic retry.", flush=True)
        return 1
    finally:
        result["finished_unix"] = time.time()
        (args.log_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
