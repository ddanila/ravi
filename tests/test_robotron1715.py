from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

from ravi.backends.robotron1715.__main__ import READY, main
from ravi.backends.robotron1715.boot import (
    BootError,
    StockBoot,
    load_record,
    run_record,
)
from ravi.transport import (
    LoopbackTransport,
    Transport,
    TransportError,
    read_fd,
    write_fd,
)


class BootTests(unittest.TestCase):
    def test_frozen_records_and_boundaries(self):
        self.assertEqual(
            load_record(0x4567, b"\x00\x11\xaa"), b"\x0a\x67\x45\x03\x00\x00\x11\xaa"
        )
        self.assertEqual(run_record(0x4567), b"\xaa\x67\x45")
        self.assertEqual(len(load_record(0x4000, bytes(0x8000))), 0x8005)
        for addr, data in [
            (0x800, b"x"),
            (0x3FFF, b"x"),
            (0xBFFF, b"xx"),
            (0x4000, b""),
            (-1, b"x"),
            (0xFFFF, b"xx"),
        ]:
            with self.subTest(addr=addr, data=data), self.assertRaises(ValueError):
                load_record(addr, data)

    def test_handshake_fragmentation_noise_and_single_execution(self):
        sent = []

        def peer(data):
            sent.append(data)
            return b"noise\x12\x12" if data == b"\x11\x11" else b""

        boot = StockBoot(LoopbackTransport(peer), byte_delay=0)
        boot.handshake(0.1)
        boot.upload(0x4000, b"abc")
        with self.assertRaises(ValueError):
            boot.execute(0x4003)
        boot.execute(0x4000)
        self.assertEqual(b"".join(sent), b"\x11\x11\x0a\x00\x40\x03\x00abc\xaa\x00\x40")
        with self.assertRaises(BootError):
            boot.execute(0x4000)

    def test_timeout_and_partial_write_never_replay(self):
        boot = StockBoot(LoopbackTransport(lambda _: b""), byte_delay=0)
        with self.assertRaises(BootError):
            boot.handshake(0.01, 0.003)
        with self.assertRaises(BootError):
            boot.handshake()
        wire = LoopbackTransport(lambda _: b"\x12\x12")
        boot = StockBoot(wire, byte_delay=0)
        boot.handshake()
        with patch.object(
            wire, "write", side_effect=[None, TransportError("disconnect")]
        ) as write:
            with self.assertRaises(TransportError):
                boot.upload(0x4000, b"abc")
            self.assertEqual(write.call_count, 2)
        with self.assertRaises(BootError):
            boot.upload(0x4000, b"abc")
        with self.assertRaises(BootError):
            boot.execute(0x4000)

    def test_failed_exec_never_replays(self):
        wire = LoopbackTransport(lambda _: b"\x12\x12")
        boot = StockBoot(wire, byte_delay=0)
        boot.handshake()
        boot.upload(0x4000, b"abc")
        with patch.object(wire, "write", side_effect=TransportError("disconnect")):
            with self.assertRaises(TransportError):
                boot.execute(0x4000)
        with self.assertRaises(BootError):
            boot.execute(0x4000)

    def test_expect_corruption_and_lost_response(self):
        for reply in (b"wrong", b"R1715"):
            wire = LoopbackTransport(lambda _: reply)
            wire.write(b"?")
            with self.assertRaises(BootError):
                StockBoot(wire).expect(READY, 0.01)

    def test_bad_timing_rejected(self):
        for value in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                StockBoot(None, byte_delay=value)
        for value in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                StockBoot(None).handshake(value)

    def test_cli_validates_payload_before_opening_port(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("ravi.backends.robotron1715.__main__.SerialTransport") as serial,
        ):
            image = Path(tmp) / "empty.bin"
            image.write_bytes(b"")
            with self.assertRaises(SystemExit):
                main(
                    [
                        "--port",
                        "unused",
                        "--log-dir",
                        tmp + "/logs",
                        "upload",
                        str(image),
                    ]
                )
            serial.assert_not_called()

    @unittest.skipUnless(
        shutil.which("z80asm"), "optional z80asm reproducibility check"
    )
    def test_smoke_binary_matches_source(self):
        resource = files("ravi.backends.robotron1715")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "smoke.bin"
            subprocess.run(
                ["z80asm", "-o", str(output), str(resource.joinpath("smoke.asm"))],
                check=True,
            )
            self.assertEqual(
                output.read_bytes(), resource.joinpath("smoke.bin").read_bytes()
            )


