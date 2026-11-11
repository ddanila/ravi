import unittest

from ravi.backends.robotron1715w import protocol as p
from ravi.backends.robotron1715w.host import Monitor
from ravi.execution import OutcomeUnknown


class Wire:
    def __init__(self, data):
        self.data = bytearray(data)
        self.sent = []

    def write(self, data):
        self.sent.append(data)

    def read(self, size, timeout):
        data = bytes(self.data[:size])
        del self.data[:size]
        return data


class Handoff(unittest.TestCase):
    def test_runtime_bytes_stay_unread(self):
        frame = b"\x5a" + p.protected(bytes([p.STARTED, 1, 1, 0x33, 0xC0, 0]))
        wire = Wire(frame + b"JD\x26\x01")
        m = Monitor(wire)
        m.identity = {"protocol": "W3"}
        m.start(0xC033)
        self.assertEqual(wire.data, b"JD\x26\x01")
        self.assertFalse(m.usable)
        with self.assertRaises(OutcomeUnknown):
            m.start(0xC033)
        self.assertEqual(len(wire.sent), 1)

    def test_lost_ack_never_replayed(self):
        wire = Wire(b"")
        m = Monitor(wire, 0.001)
        m.identity = {"protocol": "W3"}
        with self.assertRaises(OutcomeUnknown):
            m.start(0xC033)
        self.assertEqual(len(wire.sent), 1)

    def test_corrupt_ack_never_hands_off(self):
        wire = Wire(b"\x5a" + b"\x00" * 8)
        m = Monitor(wire, 0.001)
        m.identity = {"protocol": "W3"}
        with self.assertRaises(OutcomeUnknown):
            m.start(0xC033)
        self.assertFalse(m.usable)
