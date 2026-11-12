"""W4 tests execute the ROM through independent timed serial hardware models."""

import json
import os
import random
import unittest
from unittest.mock import patch
from pathlib import Path

from test_robotron1715w import Peer

from ravi.backends.robotron1715w import protocol as p
from ravi.backends.robotron1715w.build import ROOT, build_rom
from ravi.backends.robotron1715w.host import Monitor, MonitorError


class BuildTests(unittest.TestCase):
    def test_w4_image(self):
        image, labels = build_rom("W4")
        self.assertEqual(image, (ROOT / "rom-w4.bin").read_bytes())
        self.assertEqual(len(image), 2048)
        self.assertEqual(p.crc16_ccitt(image), 0)
        self.assertLess(labels["image_end"], 2046)
        self.assertEqual(build_rom("W2")[0], (ROOT / "rom.bin").read_bytes())
        self.assertEqual(build_rom("W3")[0], (ROOT / "rom-w3.bin").read_bytes())


@unittest.skipUnless(
    os.getenv("RAVI_W_FIXTURE") and os.getenv("RAVI_W_CAS"),
    "actual ROM fixture required",
)
class FirmwareTests(unittest.TestCase):
    def peer(self, rate=62400, mode=""):
        peer = Peer(mode, ROOT / "rom-w4.bin", rate)
        self.addCleanup(peer.close)
        return peer

    def connect(self, peer):
        m = Monitor(peer, 0.15)
        for _ in range(20):
            try:
                info = m.identify()
                self.assertEqual(info["firmware_version"], "4.0.0")
                return m
            except (TimeoutError, MonitorError):
                if not m.usable:
                    raise
        self.fail("W4 discovery failed")

    def test_all_speeds_headless_and_reconnect(self):
        for rate in p.BAUDS:
            with self.subTest(rate=rate):
                peer = self.peer(rate, "no-ram,no-display")
                m = self.connect(peer)
                self.assertEqual(m.identity["baud"], rate)
                peer.command("S 12000000")
                again = self.connect(peer)
                self.assertEqual(again.identity["baud"], rate)
                peer.command("D")
                # Fixture reports violations at process close; separate test below.

    def test_no_ram_serial_first(self):
        peer = Peer("no-ram,no-display", ROOT / "rom-w4.bin", 62400)
        try:
            self.connect(peer)
        finally:
            report = json.loads(peer.close())
        self.assertEqual(report["violations"], 0)
        self.assertEqual(report["ram_reads"], 0)
        self.assertEqual(report["ram_writes"], 0)
        self.assertEqual(report["first_tx_display_writes"], 0)

    def test_gate_stale_token_and_timeout(self):
        peer = self.peer()
        peer.buffer.clear()
        peer.write(p.request("F", 1, 1, 0x8000, 0x55))
        replies = p.Parser().feed(peer.buffer)
        self.assertTrue(any(r.status == p.NOT_CONNECTED for r in replies))
        m = self.connect(peer)
        self.assertEqual(m.read_memory(0x8000, 64), bytes([0xA7]) * 64)
        m._ok(m._begin("H", address=0x1234))
        with self.assertRaises(MonitorError):
            m._ok(m._begin("C", address=0x4321))
        self.connect(peer)
        m._ok(m._begin("H", address=0x5678))
        peer.command("S 12000000")
        # Expired token cannot authorize memory operations; a fresh handshake works.
        m = self.connect(peer)
        self.assertEqual(m.read_memory(0x8000, 64), bytes([0xA7]) * 64)

    def test_adapter_clock_skew_and_failed_write(self):
        peer = self.peer(62500)
        m = self.connect(peer)
        self.assertEqual(m.identity["baud"], 62400)
        m.write_memory(0x8000, bytes(range(256)) * 4)
        peer.command("F 8000 ff 00 1")
        with self.assertRaises(MonitorError) as cm:
            m.write_memory(0x8000, bytes([255]) * 64)
        self.assertEqual(cm.exception.reply.status, p.VERIFY)
        self.assertEqual(m.identify()["baud"], 62400)

    def test_bad_rom_is_rejected(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            image = bytearray((ROOT / "rom-w4.bin").read_bytes())
            image[-3] ^= 1
            rom = Path(tmp) / "bad.bin"
            rom.write_bytes(image)
            peer = Peer("no-display", rom, 62400)
            try:
                with self.assertRaises(MonitorError) as cm:
                    Monitor(peer).identify()
                self.assertEqual(cm.exception.reply.status, p.ROM_BAD)
            finally:
                peer.close()

    def test_release_and_speed_selection(self):
        peer = self.peer()
        m = self.connect(peer)
        m.release()
        peer.command("B 41600")
        self.assertEqual(self.connect(peer).identity["baud"], 41600)

    def test_continuous_transfers_and_corruption(self):
        peer = self.peer()
        m = self.connect(peer)
        rng = random.Random(17154)
        for n in range(32):
            data = bytes(range(256)) * 4 if n == 0 else rng.randbytes(1024)
            m.write_memory(0x8000, data)
            self.assertEqual(m.read_memory(0x8000, len(data)), data)
        frame = bytearray(p.request("F", 77, 1, 0x8000, 0x11))
        frame[-1] ^= 1
        peer.write(frame)
        m = self.connect(peer)
        self.assertEqual(m.read_memory(0x8000, len(data)), data)
        # Truncated payload must time out without losing a locked connection.
        peer.write(p.request("W", 78, 1, 0x9000, 64) + b"abc")
        peer.command("S 2000000")
        self.assertEqual(self.connect(peer).identity["baud"], 62400)

    def test_return_from_diagnostic_restarts_discovery(self):
        peer = self.peer()
        m = self.connect(peer)
        m.write_memory(0x8000, bytes.fromhex("c30300"))
        peer.write(p.request("G", 91, 1, 0x8000))
        self.assertEqual(self.connect(peer).identity["baud"], 62400)

    def test_cooperative_result_at_default_speed(self):
        peer = self.peer()
        m = self.connect(peer)
        m.write_memory(0x8000, bytes.fromhex("3e2ac30300"))
        self.assertEqual(m.execute(0x8000)["accumulator"], 42)
        identify = m.identify
        # A lost identity request after RETURN must not replay the diagnostic.
        attempts = []

        def delayed_identity():
            attempts.append(1)
            if len(attempts) == 1:
                raise TimeoutError("discovery window missed")
            return identify()

        with patch.object(m, "identify", side_effect=delayed_identity):
            self.assertEqual(m.read_memory(0x8000, 5), bytes.fromhex("3e2ac30300"))
        self.assertGreaterEqual(len(attempts), 2)
        self.assertEqual(m.identity["baud"], 62400)
        self.assertFalse(m.rediscover)

    def test_lost_confirmation_ack_reconnects_without_replay(self):
        peer = self.peer()
        m = self.connect(peer)
        m._ok(m._begin("H", address=0x1234))
        peer.write(p.request("C", 88, address=0x1234))
        peer.buffer.clear()  # Lose the acknowledgement after the ROM locks.
        m = self.connect(peer)
        self.assertEqual(m.read_memory(0x8000, 64), bytes([0xA7]) * 64)

    def test_uart_noise_and_stalled_transmitter_recover(self):
        peer = self.peer()
        self.connect(peer)
        peer.command("P 0x218")
        peer.write(p.request("I", 88))
        peer.command("S 5000000")
        peer.command("P 0x208")
        self.connect(peer)
        peer.command("U 1")
        peer.write(p.request("I", 89))
        peer.command("S 5000000")
        peer.command("U 0")
        self.connect(peer)

    def test_host_auto_falls_back_to_standard_rate(self):
        from unittest.mock import patch

        from ravi.backends.robotron1715w.discovery import discover

        peer = self.peer(9600)

        def configure(port, path, rate):
            if rate != 9600:
                raise ValueError("adapter has no qualified custom rate")
            return {"requested": rate, "calculated_actual": rate}

        with patch(
            "ravi.backends.robotron1715w.discovery.configure_rate",
            side_effect=configure,
        ):
            m, attempts = discover(peer, peer, "offline", "auto", 3)
        self.assertEqual(m.identity["baud"], 9600)
        self.assertEqual([a["requested"] for a in attempts], [62400, 41600, 9600])
