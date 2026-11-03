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
from ravi.backends.robotron1715w.diagnostic import build_diagnostic, run_diagnostic
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
                ["diagnose", "data-lines", "0x8000", "1", "--workspace", "0xf000"],
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
            execution = json.loads((root / "3/result.json").read_text())
            self.assertEqual(execution["execution"]["accumulator"], 42)
            self.assertTrue(result["diagnostic"]["passed"])

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

    def test_dropped_and_duplicated_command_bytes(self):
        frame = p.request("F", 90, 1, 0x8000, 0x55)
        for index in range(len(frame)):
            for damaged in (
                frame[:index] + frame[index + 1 :],
                frame[:index] + frame[index : index + 1] + frame[index:],
            ):
                self.m.write_memory(0x8000, b"\xa7")
                self.peer.write(damaged)
                self.peer.command("S 5000000")
                self.m.identify()
                expected = b"\x55" if damaged[:9] == frame else b"\xa7"
                self.assertEqual(self.m.read_memory(0x8000, 1), expected)
        # A duplicated final CRC byte leaves one valid complete command.
        # The ROM makes no exactly-once claim for duplicated valid frames.

    def test_payload_loss_duplication_and_reset_boundaries(self):
        frame = p.request("W", 91, 1, 0x8000, 8)
        payload = p.protected(bytes(range(8)))
        for index in range(len(payload)):
            for damaged in (
                payload[:index] + payload[index + 1 :],
                payload[:index] + payload[index : index + 1] + payload[index:],
            ):
                self.peer.write(frame + damaged)
                self.peer.command("S 5000000")
                replies = p.Parser().feed(bytes(self.peer.buffer))
                if damaged[: len(payload)] != payload:
                    self.assertFalse(
                        any(r.transaction == 91 and r.status == p.OK for r in replies)
                    )
                self.m.identify()
        for cut in (1, 5, 9, 10, 15):
            self.peer.write((frame + payload)[:cut])
            self.peer.command("Z")
            fresh = Monitor(self.peer)
            fresh.identify()
        # Simulated reset is external to the ROM and does not roll back RAM.

    def test_reset_during_write_invalidates_session(self):
        self.m.identify()
        original = self.peer.write

        def interrupted(data):
            original(data[:10])  # validated W header plus one payload byte
            self.peer.command("Z")

        with patch.object(self.peer, "write", side_effect=interrupted):
            with self.assertRaises(ConnectionError):
                self.m.write_memory(0x8000, b"abc")
        with self.assertRaises(OutcomeUnknown):
            self.m.identify()
        fresh = Monitor(self.peer)
        fresh.identify()
        self.assertEqual(fresh.read_memory(0x8000, 3), b"a\xa7\xa7")

    def test_damaged_reply_no_mutation_replay(self):
        self.m.identify()
        original = self.peer.write
        for mutate in (lambda b: b[:4] + b[5:], lambda b: b[:4] + b[3:]):
            monitor = Monitor(self.peer, timeout=0.03)

            def damaged(data):
                original(data)
                self.peer.buffer = bytearray(mutate(self.peer.buffer))

            before = len(self.peer.tx)
            with patch.object(self.peer, "write", side_effect=damaged):
                with self.assertRaises(TimeoutError):
                    monitor.fill_page(0x8000, 0x55)
            self.assertEqual(len(self.peer.tx), before + 1)
            self.assertEqual(self.m.read_memory(0x8000, 1), b"\x55")

    def test_stack_fault_is_uncertain_and_never_replayed(self):
        helper = BankedMonitor(self.m, 0xF000)
        helper.install()
        self.m.write_memory(0x7000, bytes.fromhex("3e2ac9"))
        # Corrupt the return address when RET reads the tested helper stack.
        self.peer.command(f"F {helper.labels['stack_end'] - 1:x} ff 00")
        before = len([x for x in self.peer.tx if x[1] == ord("G")])
        with self.assertRaises(OutcomeUnknown):
            helper.call(0x7000, timeout=0.05)
        self.assertEqual(len([x for x in self.peer.tx if x[1] == ord("G")]), before + 1)
        with self.assertRaises(OutcomeUnknown):
            self.m.identify()

    def test_bounded_diagnostic_snippets(self):
        for kind, length in (
            ("data-lines", 1),
            ("ram-patterns", 256),
            ("address-lines", 512),
        ):
            with self.subTest(kind=kind):
                report = run_diagnostic(self.m, kind, 0xF000, 0x8000, length)
                self.assertTrue(report["passed"])
                self.assertEqual(report["manifest"]["stack_bytes"], 0)
        # Snippet banks both reads and writes, without relying on helper CALL.
        self.assertTrue(
            run_diagnostic(self.m, "address-lines", 0xF000, 0x100, 512, 3)["passed"]
        )
        self.peer.command("F 8000 01 00")
        result = run_diagnostic(self.m, "data-lines", 0xF000, 0x8000, 1)
        self.assertFalse(result["passed"])
        self.assertEqual(
            result["failure"],
            {"bank": 1, "address": 0x8000, "expected": 1, "actual": 0},
        )
        self.peer.command("F 8003 01 00")
        result = run_diagnostic(self.m, "ram-patterns", 0xF000, 0x8000, 256)
        self.assertEqual(
            result["failure"],
            {"bank": 1, "address": 0x8003, "expected": 255, "actual": 254},
        )
        self.peer.command("F ffffffff 00 00")
        # Inject after workspace preparation so the diagnostic catches the alias.
        original_execute = self.m.execute

        def aliased(*args, **kwargs):
            self.peer.command("A 256")
            try:
                return original_execute(*args, **kwargs)
            finally:
                self.peer.command("A 0")

        with patch.object(self.m, "execute", side_effect=aliased):
            self.assertFalse(
                run_diagnostic(self.m, "address-lines", 0xF000, 0x8000, 512)["passed"]
            )
        self.m.identify()

    def test_corrupt_diagnostic_result_stops_session(self):
        original = self.m.execute
        _, _, manifest = build_diagnostic("data-lines", 0xF000, 0x8000, 1)

        def corrupt_result(*args, **kwargs):
            result = original(*args, **kwargs)
            self.peer.command(f"F {manifest['labels']['result_done']:x} ff 00")
            return result

        with patch.object(self.m, "execute", side_effect=corrupt_result):
            with self.assertRaises(OutcomeUnknown):
                run_diagnostic(self.m, "data-lines", 0xF000, 0x8000, 1)
        with self.assertRaises(OutcomeUnknown):
            self.m.identify()

    def test_diagnostic_workspace_and_artifacts(self):
        for args in (
            ("ram-patterns", 0x8000, 0x8000, 256, 1),
            ("data-lines", 0x7000, 0x8000, 2, 1),
            ("address-lines", 0x7000, 0x100, 256, 3),
        ):
            with self.assertRaises(ValueError):
                build_diagnostic(*args)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "diagnostic"
            result = run_diagnostic(
                self.m, "ram-patterns", 0xF000, 0x8000, 256, artifacts=out
            )
            self.assertEqual(json.loads((out / "result.json").read_text()), result)
            self.assertTrue((out / "snippet.asm").read_text())
            self.assertTrue((out / "snippet.bin").read_bytes())
        self.peer.command("F f003 ff ff")
        before = len([x for x in self.peer.tx if x[1] == ord("G")])
        with self.assertRaises(ValueError):
            run_diagnostic(self.m, "data-lines", 0xF000, 0x8000, 1)
        self.assertEqual(len([x for x in self.peer.tx if x[1] == ord("G")]), before)

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
