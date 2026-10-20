from __future__ import annotations

import io
import os
import pty
import socket
import termios
import unittest
from unittest.mock import patch

from ravi.transport import (
    FDTransport,
    LoggedTransport,
    SerialTransport,
    SocketTransport,
    TransportError,
)


class SerialTransportTests(unittest.TestCase):
    def test_odd_parity_two_stop_bits_requested_without_flow_control(self):
        # PTYs may silently drop PARENB; inspect the actual tcsetattr request.
        master, slave = pty.openpty()
        try:
            original = termios.tcgetattr(slave)
            with patch("ravi.transport.termios.tcsetattr") as configure:
                transport = SerialTransport(
                    os.ttyname(slave), 9600, parity="O", stop_bits=2
                )
                attrs = configure.call_args.args[2]
                self.assertEqual(attrs[0], 0)  # includes IXON/IXOFF/ISTRIP off
                flags = termios.CS8 | termios.CREAD | termios.CLOCAL
                flags |= termios.PARENB | termios.PARODD | termios.CSTOPB
                self.assertEqual(attrs[2], flags)
                self.assertEqual(attrs[4:6], [termios.B9600] * 2)
                transport.close()
                self.assertEqual(configure.call_args.args[2], original)
        finally:
            os.close(master)
            os.close(slave)

    def test_bad_format_rejected_before_open(self):
        with patch("ravi.transport.os.open") as opened:
            for options in ({"parity": "x"}, {"stop_bits": 1.5}):
                with self.assertRaises(ValueError):
                    SerialTransport("unused", **options)
            opened.assert_not_called()

    def test_raw_8n1_configuration_and_restore(self) -> None:
        master, slave = pty.openpty()
        try:
            device = os.ttyname(slave)
            original = termios.tcgetattr(slave)
            transport = SerialTransport(device, 38400)
            configured = termios.tcgetattr(transport.fd)
            self.assertEqual(configured[0], 0)
            self.assertEqual(configured[1], 0)
            self.assertEqual(configured[2] & termios.CSIZE, termios.CS8)
            self.assertFalse(configured[2] & termios.PARENB)
            self.assertFalse(configured[2] & termios.CSTOPB)
            transport.close()
            restored = termios.tcgetattr(slave)
            self.assertEqual(restored, original)
        finally:
            os.close(master)
            os.close(slave)


