import unittest
from ravi.backends.robotron1715.monitor import Monitor
from ravi.backends.robotron1715.boot import BootError

class Wire:
    def __init__(self, data): self.data=bytearray(data); self.sent=bytearray()
    def write(self, data): self.sent.extend(data)
    def read(self, size, timeout):
        result=bytes(self.data[:size]); del self.data[:size]; return result

class HandoffTests(unittest.TestCase):
    def test_keeps_first_guest_request(self):
        wire=Wire(b'GO\r\nJD\x26\x01')
        Monitor(wire,0).start(0xc033)
        self.assertEqual(wire.sent,b'G\x33\xc0')
        self.assertEqual(wire.data,b'JD\x26\x01')
    def test_error_does_not_retry(self):
        wire=Wire(b'ERR RANGE\r\nREADY\r\n')
        with self.assertRaises(BootError): Monitor(wire,0).start(0xc033)
        self.assertEqual(wire.sent,b'G\x33\xc0')
    def test_protected_entry(self):
        wire=Wire(b'')
        with self.assertRaises(ValueError): Monitor(wire,0).start(0x4000)
        self.assertFalse(wire.sent)
