"""Protocol tests plus opt-in real-ROM qualification against dac-emulation."""

import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import nullcontext, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ravi.backends.robotron1715w import protocol as p
from ravi.backends.robotron1715w.__main__ import main as cli
from ravi.backends.robotron1715w.banked import BankAddress, BankedMonitor
from ravi.backends.robotron1715w.build import ROOT, assemble
from ravi.backends.robotron1715w.host import Monitor, MonitorError
from ravi.execution import OutcomeUnknown


class Peer:
    def __init__(self, mode=""):
        self.proc = subprocess.Popen(
            [
                os.environ["RAVI_W_FIXTURE"],
                str(ROOT / "rom.bin"),
                os.environ["RAVI_W_CAS"],
                mode,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.buffer = bytearray.fromhex(self.proc.stdout.readline().strip())
        self.tx = []

    def command(self, line):
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        self.buffer.extend(bytes.fromhex(self.proc.stdout.readline().strip()))

    def write(self, data):
        self.tx.append(data)
        self.command("T " + data.hex())

    def read(self, size, timeout):
        if not self.buffer:
            self.command("S 1000000")
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result

    def close(self):
        self.proc.stdin.write("D\nQ\n")
        self.proc.stdin.flush()
        out, err = self.proc.communicate(timeout=5)
        if self.proc.returncode:
            raise AssertionError(err)
        return err


class WireTests(unittest.TestCase):
    def test_crc_and_resync(self):
        frame = b"\x5a" + p.protected(bytes((0, 42, 0, 0, 8, 1)))
        self.assertEqual(frame.hex(), "5a002a00000801d982")
        for split in range(len(frame) + 1):
            parser = p.Parser()
            got = parser.feed(b"noise" + frame[:split]) + parser.feed(frame[split:])
            self.assertEqual(got, [p.Response(0, 42, 0, 2048, 1)])
        broken = bytearray(frame)
        broken[3] ^= 1
        self.assertEqual(
            p.Parser().feed(bytes(broken) + frame), [p.Response(0, 42, 0, 2048, 1)]
        )

    @unittest.skipUnless(shutil.which("z80asm"), "needs z80asm")
    def test_reproducible_2716(self):
        image, labels = assemble((ROOT / "rom.asm").read_text())
        self.assertEqual(len(image), 2048)
        self.assertLessEqual(labels["image_end"], 2048)
        self.assertEqual(image, (ROOT / "rom.bin").read_bytes())


@unittest.skipUnless(
    os.getenv("RAVI_W_FIXTURE") and os.getenv("RAVI_W_CAS"),
    "set RAVI_W_FIXTURE and RAVI_W_CAS for actual ROM tests",
)
class FirmwareTests(unittest.TestCase):
    def setUp(self):
        self.peer = Peer()
        self.m = Monitor(self.peer)

    def tearDown(self):
        self.peer.close()

    def test_identity_and_no_ram(self):
        self.assertEqual(self.m.identify()["protocol"], "W1")
        for mode in ("no-ram", "no-ram,no-display"):
            peer = Peer(mode)
            m = Monitor(peer)
            self.assertEqual(m.identify()["main_ram_workspace"], 0)
            report = peer.close()
            self.assertIn('"violations":0', report)
            self.assertIn('"ram_reads":0', report)
            self.assertIn('"ram_writes":0', report)
            self.assertIn('"display":1', report)
            if mode == "no-ram":
                self.assertGreater(json.loads(report)["lit_pixels"], 100)

    def test_cli_upload_read_run_and_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snippet = bytes.fromhex("3e2ac30300")
            (root / "snippet.bin").write_bytes(snippet)
            commands = [
                ["probe"],
                ["load", "0x7000", str(root / "snippet.bin")],
                ["read", "0x7000", "5", "--output", str(root / "read.bin")],
                ["run", "0x7000"],
            ]
            for index, command in enumerate(commands):
                logs = root / str(index)
                with (
                    patch(
                        "ravi.backends.robotron1715w.__main__.SerialTransport",
                        return_value=nullcontext(self.peer),
                    ) as serial,
                    redirect_stdout(io.StringIO()),
                ):
                    self.assertEqual(
                        cli(
                            ["--port", "offline-peer", "--log-dir", str(logs)] + command
                        ),
                        0,
                    )
                    serial.assert_called_once_with(
                        "offline-peer", 9600, parity="N", stop_bits=1
                    )
                result = json.loads((logs / "result.json").read_text())
                self.assertTrue(result["success"])
                self.assertTrue(result["events"])
                self.assertTrue((logs / "tx.bin").read_bytes())
                self.assertTrue((logs / "rx.bin").read_bytes())
            self.assertEqual((root / "read.bin").read_bytes(), snippet)
            self.assertEqual(result["execution"]["accumulator"], 42)

    def test_write_read_edges(self):
        for address in (0x4000, 0x71FD, 0xFFC0):
            data = bytes(range(64))
            self.m.write_memory(address, data)
            self.assertEqual(self.m.read_memory(address, len(data)), data)
        self.m.write_memory(0xFFFF, b"\xa5")
        self.assertEqual(self.m.read_memory(0xFFFF, 1), b"\xa5")
        for address, length in ((0x3FFF, 1), (0xFFFF, 2)):
            with self.assertRaises(ValueError):
                self.m.read_memory(address, length)

    def test_corrupt_and_incomplete(self):
        frame = bytearray(p.request("F", 77, 1, 0x8000, 0x55))
        frame[-1] ^= 1
        self.peer.write(bytes(frame))
        self.peer.command("S 5000000")
        self.assertEqual(self.m.identify()["protocol"], "W1")
        self.assertEqual(self.m.read_memory(0x8000, 1), b"\xa7")
        self.peer.write(p.request("W", 78, 1, 0x8000, 3) + b"\x01")
        self.peer.command("S 5000000")
        self.m.identify()
        self.assertEqual(self.m.read_memory(0x8000, 1), b"\x01")
        self.peer.write(p.request("W", 79, 1, 0x8000, 2) + b"\x23\x45\0\0")
        self.peer.command("S 5000000")
        self.m.identify()
        self.assertEqual(self.m.read_memory(0x8000, 2), b"\x23\x45")

    def test_fault_recovery_and_survey(self):
        self.peer.command("F 8003 01 00")
        with self.assertRaises(MonitorError) as cm:
            self.m.fill_page(0x8000, 255)
        self.assertEqual(cm.exception.reply.status, p.VERIFY)
        self.assertEqual(cm.exception.reply.address, 0x8003)
        with self.assertRaises(MonitorError):
            self.m.write_memory(0x8000, b"\xff" * 64)
        self.m.identify()
        self.peer.command("F ffffffff 00 00")
        self.assertTrue(self.m.survey(0x8000, 256)[0]["passed"])

    def test_stackless_return_and_hang(self):
        # C preserves request ID. Return A=42 via ROM recovery vector.
        self.m.write_memory(0x7000, bytes.fromhex("3e2ac30300"))
        self.assertEqual(self.m.execute(0x7000)["accumulator"], 42)
        self.m.identify()
        self.m.write_memory(0x7000, bytes.fromhex("c30070"))
        before = len(self.peer.tx)
        with self.assertRaises(OutcomeUnknown):
            self.m.execute(0x7000, timeout=0.1)
        self.assertEqual(len(self.peer.tx), before + 1)
        with self.assertRaises(OutcomeUnknown):
            self.m.identify()

    def test_lost_execution_replies_are_never_replayed(self):
        self.m.write_memory(0x7000, bytes.fromhex("3e2ac30300"))
        original_write = self.peer.write
        for lost_status in (p.STARTED, p.RETURN):
            monitor = Monitor(self.peer, timeout=0.03)

            def dropping_write(data):
                original_write(data)
                # The fixture has executed the short snippet before returning.
                raw = self.peer.buffer
                self.peer.buffer = bytearray().join(
                    raw[i : i + 9]
                    for i in range(0, len(raw), 9)
                    if raw[i + 1] != lost_status
                )

            before = len(self.peer.tx)
            with patch.object(self.peer, "write", side_effect=dropping_write):
                with self.assertRaises(OutcomeUnknown):
                    monitor.execute(0x7000, timeout=0.03)
            self.assertEqual(len(self.peer.tx), before + 1)
            with self.assertRaises(OutcomeUnknown):
                monitor.identify()

    def test_banked_helper_and_call(self):
        helper = BankedMonitor(self.m, 0xF000)
        helper.install()
        data = bytes(range(64))
        for bank in (1, 2, 3, 4):
            location = BankAddress(bank, 0x200)
            value = bytes(x ^ bank for x in data)
            helper.write_memory(location, value)
            self.assertEqual(helper.read_memory(location, 64), value)
        # Common high RAM aliases all selectors.
        helper.write_memory(BankAddress(2, 0xD000), data)
        self.assertEqual(helper.read_memory(BankAddress(4, 0xD000), 64), data)
        with self.assertRaises(ValueError):
            helper.write_memory(BankAddress(4, 0xF000), data)
        with self.assertRaises(ValueError):
            self.m.write_memory(0xF000, data)
        self.m.write_memory(0x7000, bytes.fromhex("3e37c9"))
        self.assertEqual(helper.call(0x7000)["accumulator"], 55)
        helper.write_memory(BankAddress(3, 0x100), bytes.fromhex("3e29c9"))
        self.assertEqual(helper.call(BankAddress(3, 0x100))["accumulator"], 41)
        self.m.identify()

    def test_low_helper_and_failed_install(self):
        self.peer.command("F 7003 01 00")
        with self.assertRaises(ValueError):
            BankedMonitor(self.m, 0x7000).install()
        self.m.identify()
        self.peer.command("F ffffffff 00 00")
        helper = BankedMonitor(self.m, 0x7000)
        helper.install()
        helper.write_memory(BankAddress(1, 0x100), b"hello")
        self.assertEqual(helper.read_memory(BankAddress(1, 0x100), 5), b"hello")
        with self.assertRaises(ValueError):
            helper.read_memory(BankAddress(2, 0x100), 1)

    def test_alias_uart_and_transmit_recovery(self):
        self.peer.command("A 1")
        self.assertFalse(self.m.survey(0x8000, 256)[0]["passed"])
        self.peer.command("A 0")
        self.m.identify()
        self.peer.command("P 0x218")
        self.peer.write(p.request("I", 88))
        self.peer.command("S 5000000")
        self.peer.command("P 0x208")
        self.peer.command("S 5000000")
        self.m.identify()
        self.peer.command("U 1")
        self.peer.write(p.request("I", 89))
        self.peer.command("S 5000000")
        self.peer.command("U 0")
        self.m.identify()

    def test_changed_helper_stops_before_run(self):
        helper = BankedMonitor(self.m, 0xF000)
        helper.install()
        self.peer.command("F f001 ff ff")
        before = len([x for x in self.peer.tx if x[1] == ord("G")])
        with self.assertRaises(ValueError):
            helper.read_memory(BankAddress(2, 0x100), 1)
        after = len([x for x in self.peer.tx if x[1] == ord("G")])
        self.assertEqual(before, after)
        self.m.identify()
