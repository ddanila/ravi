import unittest
from unittest.mock import patch

from ravi.backends.juku import protocol as juku
from ravi.integrity import crc8_atm, crc16_ccitt, crc32
from ravi.monitor import LoaderResponseTimeout, MonitorTransactions
from ravi.protocols import dos_v1 as dos
from ravi.protocols import monitor_v2 as monitor


class ProtocolTests(unittest.TestCase):
    def test_independent_standard_integrity_vectors(self):
        self.assertEqual(crc8_atm(b"123456789"), 0xF4)
        self.assertEqual(crc16_ccitt(b"123456789"), 0x29B1)
        self.assertEqual(crc32(b"123456789"), 0xCBF43926)
        self.assertEqual(crc32(b"56789", crc32(b"1234")), 0xCBF43926)

    def test_frozen_dos_c_fixture_and_every_stream_split(self):
        wire = bytes.fromhex("030101010612345678030101020602410242054344edc300")
        frame = dos.Frame(
            dos.FrameType.REQUEST, 0x78563412, sequence=3, payload=b"A\0B\0CD"
        )
        self.assertEqual(frame.encode(), wire)
        for split in range(len(wire) + 1):
            decoder = dos.FrameDecoder()
            self.assertEqual(
                decoder.feed(wire[:split]) + decoder.feed(wire[split:]), [frame]
            )
        decoder = dos.FrameDecoder()
        self.assertEqual(decoder.feed(b"x" * 10000 + b"\0" + wire), [frame])
        self.assertLessEqual(len(decoder.buffer), decoder.max_encoded)

    def test_frozen_juku_load_fixture_and_every_stream_split(self):
        wire = bytes.fromhex("a55a25074240007600b756a3")
        self.assertEqual(juku.encode_loader_v2_load(0x42, 0x4000, b"\x76\x00"), wire)
        for split in range(len(wire) + 1):
            decoder = monitor.StreamDecoder()
            frames = decoder.feed(wire[:split]) + decoder.feed(wire[split:])
            self.assertEqual(len(frames), 1)
            self.assertEqual(
                monitor.validate_loader_v2_command(frames[0]),
                (0x42, b"\x40\x00\x76\x00"),
            )
        bad = wire[:-1] + bytes((wire[-1] ^ 1,))
        decoder = monitor.StreamDecoder()
        self.assertEqual(len(decoder.feed(b"noise" * 1000 + bad + wire + wire)), 2)
        self.assertLessEqual(len(decoder._buffer), 260)

    def test_inner_crc_detects_stored_command_corruption_even_if_outer_is_repaired(
        self,
    ):
        command = juku.encode_loader_v2_load(1, 0x4000, b"\x76")
        frame = monitor.StreamDecoder().feed(command)[0]
        payload = bytearray(frame.payload)
        payload[3] ^= 1
        repaired = monitor.encode_frame(frame.record_type, bytes(payload))
        decoded = monitor.StreamDecoder().feed(repaired)[0]
        with self.assertRaises(ValueError):
            monitor.validate_loader_v2_command(decoded)

    def test_stale_response_flood_cannot_extend_transaction_deadline(self):
        class Clock:
            now = 0.0

            def __call__(self):
                return self.now

        clock = Clock()

        class Exchange(MonitorTransactions):
            loader_retries = 2
            sends = 0

            def _send_loader_frame(self, *args):
                self.sends += 1

            def _wait_loader_frame(self, expected, cursor, timeout, description):
                clock.now += 0.5
                return monitor.Frame(monitor.TYPE_LOADER_V2_DATA, b"\xfe"), cursor + 1

        exchange = Exchange()
        with (
            patch("ravi.monitor.time.monotonic", clock),
            self.assertRaises(LoaderResponseTimeout),
        ):
            exchange._loader_v2_transact(
                b"request", 7, monitor.TYPE_LOADER_V2_DATA, 0, 1, "test"
            )
        self.assertEqual(exchange.sends, 2)
        self.assertEqual(clock.now, 2)


if __name__ == "__main__":
    unittest.main()
