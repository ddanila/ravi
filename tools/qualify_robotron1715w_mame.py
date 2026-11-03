#!/usr/bin/env python3
"""Offline W1 qualification through MAME's real null-modem serial device."""

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

from ravi.backends.robotron1715w.banked import BankAddress, BankedMonitor
from ravi.backends.robotron1715w.build import ROOT
from ravi.backends.robotron1715w.diagnostic import run_diagnostic
from ravi.backends.robotron1715w.host import Monitor
from ravi.transport import LoggedTransport, SocketTransport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mame", default="mame")
    parser.add_argument(
        "--media", type=Path, required=True, help="cas.bin and s600.bin"
    )
    parser.add_argument("--output", type=Path, required=True, help="new directory")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    media = out / "roms/rt1715w"
    media.mkdir(parents=True)
    hashes = {}
    for source, name in (
        (ROOT / "rom.bin", "s550.bin"),
        (args.media / "cas.bin", "287.bin"),
        (args.media / "s600.bin", "s600.ic8"),
    ):
        shutil.copyfile(source, media / name)
        hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    # Lua only observes CPU PC and screen output. All commands,
    # helper uploads and execution go through the null-modem serial wire.
    lua = r"""
local m=manager.machine
local frames=0
emu.register_frame_done(function()
 frames=frames+1
 if frames==10 then
  local f=io.open(OUT..'/startup.json','w')
  f:write(string.format('{"pc":%d}',m.devices[':maincpu'].state['PC'].value))
  f:close()
  m.screens[':screen']:snapshot(OUT..'/startup.png')
 end
 local f=io.open(OUT..'/stop','r')
 if f then f:close();m.screens[':screen']:snapshot(OUT..'/final.png');m:exit() end
end)
"""
    script = out / "observe.lua"
    script.write_text("local OUT=" + json.dumps(str(out)) + "\n" + lua)
    report = {
        "passed": False,
        "mame": subprocess.check_output([args.mame, "-version"], text=True).strip(),
        "machine": "rt1715w",
        "firmware_sha256": hashes,
        "checks": [],
        "physical_qualification": False,
        "limits": [
            "Reference CAS, not PC001 PROM.",
            "No hardware or analog timing qualification.",
            "Custom ROM checksum warning is expected.",
            "MAME devices are unmodified; Lua observes only.",
        ],
    }
    proc = None
    try:
        with (
            socket.socket() as listener,
            (out / "mame.log").open("w") as log,
            (out / "tx.bin").open("wb") as tx,
            (out / "rx.bin").open("wb") as rx,
        ):
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(60)
            command = [
                args.mame,
                "rt1715w",
                "-noreadconfig",
                "-rompath",
                str(out / "roms"),
                "-video",
                "none",
                "-sound",
                "none",
                "-window",
                "-skip_gameinfo",
                "-autoboot_delay",
                "0",
                "-autoboot_script",
                str(script),
                "-seconds_to_run",
                "180",
                "-bitbanger",
                f"socket.127.0.0.1:{listener.getsockname()[1]}",
            ]
            report["command"] = command
            proc = subprocess.Popen(
                command,
                cwd=out,
                env={**os.environ, "SDL_VIDEODRIVER": "dummy"},
                stdout=log,
                stderr=log,
            )
            connection, _ = listener.accept()
            with connection:
                connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                transport = object.__new__(SocketTransport)
                transport.socket = connection
                time.sleep(0.5)  # let the observer capture startup before RAM tests
                m = Monitor(LoggedTransport(transport, rx, tx), timeout=5)
                report["identity"] = m.identify()
                report["checks"].append(
                    "9600 8N1 identification through CTC2/SIO/null-modem"
                )
                for address in (0x4000, 0x71FD, 0xFFC0):
                    data = bytes(range(64))
                    m.write_memory(address, data)
                    assert m.read_memory(address, 64) == data
                m.fill_page(0x8000, 0xAA)
                assert m.read_memory(0x8000, 64) == b"\xaa" * 64
                m.write_memory(0x7000, bytes.fromhex("3e2ac30300"))
                assert m.execute(0x7000)["accumulator"] == 42
                report["checks"].append(
                    "verified direct transfers, page fill and stackless return"
                )
                h = BankedMonitor(m, 0xF000)
                report["helper"] = h.install()
                for bank in (1, 2, 3, 4):
                    data = bytes((bank, 0x55, 0xAA, 0xFF))
                    h.write_memory(BankAddress(bank, 0x200), data)
                for bank in (1, 2, 3, 4):
                    assert h.read_memory(BankAddress(bank, 0x200), 4) == bytes(
                        (bank, 0x55, 0xAA, 0xFF)
                    )
                h.write_memory(BankAddress(3, 0x100), bytes.fromhex("3e29c9"))
                assert h.call(BankAddress(3, 0x100))["accumulator"] == 41
                h.write_memory(BankAddress(2, 0xD000), b"common")
                assert h.read_memory(BankAddress(4, 0xD000), 6) == b"common"
                report["checks"].append(
                    "independent banks 1–4, common alias and bank-3 helper CALL/RET"
                )
                report["diagnostics"] = []
                for kind, length in (
                    ("data-lines", 1),
                    ("ram-patterns", 256),
                    ("address-lines", 512),
                ):
                    result = run_diagnostic(m, kind, 0xE000, 0x8000, length)
                    assert result["passed"]
                    report["diagnostics"].append(result)
                report["checks"].append(
                    "three bounded diagnostic snippets with verified results"
                )
                report["events"] = m.events
                report["startup"] = json.loads((out / "startup.json").read_text())
                assert (out / "startup.png").stat().st_size > 100
                report["checks"].append("independent 8275 screen capture")
                report["passed"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        (out / "stop").touch()
        if proc:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            report["mame_exit_code"] = proc.returncode
            if proc.returncode != 0:
                report["passed"] = False
                report.setdefault("error", "MAME did not exit cleanly")
        # Historical ROMs are caller-supplied, not release artifacts.
        shutil.rmtree(out / "roms")
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps({k: v for k, v in report.items() if k not in ("events", "helper")})
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
