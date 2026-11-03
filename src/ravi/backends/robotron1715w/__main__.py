"""Mac/Linux CLI for the custom W1/W2 ROM; never invokes the plain-1715 loader."""

import argparse
import glob
import hashlib
import json
import math
import time
from contextlib import ExitStack
from pathlib import Path

from ravi.transport import LoggedTransport, SerialTransport

from .banked import BankAddress, BankedMonitor
from .diagnostic import KINDS, build_diagnostic, run_diagnostic
from .host import Monitor


def number(value):
    return int(value, 0)


def campaign(m, helper, start, length, banks):
    report = {"direct_survey": m.survey(start, length), "bank_tests": []}
    if helper is None:
        report["passed"] = all(p["passed"] for p in report["direct_survey"])
        return report
    for bank in banks:
        location = BankAddress(bank, start)
        helper._check(location, length, True)
        patterns = [
            ("00", bytes(length)),
            ("FF", b"\xff" * length),
            ("55", b"\x55" * length),
            ("AA", b"\xaa" * length),
            ("address-low", bytes((start + i) & 255 for i in range(length))),
            ("address-high", bytes(((start + i) >> 8) & 255 for i in range(length))),
        ]
        for name, data in patterns:
            try:
                helper.write_memory(location, data)
                report["bank_tests"].append(
                    {"bank": bank, "pattern": name, "passed": True}
                )
            except ValueError as exc:
                report["bank_tests"].append(
                    {"bank": bank, "pattern": name, "passed": False, "error": str(exc)}
                )
                if not helper.active:
                    raise
    report["passed"] = all(p["passed"] for p in report["direct_survey"]) and all(
        p["passed"] for p in report["bank_tests"]
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port", help="explicit RS-232 device; never chosen automatically"
    )
    parser.add_argument("--log-dir", type=Path, help="new directory for evidence")
    parser.add_argument("--timeout", type=float, default=3)
    parser.add_argument(
        "--helper",
        type=number,
        help="survey and install helper here; overwrites its containing pages",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ports", help="list candidates without opening them")
    sub.add_parser("probe", help="identify the custom ROM only")
    read = sub.add_parser("read")
    read.add_argument("address", type=number)
    read.add_argument("length", type=number)
    read.add_argument("--bank", type=int, default=1)
    read.add_argument("--output", type=Path, required=True)
    load = sub.add_parser("load")
    load.add_argument("address", type=number)
    load.add_argument("image", type=Path)
    load.add_argument("--bank", type=int, default=1)
    fill = sub.add_parser("fill")
    fill.add_argument("address", type=number)
    fill.add_argument("value", type=number)
    survey = sub.add_parser("survey")
    survey.add_argument("address", type=number)
    survey.add_argument("length", type=number)
    run = sub.add_parser("run")
    run.add_argument("address", type=number)
    run.add_argument("--bank", type=int, default=1)
    run.add_argument("--execution-timeout", type=float, default=5)
    sub.add_parser("helper", help="install at --helper and report its verified layout")
    tests = sub.add_parser("campaign")
    tests.add_argument("address", type=number)
    tests.add_argument("length", type=number)
    tests.add_argument("--banks", type=int, nargs="+", default=[1])
    diag = sub.add_parser("diagnose", help="destructive bounded RAM diagnostic snippet")
    diag.add_argument("kind", choices=KINDS)
    diag.add_argument("address", type=number)
    diag.add_argument("length", type=number)
    diag.add_argument("--workspace", type=number, required=True)
    diag.add_argument("--bank", type=int, default=1)
    args = parser.parse_args(argv)
    if args.command == "ports":
        print(
            "\n".join(
                sorted(
                    set(
                        glob.glob("/dev/cu.usb*")
                        + glob.glob("/dev/serial/by-id/*")
                        + glob.glob("/dev/ttyUSB*")
                        + glob.glob("/dev/ttyACM*")
                    )
                )
            )
        )
        return 0
    if not args.port or not args.log_dir:
        parser.error("--port and --log-dir are required")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout must be positive")
    if args.command == "helper" and args.helper is None:
        parser.error("--helper address is required")
    image = args.image.read_bytes() if args.command == "load" else None
    if args.command == "read" and args.output.exists():
        parser.error("output already exists")
    if hasattr(args, "bank"):
        BankAddress(args.bank, args.address).validate(
            len(image)
            if image is not None
            else (1 if args.command == "run" else args.length)
        )
        if args.bank != 1 and args.helper is None and args.command != "diagnose":
            parser.error("banked access needs --helper")
    if args.command == "campaign" and args.helper is None and args.banks != [1]:
        parser.error("banked campaign needs --helper")
    if args.command == "diagnose":
        # Validate placement before opening serial or preparing any helper.
        build_diagnostic(
            args.kind, args.workspace, args.address, args.length, args.bank
        )
    args.log_dir.mkdir(parents=True, exist_ok=False)
    result = {
        "target": "PC1715W/M custom W1/W2 ROM",
        "port": args.port,
        "format": "9600 8N1",
        "command": args.command,
        "started_unix": time.time(),
        "success": False,
        "physical_qualification": "experimental; target ROM and wiring must be confirmed",
    }
    m = None
    try:
        with ExitStack() as stack:
            tx = stack.enter_context((args.log_dir / "tx.bin").open("wb"))
            rx = stack.enter_context((args.log_dir / "rx.bin").open("wb"))
            port = stack.enter_context(
                SerialTransport(args.port, 9600, parity="N", stop_bits=1)
            )
            m = Monitor(LoggedTransport(port, rx, tx), args.timeout)
            result["identity"] = m.identify()
            helper = None
            if args.helper is not None:
                helper = BankedMonitor(m, args.helper)
                result["helper"] = helper.install()
                (args.log_dir / "helper.bin").write_bytes(helper.image)
                result["helper"]["labels"] = helper.labels
            if args.command == "read":
                data = (
                    helper.read_memory(
                        BankAddress(args.bank, args.address), args.length
                    )
                    if helper
                    else m.read_memory(args.address, args.length)
                )
                with args.output.open("xb") as f:
                    f.write(data)
                result["sha256"] = hashlib.sha256(data).hexdigest()
            elif args.command == "load":
                if helper:
                    helper.write_memory(BankAddress(args.bank, args.address), image)
                else:
                    m.write_memory(args.address, image)
                result["sha256"] = hashlib.sha256(image).hexdigest()
                result["bytes"] = len(image)
            elif args.command == "fill":
                m.fill_page(args.address, args.value)
            elif args.command == "survey":
                result["survey"] = m.survey(args.address, args.length)
            elif args.command == "run":
                result["execution"] = (
                    helper.call(
                        BankAddress(args.bank, args.address), args.execution_timeout
                    )
                    if helper
                    else m.execute(args.address, args.execution_timeout)
                )
            elif args.command == "diagnose":
                result["diagnostic"] = run_diagnostic(
                    m,
                    args.kind,
                    args.workspace,
                    args.address,
                    args.length,
                    args.bank,
                    args.log_dir / "diagnostic",
                )
            elif args.command == "campaign":
                result["campaign"] = campaign(
                    m, helper, args.address, args.length, args.banks
                )
            result["success"] = (
                all(x["passed"] for x in result.get("survey", []))
                and result.get("campaign", {}).get("passed", True)
                and result.get("diagnostic", {}).get("passed", True)
            )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        result["finished_unix"] = time.time()
        result["events"] = m.events if m else []
        (args.log_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