class FDTransportTests(unittest.TestCase):
    def test_duplicate_and_borrow_have_explicit_ownership(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        with self.assertRaises(ValueError):
            FDTransport(left.fileno())
        left.setblocking(False)
        original = left.fileno()
        for duplicate in (True, False):
            with self.subTest(duplicate=duplicate):
                transport = FDTransport(original, duplicate=duplicate)
                fd = transport.fd
                self.assertEqual(fd == original, not duplicate)
                right.sendall(b"abc")
                self.assertEqual(transport.read(3, 1), b"abc")
                transport.write(b"ok")
                self.assertEqual(right.recv(2), b"ok")
                transport.close()
                transport.close()
                os.fstat(original)
                self.assertFalse(os.get_blocking(original))
                if duplicate:
                    with self.assertRaises(OSError):
                        os.fstat(fd)
                with self.assertRaises(TransportError):
                    transport.write(b"closed")


class StreamContractTests(unittest.TestCase):
    def setUp(self):
        self.master, self.slave = pty.openpty()
        self.serial = SerialTransport(os.ttyname(self.slave))
        self.addCleanup(os.close, self.master)
        self.addCleanup(os.close, self.slave)
        self.addCleanup(self.serial.close)

    def test_serial_fragmentation_and_idle_poll(self):
        self.assertEqual(self.serial.read(10, 0), b"")
        os.write(self.master, b"abcdef")
        self.assertEqual(self.serial.read(2, 1), b"ab")
        self.assertEqual(self.serial.read(4, 1), b"cdef")
        self.serial.write(b"reply")
        self.assertEqual(os.read(self.master, 5), b"reply")

    def test_serial_short_writes_and_transient_races(self):
        accepted = bytearray()
        attempts = iter([InterruptedError(), BlockingIOError(), 2, 1, 3])

        def write(fd, data):
            self.assertEqual(fd, self.serial.fd)
            result = next(attempts)
            if isinstance(result, Exception):
                raise result
            accepted.extend(data[:result])
            return result

        with patch("ravi.transport.os.write", side_effect=write):
            self.serial.write(b"abcdef")
        self.assertEqual(accepted, b"abcdef")

    def test_serial_write_has_one_deadline_despite_partial_progress(self):
        with (
            patch("ravi.transport.time.monotonic", side_effect=[0, 1, 4, 6]),
            patch(
                "ravi.transport.select.select",
                return_value=([], [self.serial.fd], []),
            ) as select,
            patch("ravi.transport.os.write", return_value=1),
            self.assertRaisesRegex(TransportError, "timeout"),
        ):
            self.serial.write(b"abcdef")
        self.assertEqual([call.args[3] for call in select.call_args_list], [4, 1])

    def test_serial_zero_write_is_not_an_infinite_loop(self):
        with (
            patch(
                "ravi.transport.os.write",
                side_effect=[0, AssertionError("retried zero write")],
            ),
            self.assertRaises(TransportError),
        ):
            self.serial.write(b"x")

    def test_serial_read_transient_race_and_eof(self):
        with (
            patch(
                "ravi.transport.select.select",
                return_value=([self.serial.fd], [], []),
            ),
            patch(
                "ravi.transport.os.read",
                side_effect=[BlockingIOError(), InterruptedError(), b"x", b""],
            ),
        ):
            self.assertEqual(self.serial.read(1, 1), b"x")
            with self.assertRaises(TransportError):
                self.serial.read(1, 1)

    def test_close_releases_fd_even_if_restore_fails(self):
        fd = self.serial.fd
        with (
            patch(
                "ravi.transport.termios.tcsetattr",
                side_effect=termios.error("unplugged"),
            ),
            self.assertRaises(termios.error),
        ):
            self.serial.close()
        with self.assertRaises(OSError):
            os.fstat(fd)
        self.serial.close()  # idempotent, including after a failed restoration

    def test_initialization_failure_releases_fd(self):
        fd = os.dup(self.slave)
        with (
            patch("ravi.transport.os.open", return_value=fd),
            patch(
                "ravi.transport.termios.tcgetattr", side_effect=termios.error("gone")
            ),
            self.assertRaises(termios.error),
        ):
            SerialTransport("unused")
        with self.assertRaises(OSError):
            os.fstat(fd)

    def test_socket_idle_fragmentation_eof_and_write_timeout_independence(self):
        # Real sockets exercise EOF/nonblocking behavior; only connection setup is substituted.
        left, right = socket.socketpair()
        self.addCleanup(right.close)
        with (
            patch("ravi.transport.socket.create_connection", return_value=left),
            patch.object(socket.socket, "setsockopt"),
        ):
            transport = SocketTransport("unused", 1)
        self.addCleanup(transport.close)
        self.assertEqual(transport.read(10, 0), b"")
        right.sendall(b"abcdef")
        self.assertEqual(transport.read(2, 1), b"ab")
        self.assertEqual(transport.read(4, 1), b"cdef")
        transport.read(1, 0)
        transport.write(b"reply")
        self.assertEqual(right.recv(5), b"reply")
        self.assertEqual(left.gettimeout(), 5.0)
        right.close()
        with self.assertRaises(TransportError):
            transport.read(1, 1)

    def test_logs_preserve_exact_stream_and_attempted_tx(self):
        rx, tx = io.BytesIO(), io.BytesIO()
        logged = LoggedTransport(self.serial, rx, tx)
        os.write(self.master, b"abc")
        self.assertEqual(logged.read(1, 1), b"a")
        self.assertEqual(logged.read(2, 1), b"bc")
        logged.read(1, 0)
        with (
            patch.object(self.serial, "write", side_effect=TransportError("gone")),
            self.assertRaises(TransportError),
        ):
            logged.write(b"attempt")
        self.assertEqual(rx.getvalue(), b"abc")
        self.assertEqual(tx.getvalue(), b"attempt")


if __name__ == "__main__":
    unittest.main()
