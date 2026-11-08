import os
import pty
import unittest
from ravi.transport import SerialTransport


class ExclusiveSerialTests(unittest.TestCase):
    def test_second_owner_rejected_and_lock_released(self):
        master, slave = pty.openpty()
        try:
            name = os.ttyname(slave)
            with SerialTransport(name, 9600, stop_bits=2, exclusive=True):
                with self.assertRaises(OSError):
                    SerialTransport(name, 9600, exclusive=True)
            with SerialTransport(name, 9600, exclusive=True):
                pass
        finally:
            os.close(master)
            os.close(slave)