class ProcessTransport(Transport):
    def __init__(self, process):
        self.process = process
        os.set_blocking(process.stdout.fileno(), False)
        os.set_blocking(process.stdin.fileno(), False)

    def read(self, size, timeout):
        return read_fd(self.process.stdout.fileno(), size, timeout)

    def write(self, data):
        write_fd(self.process.stdin.fileno(), data, time.monotonic() + 5)

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process.stdout.close()


@unittest.skipUnless(
    os.environ.get("RAVI_PC1715_ROM") and os.environ.get("RAVI_CHIPS_DIR"),
    "external ROM and Z80 header required",
)
class HistoricalRomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = Path(os.environ["RAVI_PC1715_ROM"])
        if (
            hashlib.sha256(cls.rom.read_bytes()).hexdigest()
            != "51cb80639b5667f2611da71ce7305061566cf3474bda7db6fc82709d08e46d01"
        ):
            raise ValueError("unsupported historical ROM hash")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.binary = Path(cls.tmp.name) / "rom-test"
        subprocess.run(
            [
                "cc",
                "-std=c99",
                "-O2",
                "-I",
                os.environ["RAVI_CHIPS_DIR"],
                str(Path(__file__).parent / "fixtures/robotron1715_rom.c"),
                "-o",
                str(cls.binary),
            ],
            check=True,
        )

    def connect(self, fault=False):
        process = subprocess.Popen(
            [str(self.binary), str(self.rom), *(["fault"] if fault else [])],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        transport = ProcessTransport(process)
        self.addCleanup(transport.close)
        boot = StockBoot(transport, byte_delay=0)
        boot.handshake(5)
        return boot, transport

    def test_actual_rom_upload_exec_ram_test_and_all_byte_echo(self):
        boot, transport = self.connect()
        image = files("ravi.backends.robotron1715").joinpath("smoke.bin").read_bytes()
        boot.upload(0x4000, image)
        boot.execute(0x4000)
        boot.expect(READY)
        for byte in range(256):
            transport.write(bytes([byte]))
            boot.expect(bytes([byte]))

    def test_actual_instructions_detect_ram_fault(self):
        boot, _ = self.connect(fault=True)
        boot.upload(
            0x4000,
            files("ravi.backends.robotron1715").joinpath("smoke.bin").read_bytes(),
        )
        boot.execute(0x4000)
        boot.expect(b"R1715 RAM FAIL!")

    def test_cli_smoke_records_real_rom_exchange(self):
        process = subprocess.Popen(
            [str(self.binary), str(self.rom)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        transport = ProcessTransport(process)
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch(
                "ravi.backends.robotron1715.__main__.SerialTransport",
                return_value=transport,
            ),
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            logs = Path(tmp) / "logs"
            code = main(
                [
                    "--port",
                    "emulated",
                    "--byte-delay",
                    "0",
                    "--log-dir",
                    str(logs),
                    "smoke",
                ]
            )
            self.assertEqual(code, 0)
            self.assertTrue(json.loads((logs / "result.json").read_text())["success"])
            self.assertEqual(
                (logs / "rx.bin").read_bytes(), b"\x12\x12" + READY + bytes(range(256))
            )
            self.assertTrue((logs / "tx.bin").read_bytes().endswith(bytes(range(256))))
