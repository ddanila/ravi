#!/usr/bin/env python3
"""W4 destructive scratch-RAM transfer qualification after burning the EPROM."""

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

from ravi.backends.robotron1715w.discovery import configure_rate, identify_at_rate
from ravi.transport import LoggedTransport, SerialTransport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=1800)
    args = parser.parse_args()
    if not 0 < args.seconds <= 86400:
        parser.error("--seconds must be positive and at most one day")
    args.output.mkdir(parents=True, exist_ok=False)
    report = {
        "physical_qualification": True,
        "complete": False,
        "scratch_address": 0x8000,
        "scratch_bytes": 4096,
        "requested_soak_seconds": args.seconds,
        "trials": [],
    }
    rng = random.Random(1715400)
    try:
        with (
            SerialTransport(
                args.port, 9600, parity="N", stop_bits=1, exclusive=True
            ) as port,
            (args.output / "rx.bin").open("wb") as rx,
            (args.output / "tx.bin").open("wb") as tx,
        ):
            wire = LoggedTransport(port, rx, tx)
            for rate in (9600, 41600, 62400):
                config = configure_rate(port, args.port, rate)
                monitor = identify_at_rate(wire, 5)
                if (
                    monitor.identity["protocol"] != "W4"
                    or monitor.identity["baud"] != rate
                ):
                    raise ValueError(
                        "Expected W4 at selected baud; no scratch writes performed"
                    )
                trial = {
                    "baud": rate,
                    "configuration": config,
                    "identity": monitor.identity,
                    "rounds": 0,
                    "verified_bytes": 0,
                }
                report["trials"].append(trial)
                begin = time.monotonic()
                while True:
                    data = rng.randbytes(4096)
                    monitor.write_memory(0x8000, data)
                    actual = monitor.read_memory(0x8000, len(data))
                    if actual != data:
                        raise ValueError("Independent readback mismatch")
                    trial["rounds"] += 1
                    trial["verified_bytes"] += len(data)
                    trial["last_sha256"] = hashlib.sha256(actual).hexdigest()
                    trial["seconds"] = time.monotonic() - begin
                    (args.output / "result.json").write_text(
                        json.dumps(report, indent=2)
                    )
                    print(rate, trial["rounds"], trial["seconds"], flush=True)
                    if rate != 62400 or trial["seconds"] >= args.seconds:
                        break
                trial["events"] = monitor.events
                if rate != 62400:
                    monitor.release()
            report["complete"] = True
    except Exception as exc:
        report["error"] = repr(exc)
        raise
    finally:
        (args.output / "result.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
