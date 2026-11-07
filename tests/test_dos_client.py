import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from ravi.backends.dos.client import Client, RemoteError
from ravi.protocols.dos_v1 import (
    Command,
    Frame,
    FrameDecoder,
    FrameType,
    Status,
    file_crc32,
)
from ravi.transport import LoopbackTransport


class DOSUploadTests(unittest.TestCase):
    def test_matching_remote_needs_no_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "reader.com"
            source.write_bytes(b"reader")
            client = Client(LoopbackTransport(lambda data: b""))
            client.crc = Mock(return_value=(6, file_crc32(b"reader")))
            client.request = Mock(side_effect=AssertionError("unexpected upload"))
            stats = client.put(source, "READER.COM")
            self.assertTrue(stats.skipped)
            self.assertEqual(stats.resumed_bytes, 6)
            self.assertEqual(stats.bytes_per_second, 0)
            client.crc.assert_called_once_with("READER.COM")

    def test_identity_failure_is_not_treated_as_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "reader.com"
            source.write_bytes(b"reader")
            client = Client(LoopbackTransport(lambda data: b""))
            client.crc = Mock(side_effect=RemoteError(Command.CRC, Status.IO_ERROR))
            client.request = Mock()
            with self.assertRaises(RemoteError):
                client.put(source, "READER.COM")
            client.request.assert_not_called()

    def test_decoder_counts_bad_frames_and_recovers(self):
        decoder = FrameDecoder(max_encoded=32)
        valid = Frame(FrameType.REQUEST, 7, payload=b"ok").encode()
        frames = decoder.feed(b"bad\0" + b"x" * 40 + b"\0" + valid)
        self.assertEqual(decoder.rejected_frames, 2)
        self.assertEqual([frame.transaction for frame in frames], [7])
